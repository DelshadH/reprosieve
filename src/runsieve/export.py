from __future__ import annotations

import shutil
from pathlib import Path

from .capsule import load_capsule, read_capsule_document
from .predicate import predicate_spec_from_json
from .safeio import ensure_new_path, ensure_regular_file
from .schema import safe_relative_path

_REPRODUCER = r'''from __future__ import annotations

import hashlib
import json
import os
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from pathlib import Path, PurePosixPath

CAPSULE = Path(__file__).with_name("capsule.runsieve")
MAX_ARCHIVE = 32 * 1024 * 1024
MAX_MEMBER = 16 * 1024 * 1024
MAX_TOTAL = 64 * 1024 * 1024
MAX_MEMBERS = 512
MAX_RATIO = 20


def fail(message: str, code: int = 2) -> int:
    print(message)
    return code


def safe_path(value: str) -> str:
    if not value or "\\" in value or "\x00" in value:
        raise ValueError("unsafe path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("unsafe path")
    if ":" in path.parts[0] or path.parts[0].startswith("~") or path.as_posix() != value:
        raise ValueError("unsafe path")
    return value


def load() -> tuple[dict[str, bytes], dict[str, object]]:
    if CAPSULE.is_symlink() or not CAPSULE.is_file() or CAPSULE.stat().st_size > MAX_ARCHIVE:
        raise ValueError("invalid capsule")
    with zipfile.ZipFile(CAPSULE) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_MEMBERS:
            raise ValueError("too many members")
        names: set[str] = set()
        total = 0
        for info in infos:
            safe_path(info.filename)
            if info.filename in names:
                raise ValueError("duplicate member")
            names.add(info.filename)
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError("symlink member")
            if info.file_size > MAX_MEMBER:
                raise ValueError("member too large")
            total += info.file_size
            if total > MAX_TOTAL:
                raise ValueError("capsule too large")
            if info.file_size / max(1, info.compress_size) > MAX_RATIO:
                raise ValueError("expansion ratio")
        members = {info.filename: archive.read(info) for info in infos}
    manifest = json.loads(members["manifest.json"])
    if manifest.get("format") != "runsieve-capsule" or manifest.get("format_version") != 1:
        raise ValueError("unsupported capsule")
    entries = manifest.get("entries")
    if not isinstance(entries, dict) or set(entries) != set(members) - {"manifest.json"}:
        raise ValueError("invalid manifest")
    content = hashlib.sha256()
    for name in sorted(entries):
        descriptor = entries[name]
        payload = members[name]
        digest = hashlib.sha256(payload).hexdigest()
        if not isinstance(descriptor, dict):
            raise ValueError("invalid manifest entry")
        if descriptor.get("sha256") != digest or descriptor.get("size") != len(payload):
            raise ValueError("hash mismatch")
        content.update(name.encode())
        content.update(b"\0")
        content.update(bytes.fromhex(digest))
    if manifest.get("content_sha256") != content.hexdigest():
        raise ValueError("content hash mismatch")
    return members, manifest


def replay(members: dict[str, bytes], trace_id: str) -> dict[str, object]:
    events = json.loads(members["events/v1.json"])
    kinds = {event["id"]: event["kind"] for event in events}
    models: list[dict[str, object]] = []
    tools: list[dict[str, object]] = []
    for event in events:
        if event["kind"] == "model_response":
            request = next(item for item in event["dependencies"] if kinds[item] == "model_request")
            payload = event["payload"]
            models.append({
                "event_id": event["id"],
                "request_id": request,
                "output": payload.get("output") if isinstance(payload, dict) else payload,
            })
        elif event["kind"] == "tool_result":
            call = next(item for item in event["dependencies"] if kinds[item] == "tool_call")
            payload = event["payload"]
            item = {"call_id": call, "event_id": event["id"]}
            if isinstance(payload, dict):
                for key in ("name", "output", "error"):
                    if key in payload:
                        item[key] = payload[key]
            else:
                item["output"] = payload
            tools.append(item)
    return {
        "events_replayed": len(events),
        "mode": "recorded-output-materialization",
        "model_outputs": models,
        "tool_outputs": tools,
        "trace_id": trace_id,
    }


def guard_source(timeout: float, output_limit: int, process_limit: int) -> str:
    cpu = max(1, int(timeout) + 2)
    return (
        "import socket,sys\n"
        "def denied(*a,**k): raise PermissionError('network disabled')\n"
        "socket.create_connection=denied\n"
        "socket.getaddrinfo=denied\n"
        "socket.socket.connect=denied\n"
        "socket.socket.connect_ex=denied\n"
        "sys.setrecursionlimit(min(sys.getrecursionlimit(),1000))\n"
        "try:\n"
        " import resource\n"
        f" resource.setrlimit(resource.RLIMIT_CPU,({cpu},{cpu}))\n"
        f" resource.setrlimit(resource.RLIMIT_FSIZE,({output_limit},{output_limit}))\n"
        f" resource.setrlimit(resource.RLIMIT_NPROC,({process_limit},{process_limit}))\n"
        " resource.setrlimit(resource.RLIMIT_NOFILE,(64,64))\n"
        "except (ImportError,ValueError,OSError): pass\n"
        "_root=__import__('os').path.realpath(__import__('os').environ['RUNSIEVE_WORKSPACE'])\n"
        "_capsule=__import__('os').path.realpath(__import__('os').environ['RUNSIEVE_CAPSULE'])\n"
        "_prefixes=tuple(__import__('os').path.realpath(p) for p in {sys.prefix,sys.base_prefix})\n"
        "def inside(path,roots):\n"
        " try: resolved=__import__('os').path.realpath(__import__('os').fspath(path))\n"
        " except TypeError: return True\n"
        " return any(resolved==root or resolved.startswith(root+__import__('os').sep) for root in roots)\n"
        "def audit(event,args):\n"
        " if event.startswith('socket.'):\n"
        "  raise PermissionError('network disabled')\n"
        " if event=='open' and args:\n"
        "  mode=args[1] if len(args)>1 and isinstance(args[1],str) else ''\n"
        "  flags=args[2] if len(args)>2 and isinstance(args[2],int) else 0\n"
        "  writing=any(c in mode for c in 'wax+') or bool(flags&3)\n"
        "  roots=(_root,) if writing else (_root,_capsule,*_prefixes)\n"
        "  if not inside(args[0],roots): raise PermissionError('filesystem access denied')\n"
        " if event.startswith('subprocess.') or event in "
        "{'os.system','os.spawn','os.posix_spawn','os.fork','pty.spawn','ctypes.dlopen'}:\n"
        "  raise PermissionError('child processes and native loading disabled')\n"
        " if event in {'os.remove','os.rmdir','os.mkdir','os.chdir'} "
        "and args and not inside(args[0],(_root,)):\n"
        "  raise PermissionError('filesystem access denied')\n"
        " if event in {'os.listdir','os.scandir'} and args and "
        "not inside(args[0],(_root,*_prefixes)):\n"
        "  raise PermissionError('filesystem access denied')\n"
        " if event in {'os.rename','os.replace'} and any(not inside(p,(_root,)) for p in args[:2]):\n"
        "  raise PermissionError('filesystem access denied')\n"
        "sys.addaudithook(audit)\n"
        "def uncaught(_kind,_value,_traceback): __import__('os')._exit(2)\n"
        "sys.excepthook=uncaught\n"
    )


def terminate(process: subprocess.Popen[bytes]) -> None:
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except OSError:
        pass


def run_command(
    command: list[str],
    *,
    root: Path,
    environment: dict[str, str],
    deadline: float,
    output_limit: int,
    label: str,
) -> tuple[int | None, int]:
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
    process = subprocess.Popen(
        command,
        cwd=root,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        start_new_session=os.name == "posix",
        creationflags=creationflags,
    )
    counts = [0, 0]
    exceeded = threading.Event()
    lock = threading.Lock()

    def drain(stream: object, index: int) -> None:
        while True:
            try:
                chunk = stream.read(4096)
            except OSError:
                return
            if not chunk:
                return
            with lock:
                counts[index] += len(chunk)
                if sum(counts) > output_limit:
                    exceeded.set()
                    return

    threads = [
        threading.Thread(target=drain, args=(process.stdout, 0), daemon=True),
        threading.Thread(target=drain, args=(process.stderr, 1), daemon=True),
    ]
    for thread in threads:
        thread.start()
    while process.poll() is None:
        if exceeded.is_set() or time.monotonic() >= deadline:
            terminate(process)
            process.wait()
            for thread in threads:
                thread.join(timeout=1)
            return None, sum(counts)
        time.sleep(0.01)
    for thread in threads:
        thread.join(timeout=1)
    output_bytes = sum(counts)
    if exceeded.is_set() or output_bytes > output_limit:
        return None, output_bytes
    return process.returncode, output_bytes


def trial(
    members: dict[str, bytes],
    manifest: dict[str, object],
    predicate: dict[str, object],
    index: int,
) -> int | None:
    with tempfile.TemporaryDirectory(prefix="runsieve-repro-") as temporary:
        root = Path(temporary)
        workspace_index = json.loads(members["workspace/index.json"])
        if not isinstance(workspace_index, list):
            return None
        for raw_path in workspace_index:
            if not isinstance(raw_path, str):
                return None
            path = safe_path(raw_path)
            target = root.joinpath(*PurePosixPath(path).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(members[f"workspace/files/{path}"])
        replay_path = root / "replay.json"
        replay_path.write_text(
            json.dumps(replay(members, str(manifest["trace_id"])), sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        guard = root / ".guard"
        guard.mkdir()
        timeout = float(predicate["timeout_seconds"])
        output_limit = int(predicate["output_limit_bytes"])
        process_limit = int(predicate["process_limit"])
        (guard / "sitecustomize.py").write_text(
            guard_source(timeout, output_limit, process_limit),
            encoding="utf-8",
        )
        argv = predicate["argv"]
        if not isinstance(argv, list) or len(argv) < 2 or not all(isinstance(item, str) for item in argv):
            return None
        if Path(argv[0]).name.lower() not in {"python", "python3", "python.exe", "py"}:
            return None
        script = safe_path(argv[1])
        if script not in workspace_index:
            return None
        command = [sys.executable, script, *argv[2:]]
        environment: dict[str, str] = {}
        captured_environment = json.loads(members["environment.json"])
        if not isinstance(captured_environment, dict) or any(
            not isinstance(name, str) or not isinstance(value, str)
            for name, value in captured_environment.items()
        ):
            return None
        provider_prefixes = (
            "OPENAI_", "ANTHROPIC_", "AZURE_", "AWS_ACCESS", "AWS_SECRET",
            "GOOGLE_API", "GEMINI_", "COHERE_", "MISTRAL_",
        )
        proxy_names = {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"}
        for name, value in captured_environment.items():
            upper = name.upper()
            if upper not in proxy_names and not any(
                upper.startswith(prefix) for prefix in provider_prefixes
            ):
                environment[name] = value
        for name in ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "LANG", "LC_ALL"):
            if os.environ.get(name):
                environment[name] = os.environ[name]
        environment.update({
            "HOME": str(root),
            "USERPROFILE": str(root),
            "TMP": str(root),
            "TEMP": str(root),
            "HTTP_PROXY": "",
            "HTTPS_PROXY": "",
            "ALL_PROXY": "",
            "NO_PROXY": "",
            "PYTHONPATH": str(guard),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "RUNSIEVE_CAPSULE": str(CAPSULE),
            "RUNSIEVE_MODE": "offline",
            "RUNSIEVE_REPLAY": str(replay_path),
            "RUNSIEVE_TRIAL": str(index),
            "RUNSIEVE_WORKSPACE": str(root),
        })
        deadline = time.monotonic() + timeout
        metadata = json.loads(members["metadata.json"])
        if not isinstance(metadata, dict):
            return None
        if "application_replay" in metadata:
            return None
        consumed_output = 0
        remaining_output = output_limit
        if remaining_output < 1:
            return None
        predicate_exit, predicate_output = run_command(
            command,
            root=root,
            environment=environment,
            deadline=deadline,
            output_limit=remaining_output,
            label="predicate",
        )
        if consumed_output + predicate_output > output_limit:
            return None
        return predicate_exit


def main() -> int:
    try:
        members, manifest = load()
        predicate = json.loads(members["predicate.json"])
        if not isinstance(predicate, dict):
            return fail("invalid predicate")
        trials = int(predicate["trials"])
        required = int(predicate["required_reproductions"])
        results = [trial(members, manifest, predicate, index) for index in range(trials)]
        if any(result not in {0, 1} for result in results):
            return fail("reproduction harness invalid")
        if sum(result == 0 for result in results) >= required:
            print("target failure reproduced offline")
            return 0
        return fail("target failure absent", 1)
    except Exception:  # noqa: BLE001 - reject untrusted capsules without a traceback.
        return fail("reproduction capsule invalid")


if __name__ == "__main__":
    raise SystemExit(main())
'''


def export_reproduction(source: str | Path, output: str | Path) -> Path:
    source_path = ensure_regular_file(source, label="export source")
    capsule = load_capsule(source_path)
    if "application_replay" in capsule.metadata:
        raise ValueError("application replay is not supported in the seed release")
    predicate_document = read_capsule_document(source_path, "predicate.json")
    spec = predicate_spec_from_json(predicate_document)
    if len(spec.argv) < 2 or Path(spec.argv[0]).name.casefold() not in {
        "python",
        "python3",
        "python.exe",
        "py",
    }:
        raise ValueError("export requires an embedded Python predicate")
    script = safe_relative_path(spec.argv[1], label="predicate script")
    if script not in capsule.workspace:
        raise ValueError("export predicate script is not embedded in the capsule")

    destination = ensure_new_path(output, label="export output")
    destination.mkdir(mode=0o700)
    try:
        (destination / "capsule.runsieve").write_bytes(source_path.read_bytes())
        (destination / "reproduce.py").write_text(_REPRODUCER, encoding="utf-8", newline="\n")
        (destination / "README.md").write_text(
            "# RunSieve issue reproduction\n\n"
            "Run the redacted, offline reproduction with:\n\n"
            "```bash\npython reproduce.py\n```\n\n"
            "The command validates the capsule, reconstructs recorded model and tool outputs, "
            "runs any declared embedded application adapter before the predicate, denies "
            "outbound network, and never calls the original provider or tools.\n",
            encoding="utf-8",
            newline="\n",
        )
    except Exception:
        shutil.rmtree(destination)
        raise
    return destination
