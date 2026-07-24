from __future__ import annotations

import argparse
import base64
import hashlib
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from .capsule import (
    canonical_json,
    capsule_bytes,
    capsule_file_sha256,
    load_capsule,
    read_capsule_document,
    write_capsule,
)
from .ddmin import PredicateResult
from .export import export_reproduction
from .hierarchy import minimize_capsule
from .predicate import (
    PredicateSpec,
    run_predicate,
)
from .replay import offline_replay, write_replay
from .safeio import ensure_new_path, ensure_real_directory, ensure_regular_file
from .verify import verify_one_minimal


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="runsieve",
        description="Capture and reduce a failed agent run into an offline reproduction.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    capture = subparsers.add_parser("capture", help="capture one OpenAI Agents SDK trace")
    capture.add_argument("--output", required=True)
    capture.add_argument("--workspace-root", default=".")
    capture.add_argument("--include", action="append", default=[])
    capture.add_argument("--env", action="append", default=[])
    capture.add_argument("--canary-env", action="append", default=[])
    capture.add_argument("--redact-regex", action="append", default=[])
    capture.add_argument("--allow-path", action="append", default=[])
    capture.add_argument("--deny-path", action="append", default=[])
    capture.add_argument("--max-events", type=int, default=10_000)
    capture.add_argument("--timeout", type=float, default=300.0)
    capture.add_argument("--retain-sdk-exporter", action="store_true")
    capture.add_argument("target", nargs=argparse.REMAINDER)

    minimize = subparsers.add_parser("minimize", help="reduce a capsule with a predicate")
    minimize.add_argument("source")
    minimize.add_argument("--output-dir", required=True)
    _predicate_arguments(minimize)

    replay = subparsers.add_parser("replay", help="replay recorded outputs without providers")
    replay.add_argument("source")
    replay.add_argument("--offline", action="store_true", default=True)
    replay.add_argument("--output")

    verify = subparsers.add_parser(
        "verify-minimal",
        help="independently verify 1-minimality",
    )
    verify.add_argument("source")
    _predicate_arguments(verify)

    export = subparsers.add_parser("export", help="write a one-command issue reproduction")
    export.add_argument("source")
    export.add_argument("--format", choices=("repro-dir",), default="repro-dir")
    export.add_argument("--output", required=True)
    return parser


def _predicate_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--output-limit", type=int, default=64 * 1024)
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--required", type=int, default=1)
    parser.add_argument("--process-limit", type=int, default=16)
    parser.add_argument("--predicate", nargs=argparse.REMAINDER, required=True)


def _strip_separator(values: Sequence[str]) -> tuple[str, ...]:
    result = tuple(values)
    if result and result[0] == "--":
        result = result[1:]
    return result


def _spec(args: argparse.Namespace) -> PredicateSpec:
    return PredicateSpec(
        argv=_strip_separator(args.predicate),
        timeout_seconds=args.timeout,
        output_limit_bytes=args.output_limit,
        required_reproductions=args.required,
        trials=args.trials,
        process_limit=args.process_limit,
    )


def _resolve_target(argv: tuple[str, ...]) -> list[str]:
    if not argv:
        raise ValueError("capture target command is required")
    first = argv[0]
    if Path(first).name.casefold() in {"python", "python3", "python.exe", "py"}:
        return [sys.executable, *argv[1:]]
    if "/" in first or "\\" in first:
        executable = ensure_regular_file(first, label="capture target executable")
        return [str(executable), *argv[1:]]
    resolved = shutil.which(first)
    if resolved is None:
        raise ValueError("capture target executable was not found")
    return [resolved, *argv[1:]]


def _terminate(process: subprocess.Popen[bytes]) -> None:
    try:
        if sys.platform == "win32":
            process.kill()
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except OSError:
        pass


def _capture(args: argparse.Namespace) -> int:
    output = ensure_new_path(args.output, label="capture output")
    canaries: list[str] = []
    for name in args.canary_env:
        value = os.environ.get(name)
        if value:
            canaries.append(value)
    if any(canary in str(output) for canary in canaries):
        raise ValueError("capture output path contains a declared canary")
    target = _resolve_target(_strip_separator(args.target))
    if not 0 < args.timeout <= 86_400:
        raise ValueError("capture timeout is invalid")
    config = {
        "allow_paths": args.allow_path,
        "deny_paths": args.deny_path,
        "environment_names": args.env,
        "exact_canaries": canaries,
        "max_events": args.max_events,
        "output_path": str(output),
        "patterns": args.redact_regex,
        "retain_existing": args.retain_sdk_exporter,
        "workspace_paths": args.include,
        "workspace_root": str(ensure_real_directory(args.workspace_root, label="workspace root")),
    }
    encoded = base64.b64encode(canonical_json(config)).decode("ascii")
    with tempfile.TemporaryDirectory(prefix="runsieve-capture-") as temporary:
        bootstrap = Path(temporary)
        (bootstrap / "sitecustomize.py").write_text(
            "import os\n"
            "try:\n"
            "    from runsieve._capture_bootstrap import install_from_environment\n"
            "    install_from_environment()\n"
            "except Exception:\n"
            "    os._exit(78)\n",
            encoding="utf-8",
            newline="\n",
        )
        environment = dict(os.environ)
        environment["RUNSIEVE_CAPTURE_CONFIG_B64"] = encoded
        previous_pythonpath = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = (
            str(bootstrap)
            if not previous_pythonpath
            else os.pathsep.join((str(bootstrap), previous_pythonpath))
        )
        creationflags = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
        )
        process = subprocess.Popen(
            target,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            start_new_session=os.name == "posix",
            creationflags=creationflags,
        )
        try:
            process.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired as error:
            _terminate(process)
            process.wait()
            raise ValueError("capture target timed out") from error
    if not output.is_file() or output.is_symlink():
        raise ValueError("capture target produced no complete trace capsule")
    load_capsule(output)
    print("captured one redacted trace")
    return 0


def _minimize(args: argparse.Namespace) -> int:
    source_path = Path(args.source)
    source = load_capsule(source_path)
    source_sha256 = capsule_file_sha256(source_path)
    spec = _spec(args)
    predicate_hash = hashlib.sha256(canonical_json(spec.to_json())).hexdigest()
    working = replace(
        source,
        metadata={
            **source.metadata,
            "predicate": {
                "mode": "probabilistic" if spec.trials > 1 else "deterministic",
                "sha256": predicate_hash,
            },
            "provenance": {
                "source_sha256": source_sha256,
                "source_trace_id": source.trace_id,
            },
        },
    )

    def evaluate(candidate: object) -> PredicateResult:
        return run_predicate(candidate, spec).result  # type: ignore[arg-type]

    result = minimize_capsule(working, evaluate)
    proof = verify_one_minimal(result.capsule, evaluate)
    if not proof.is_one_minimal:
        raise RuntimeError("independent 1-minimality verification failed")
    reduction = result.report.to_json()
    reduction.pop("wall_seconds", None)
    final = replace(
        result.capsule,
        metadata={
            **result.capsule.metadata,
            "minimality": proof.to_json(),
            "offline_proof": {"original_tool_calls": 0, "provider_calls": 0},
            "reduction": reduction,
        },
    )
    if run_predicate(final, spec).result is not PredicateResult.REPRODUCES:
        raise RuntimeError("decorated reduced capsule no longer reproduces")
    output_directory = Path(os.path.abspath(args.output_dir))
    if output_directory.exists():
        output_directory = ensure_real_directory(
            output_directory,
            label="minimize output",
        )
    else:
        ensure_new_path(output_directory, label="minimize output")
        output_directory.mkdir()
    redaction = read_capsule_document(source_path, "redaction.json")
    data = capsule_bytes(final, redaction_report=redaction, predicate=spec.to_json())
    digest = hashlib.sha256(data).hexdigest()
    destination = output_directory / f"{digest}.runsieve"
    if destination.exists():
        if destination.read_bytes() != data:
            raise RuntimeError("hash-addressed output collision")
    else:
        info = write_capsule(
            final,
            destination,
            redaction_report=redaction,
            predicate=spec.to_json(),
        )
        if info.sha256 != digest:
            raise RuntimeError("hash-addressed output verification failed")
    print(
        f"reduced {len(source.events)} events to {len(final.events)}; "
        f"1-minimal; {result.report.predicate_calls} predicate calls; "
        f"{result.report.wall_seconds:.3f}s; artifact {digest}.runsieve"
    )
    return 0


def _replay(args: argparse.Namespace) -> int:
    report = offline_replay(load_capsule(args.source))
    if args.output:
        write_replay(report, args.output)
        print("wrote deterministic offline replay")
    else:
        sys.stdout.buffer.write(canonical_json(report.to_json()))
    return 0


def _verify(args: argparse.Namespace) -> int:
    source_path = Path(args.source)
    capsule = load_capsule(source_path)
    spec = _spec(args)
    stored = read_capsule_document(source_path, "predicate.json")
    if stored and stored != spec.to_json():
        raise ValueError("predicate does not match the capsule's recorded predicate")

    def evaluate(candidate: object) -> PredicateResult:
        return run_predicate(candidate, spec).result  # type: ignore[arg-type]

    proof = verify_one_minimal(capsule, evaluate)
    if proof.is_one_minimal:
        print(f"verified 1-minimality with {len(proof.attempts)} independent deletions")
        return 0
    print(f"not 1-minimal: {len(proof.reproducing_deletions)} deletion(s) still reproduce")
    return 1


def _export(args: argparse.Namespace) -> int:
    export_reproduction(args.source, args.output)
    print("exported one-command offline issue reproduction")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        handlers = {
            "capture": _capture,
            "minimize": _minimize,
            "replay": _replay,
            "verify-minimal": _verify,
            "export": _export,
        }
        return handlers[args.command](args)
    except (FileExistsError, OSError, RuntimeError, ValueError) as error:
        print(f"runsieve: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
