from __future__ import annotations

import hashlib
import math
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .capsule import canonical_json, capsule_bytes, write_capsule
from .ddmin import PredicateResult
from .replay import offline_replay, write_replay
from .safeio import ensure_regular_file
from .schema import Capsule, JsonValue, safe_relative_path, validate_capsule

_PROVIDER_PREFIXES = (
    "OPENAI_",
    "ANTHROPIC_",
    "AZURE_",
    "AWS_ACCESS",
    "AWS_SECRET",
    "GOOGLE_API",
    "GEMINI_",
    "COHERE_",
    "MISTRAL_",
)
_PROXY_NAMES = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")
_MAX_TRIALS = 100


@dataclass(frozen=True, slots=True)
class PredicateSpec:
    argv: tuple[str, ...]
    timeout_seconds: float = 10.0
    output_limit_bytes: int = 64 * 1024
    required_reproductions: int = 1
    trials: int = 1
    process_limit: int = 16

    def __post_init__(self) -> None:
        if not self.argv or any(
            not isinstance(item, str)
            or not item
            or "\x00" in item
            or len(item.encode("utf-8")) > 16 * 1024
            for item in self.argv
        ):
            raise ValueError("predicate argv is invalid")
        if not math.isfinite(self.timeout_seconds) or not 0 < self.timeout_seconds <= 3600:
            raise ValueError("predicate timeout is invalid")
        if not 256 <= self.output_limit_bytes <= 16 * 1024 * 1024:
            raise ValueError("predicate output limit is invalid")
        if not 1 <= self.trials <= _MAX_TRIALS:
            raise ValueError("predicate trial count is invalid")
        if not 1 <= self.required_reproductions <= self.trials:
            raise ValueError("predicate reproduction threshold is invalid")
        if not 1 <= self.process_limit <= 128:
            raise ValueError("predicate process limit is invalid")
        if Path(self.argv[0]).name.casefold() not in {
            "python",
            "python3",
            "python.exe",
            "py",
        }:
            raise ValueError("only embedded Python predicates are supported")
        if len(self.argv) < 2:
            raise ValueError("predicate must name an embedded Python script")
        safe_relative_path(self.argv[1], label="predicate script")

    def to_json(self) -> dict[str, JsonValue]:
        return {
            "argv": list(self.argv),
            "output_limit_bytes": self.output_limit_bytes,
            "process_limit": self.process_limit,
            "required_reproductions": self.required_reproductions,
            "timeout_seconds": self.timeout_seconds,
            "trials": self.trials,
        }


@dataclass(frozen=True, slots=True)
class PredicateAttempt:
    trial: int
    result: PredicateResult
    reason: str
    exit_code: int | None
    signal: int | None
    duration_seconds: float
    output_bytes: int
    stdout_sha256: str
    stderr_sha256: str
    workspace_id: str
    network_guard: str
    application_replay: bool = False
    application_exit_code: int | None = None

    def to_json(self) -> dict[str, JsonValue]:
        return {
            "application_exit_code": self.application_exit_code,
            "application_replay": self.application_replay,
            "exit_code": self.exit_code,
            "network_guard": self.network_guard,
            "output_bytes": self.output_bytes,
            "reason": self.reason,
            "result": self.result.value,
            "signal": self.signal,
            "stderr_sha256": self.stderr_sha256,
            "stdout_sha256": self.stdout_sha256,
            "trial": self.trial,
            "workspace_id": self.workspace_id,
        }


@dataclass(frozen=True, slots=True)
class PredicateReport:
    result: PredicateResult
    attempts: tuple[PredicateAttempt, ...]
    cache_key: str
    probabilistic: bool
    required_reproductions: int
    trials: int

    def to_json(self) -> dict[str, JsonValue]:
        return {
            "attempts": [attempt.to_json() for attempt in self.attempts],
            "cache_key": self.cache_key,
            "mode": "probabilistic" if self.probabilistic else "deterministic",
            "required_reproductions": self.required_reproductions,
            "result": self.result.value,
            "trials": self.trials,
        }


def predicate_spec_from_json(value: object) -> PredicateSpec:
    if not isinstance(value, dict):
        raise ValueError("predicate document must be an object")
    required = {
        "argv",
        "output_limit_bytes",
        "process_limit",
        "required_reproductions",
        "timeout_seconds",
        "trials",
    }
    if set(value) != required:
        raise ValueError("predicate document fields are invalid")
    argv = value["argv"]
    if not isinstance(argv, list) or not all(isinstance(item, str) for item in argv):
        raise ValueError("predicate argv is invalid")
    numeric_names = (
        "output_limit_bytes",
        "process_limit",
        "required_reproductions",
        "trials",
    )
    if any(isinstance(value[name], bool) or not isinstance(value[name], int) for name in numeric_names):
        raise ValueError("predicate numeric fields are invalid")
    timeout = value["timeout_seconds"]
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise ValueError("predicate timeout is invalid")
    return PredicateSpec(
        argv=tuple(argv),
        timeout_seconds=float(timeout),
        output_limit_bytes=value["output_limit_bytes"],
        required_reproductions=value["required_reproductions"],
        trials=value["trials"],
        process_limit=value["process_limit"],
    )


def predicate_cache_key(capsule: Capsule, spec: PredicateSpec) -> str:
    validate_capsule(capsule)
    digest = hashlib.sha256()
    digest.update(b"reprosieve-predicate-cache-v1\0")
    digest.update(hashlib.sha256(capsule_bytes(capsule)).digest())
    digest.update(hashlib.sha256(canonical_json(spec.to_json())).digest())
    digest.update(b"\0offline")
    return digest.hexdigest()


def _resolve_executable(argv: tuple[str, ...], workspace: Path) -> tuple[list[str], bool]:
    first = argv[0]
    basename = Path(first).name.casefold()
    if basename in {"python", "python3", "python.exe", "py"}:
        if len(argv) < 2:
            raise ValueError("predicate must name an embedded Python script")
        script = safe_relative_path(argv[1], label="predicate script")
        target = ensure_regular_file(workspace / Path(script), label="predicate script")
        try:
            target.relative_to(workspace)
        except ValueError as error:
            raise ValueError("predicate script escapes the workspace") from error
        return [sys.executable, script, *argv[2:]], True
    raise ValueError("only embedded Python predicates are supported")


def _network_guard_source(timeout: float, output_limit: int, process_limit: int) -> str:
    cpu_seconds = max(1, math.ceil(timeout) + 1)
    return (
        "import socket, sys\n"
        "def _reprosieve_denied(*args, **kwargs):\n"
        "    raise PermissionError('outbound network disabled by ReproSieve')\n"
        "socket.create_connection = _reprosieve_denied\n"
        "socket.getaddrinfo = _reprosieve_denied\n"
        "socket.socket.connect = _reprosieve_denied\n"
        "socket.socket.connect_ex = _reprosieve_denied\n"
        "try:\n"
        "    import _winapi\n"
        "    for _name in ('CreateProcess', 'CreateProcessAsUser', 'CreateProcessWithLogonW'):\n"
        "        if hasattr(_winapi, _name): setattr(_winapi, _name, _reprosieve_denied)\n"
        "except ImportError:\n"
        "    pass\n"
        "sys.setrecursionlimit(min(sys.getrecursionlimit(), 1000))\n"
        "try:\n"
        "    import resource\n"
        f"    resource.setrlimit(resource.RLIMIT_CPU, ({cpu_seconds}, {cpu_seconds}))\n"
        f"    resource.setrlimit(resource.RLIMIT_FSIZE, ({output_limit}, {output_limit}))\n"
        f"    resource.setrlimit(resource.RLIMIT_NPROC, ({process_limit}, {process_limit}))\n"
        "    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))\n"
        "except (ImportError, ValueError, OSError):\n"
        "    pass\n"
        "_root = __import__('os').path.realpath(__import__('os').environ['RUNSIEVE_WORKSPACE'])\n"
        "_capsule = __import__('os').path.realpath(__import__('os').environ['RUNSIEVE_CAPSULE'])\n"
        "_prefixes = tuple(__import__('os').path.realpath(p) for p in {sys.prefix, sys.base_prefix})\n"
        "def _inside(path, roots):\n"
        "    try: resolved=__import__('os').path.realpath(__import__('os').fspath(path))\n"
        "    except TypeError: return True\n"
        "    return any(resolved == root or resolved.startswith(root + __import__('os').sep) "
        "for root in roots)\n"
        "def _audit(event, args):\n"
        "    if event.startswith('socket.'):\n"
        "        raise PermissionError('outbound network disabled by ReproSieve')\n"
        "    if event == 'open' and args:\n"
        "        mode = args[1] if len(args) > 1 and isinstance(args[1], str) else ''\n"
        "        flags = args[2] if len(args) > 2 and isinstance(args[2], int) else 0\n"
        "        writing = any(c in mode for c in 'wax+') or bool(flags & 3)\n"
        "        roots = (_root,) if writing else (_root, _capsule, *_prefixes)\n"
        "        if not _inside(args[0], roots): raise PermissionError('filesystem access denied')\n"
        "    if event.startswith('subprocess.') or event in "
        "{'os.system','os.spawn','os.posix_spawn','os.fork','pty.spawn','ctypes.dlopen'}:\n"
        "        raise PermissionError('child processes and native loading disabled')\n"
        "    if event in {'os.remove','os.rmdir','os.mkdir','os.chdir'} "
        "and args and not _inside(args[0], (_root,)):\n"
        "        raise PermissionError('filesystem access denied')\n"
        "    if event in {'os.listdir','os.scandir'} and args and "
        "not _inside(args[0], (_root, *_prefixes)):\n"
        "        raise PermissionError('filesystem access denied')\n"
        "    if event in {'os.rename','os.replace'} and any(not _inside(p, (_root,)) "
        "for p in args[:2]):\n"
        "        raise PermissionError('filesystem access denied')\n"
        "sys.addaudithook(_audit)\n"
        "def _uncaught(_kind, _value, _traceback):\n"
        "    __import__('os')._exit(2)\n"
        "sys.excepthook = _uncaught\n"
    )


def _minimal_environment(
    capsule: Capsule,
    *,
    workspace: Path,
    replay_path: Path,
    capsule_path: Path,
    guard_directory: Path | None,
    application_result_path: Path | None,
    trial: int,
) -> dict[str, str]:
    environment: dict[str, str] = {}
    for name in ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "LANG", "LC_ALL"):
        value = os.environ.get(name)
        if value:
            environment[name] = value
    for name, value in capsule.environment.items():
        upper = name.upper()
        if upper in _PROXY_NAMES or any(upper.startswith(prefix) for prefix in _PROVIDER_PREFIXES):
            continue
        environment[name] = value
    environment.update(
        {
            "HOME": str(workspace),
            "USERPROFILE": str(workspace),
            "TMP": str(workspace),
            "TEMP": str(workspace),
            "RUNSIEVE_CAPSULE": str(capsule_path),
            "RUNSIEVE_REPLAY": str(replay_path),
            "RUNSIEVE_MODE": "offline",
            "RUNSIEVE_TRIAL": str(trial),
            "RUNSIEVE_WORKSPACE": str(workspace),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
        }
    )
    for name in _PROXY_NAMES:
        environment[name] = ""
    if guard_directory is not None:
        environment["PYTHONPATH"] = str(guard_directory)
    if application_result_path is not None:
        environment["RUNSIEVE_APPLICATION_RESULT"] = str(application_result_path)
    return environment


def _terminate(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        if sys.platform == "win32":
            completed = subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                timeout=2,
            )
            if completed.returncode != 0 and process.poll() is None:
                process.kill()
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            process.kill()
        except (ProcessLookupError, PermissionError, OSError):
            pass


@dataclass(frozen=True, slots=True)
class _ProcessOutcome:
    return_code: int
    reason: str | None
    output_bytes: int
    stdout_sha256: str
    stderr_sha256: str


def _run_bounded_process(
    argv: list[str],
    *,
    workspace: Path,
    environment: dict[str, str],
    deadline: float,
    output_limit_bytes: int,
    cancel_event: threading.Event | None,
) -> _ProcessOutcome:
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
    try:
        process = subprocess.Popen(
            argv,
            cwd=workspace,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            start_new_session=os.name == "posix",
            creationflags=creationflags,
        )
    except (OSError, ValueError) as error:
        raise ValueError("replay process could not be started") from error

    output_limit = threading.Event()
    counts = [0, 0]
    hashes = [hashlib.sha256(), hashlib.sha256()]
    lock = threading.Lock()

    def drain(stream: object, index: int) -> None:
        reader = stream
        while True:
            try:
                chunk = reader.read(4096)  # type: ignore[attr-defined]
            except OSError:
                return
            if not chunk:
                return
            hashes[index].update(chunk)
            with lock:
                counts[index] += len(chunk)
                if sum(counts) > output_limit_bytes:
                    output_limit.set()
                    return

    threads = [
        threading.Thread(target=drain, args=(process.stdout, 0), daemon=True),
        threading.Thread(target=drain, args=(process.stderr, 1), daemon=True),
    ]
    for thread in threads:
        thread.start()

    reason: str | None = None
    while process.poll() is None:
        if cancel_event is not None and cancel_event.is_set():
            reason = "cancelled"
            break
        if output_limit.is_set():
            reason = "output_limit"
            break
        if time.monotonic() >= deadline:
            reason = "timeout"
            break
        time.sleep(0.01)
    if reason is not None:
        _terminate(process)
    try:
        return_code = process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        _terminate(process)
        return_code = process.wait(timeout=2)
    for thread in threads:
        thread.join(timeout=1)
    if output_limit.is_set() and reason is None:
        reason = "output_limit"
    return _ProcessOutcome(
        return_code=return_code,
        reason=reason,
        output_bytes=sum(counts),
        stdout_sha256=hashes[0].hexdigest(),
        stderr_sha256=hashes[1].hexdigest(),
    )


def _execute_attempt(
    capsule: Capsule,
    spec: PredicateSpec,
    *,
    trial: int,
    cancel_event: threading.Event | None,
) -> PredicateAttempt:
    started = time.monotonic()

    def invalid_attempt(
        reason: str,
        *,
        network_guard: str = "unavailable",
        application_replay: bool = False,
        application_exit_code: int | None = None,
        outcome: _ProcessOutcome | None = None,
    ) -> PredicateAttempt:
        return PredicateAttempt(
            trial=trial,
            result=PredicateResult.INVALID,
            reason=reason,
            exit_code=None,
            signal=None,
            duration_seconds=time.monotonic() - started,
            output_bytes=outcome.output_bytes if outcome is not None else 0,
            stdout_sha256=(
                outcome.stdout_sha256
                if outcome is not None
                else hashlib.sha256().hexdigest()
            ),
            stderr_sha256=(
                outcome.stderr_sha256
                if outcome is not None
                else hashlib.sha256().hexdigest()
            ),
            workspace_id=f"trial-{trial:03d}",
            network_guard=network_guard,
            application_replay=application_replay,
            application_exit_code=application_exit_code,
        )

    if "application_replay" in capsule.metadata:
        return invalid_attempt(
            "application_replay_unsupported",
            application_replay=True,
        )

    with tempfile.TemporaryDirectory(prefix="reprosieve-predicate-") as temporary:
        workspace = Path(temporary)
        for name, content in capsule.workspace.items():
            target = workspace / Path(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
        capsule_path = workspace / "candidate.reprosieve"
        write_capsule(capsule, capsule_path, predicate=spec.to_json())
        replay_path = workspace / "replay.json"
        write_replay(offline_replay(capsule), replay_path)
        try:
            argv, is_python = _resolve_executable(spec.argv, workspace)
        except ValueError:
            return invalid_attempt("harness_invalid")
        guard_directory: Path | None = None
        network_guard = "unavailable"
        if is_python:
            guard_directory = workspace / ".reprosieve-guard"
            guard_directory.mkdir()
            (guard_directory / "sitecustomize.py").write_text(
                _network_guard_source(
                    spec.timeout_seconds,
                    spec.output_limit_bytes,
                    spec.process_limit,
                ),
                encoding="utf-8",
                newline="\n",
            )
            network_guard = "python-sitecustomize"
        environment = _minimal_environment(
            capsule,
            workspace=workspace,
            replay_path=replay_path,
            capsule_path=capsule_path,
            guard_directory=guard_directory,
            application_result_path=None,
            trial=trial,
        )
        deadline = started + spec.timeout_seconds
        application_output_bytes = 0
        application_exit_code: int | None = None
        remaining_output = spec.output_limit_bytes
        if remaining_output < 1:
            return invalid_attempt(
                "output_limit",
                network_guard=network_guard,
                application_exit_code=application_exit_code,
            )
        predicate_outcome = _run_bounded_process(
            argv,
            workspace=workspace,
            environment=environment,
            deadline=deadline,
            output_limit_bytes=remaining_output,
            cancel_event=cancel_event,
        )
        return_code = predicate_outcome.return_code
        reason = predicate_outcome.reason
        signal_number = -return_code if return_code < 0 else None
        exit_code = return_code if return_code >= 0 else None
        total_output = application_output_bytes + predicate_outcome.output_bytes
        if total_output > spec.output_limit_bytes:
            reason = "output_limit"
        if reason is not None:
            result = PredicateResult.INVALID
        elif signal_number is not None:
            reason = "signal"
            result = PredicateResult.INVALID
        elif exit_code == 0:
            reason = "exit_0"
            result = PredicateResult.REPRODUCES
        elif exit_code == 1:
            reason = "exit_1"
            result = PredicateResult.ABSENT
        elif exit_code == 2:
            reason = "exit_2"
            result = PredicateResult.INVALID
        else:
            reason = "unexpected_exit"
            result = PredicateResult.INVALID

        return PredicateAttempt(
            trial=trial,
            result=result,
            reason=reason,
            exit_code=exit_code,
            signal=signal_number,
            duration_seconds=time.monotonic() - started,
            output_bytes=min(total_output, spec.output_limit_bytes * 2),
            stdout_sha256=predicate_outcome.stdout_sha256,
            stderr_sha256=predicate_outcome.stderr_sha256,
            workspace_id=f"trial-{trial:03d}",
            network_guard=network_guard,
            application_exit_code=application_exit_code,
        )


def run_predicate(
    capsule: Capsule,
    spec: PredicateSpec,
    *,
    cancel_event: threading.Event | None = None,
) -> PredicateReport:
    validate_capsule(capsule)
    attempts = tuple(
        _execute_attempt(capsule, spec, trial=trial, cancel_event=cancel_event)
        for trial in range(spec.trials)
    )
    if any(attempt.result is PredicateResult.INVALID for attempt in attempts):
        result = PredicateResult.INVALID
    elif (
        sum(attempt.result is PredicateResult.REPRODUCES for attempt in attempts)
        >= spec.required_reproductions
    ):
        result = PredicateResult.REPRODUCES
    else:
        result = PredicateResult.ABSENT
    return PredicateReport(
        result=result,
        attempts=attempts,
        cache_key=predicate_cache_key(capsule, spec),
        probabilistic=spec.trials > 1,
        required_reproductions=spec.required_reproductions,
        trials=spec.trials,
    )
