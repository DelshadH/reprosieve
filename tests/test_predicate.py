from __future__ import annotations

import os
import signal
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest

from runsieve.ddmin import PredicateResult
from runsieve.predicate import PredicateSpec, predicate_cache_key, run_predicate
from tests.helpers import sample_capsule


def _capsule_with_script(source: str):
    capsule = sample_capsule()
    return replace(capsule, workspace={"predicate.py": source})


@pytest.mark.parametrize(
    ("exit_code", "expected"),
    [
        (0, PredicateResult.REPRODUCES),
        (1, PredicateResult.ABSENT),
        (2, PredicateResult.INVALID),
        (7, PredicateResult.INVALID),
    ],
)
def test_exit_protocol_is_strict(exit_code: int, expected: PredicateResult) -> None:
    capsule = _capsule_with_script(f"raise SystemExit({exit_code})\n")
    report = run_predicate(
        capsule,
        PredicateSpec(("python", "predicate.py"), timeout_seconds=2),
    )
    assert report.result is expected
    assert report.attempts[0].exit_code == exit_code


def test_predicate_reproduction_executes_only_the_declared_workspace_entrypoint() -> None:
    capsule = sample_capsule()
    capsule = replace(
        capsule,
        workspace={
            "predicate.py": "raise SystemExit(0)\n",
            "application.py": "raise SystemExit(2)\n",
            "original_tool.py": "raise SystemExit(2)\n",
        },
    )
    report = run_predicate(
        capsule,
        PredicateSpec(("python", "predicate.py"), timeout_seconds=2),
    )
    assert report.result is PredicateResult.REPRODUCES
    assert report.attempts[0].exit_code == 0


def test_timeout_output_limit_and_signal_are_invalid() -> None:
    sleeping = _capsule_with_script("import time\ntime.sleep(30)\n")
    started = time.monotonic()
    timed_out = run_predicate(
        sleeping,
        PredicateSpec(("python", "predicate.py"), timeout_seconds=0.2),
    )
    assert timed_out.result is PredicateResult.INVALID
    assert timed_out.attempts[0].reason == "timeout"
    assert time.monotonic() - started < 5

    noisy = _capsule_with_script("import sys\nsys.stdout.write('x' * 1000000)\nsys.stdout.flush()\n")
    limited = run_predicate(
        noisy,
        PredicateSpec(("python", "predicate.py"), timeout_seconds=2, output_limit_bytes=4096),
    )
    assert limited.result is PredicateResult.INVALID
    assert limited.attempts[0].reason == "output_limit"
    assert limited.attempts[0].output_bytes <= 8192

    if os.name != "nt":
        signaled = _capsule_with_script(
            "import os, signal\nos.kill(os.getpid(), signal.SIGTERM)\n"
        )
        report = run_predicate(
            signaled,
            PredicateSpec(("python", "predicate.py"), timeout_seconds=2),
        )
        assert report.result is PredicateResult.INVALID
        assert report.attempts[0].signal == signal.SIGTERM


def test_cancellation_stops_a_running_predicate() -> None:
    capsule = _capsule_with_script("import time\ntime.sleep(30)\n")
    cancelled = threading.Event()
    timer = threading.Timer(0.2, cancelled.set)
    timer.start()
    started = time.monotonic()
    try:
        report = run_predicate(
            capsule,
            PredicateSpec(("python", "predicate.py"), timeout_seconds=20),
            cancel_event=cancelled,
        )
    finally:
        timer.cancel()
    assert report.result is PredicateResult.INVALID
    assert report.attempts[0].reason == "cancelled"
    assert time.monotonic() - started < 5


def test_each_probabilistic_trial_is_fresh_and_all_attempts_are_recorded() -> None:
    capsule = _capsule_with_script(
        "import os, pathlib\n"
        "marker = pathlib.Path('.trial-marker')\n"
        "if marker.exists(): raise SystemExit(2)\n"
        "marker.write_text('x')\n"
        "trial = int(os.environ['RUNSIEVE_TRIAL'])\n"
        "raise SystemExit(0 if trial in {0, 2} else 1)\n"
    )
    spec = PredicateSpec(
        ("python", "predicate.py"),
        timeout_seconds=2,
        required_reproductions=2,
        trials=3,
    )
    report = run_predicate(capsule, spec)
    assert report.result is PredicateResult.REPRODUCES
    assert report.probabilistic is True
    assert [attempt.result for attempt in report.attempts] == [
        PredicateResult.REPRODUCES,
        PredicateResult.ABSENT,
        PredicateResult.REPRODUCES,
    ]
    assert len({attempt.workspace_id for attempt in report.attempts}) == 3


def test_offline_guard_removes_provider_keys_proxies_and_network() -> None:
    capsule = _capsule_with_script(
        "import os, sys\n"
        "for name in os.environ:\n"
        "    if name.startswith(('OPENAI_', 'ANTHROPIC_', 'AWS_SECRET')):\n"
        "        raise SystemExit(2)\n"
        "if any(os.environ.get(name) for name in "
        "('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY')):\n"
        "    raise SystemExit(2)\n"
        "try:\n"
        "    sys.audit('socket.connect', None)\n"
        "except PermissionError:\n"
        "    raise SystemExit(0)\n"
        "raise SystemExit(2)\n"
    )
    report = run_predicate(
        capsule,
        PredicateSpec(("python", "predicate.py"), timeout_seconds=2),
    )
    assert report.result is PredicateResult.REPRODUCES
    assert report.attempts[0].network_guard == "python-sitecustomize"


def test_offline_guard_rejects_socket_audit_events_without_opening_a_connection() -> None:
    capsule = _capsule_with_script(
        "import sys\n"
        "try:\n"
        "    sys.audit('socket.connect', None)\n"
        "except PermissionError:\n"
        "    raise SystemExit(0)\n"
        "raise SystemExit(1)\n"
    )
    report = run_predicate(
        capsule,
        PredicateSpec(("python", "predicate.py"), timeout_seconds=2),
    )
    assert report.result is PredicateResult.REPRODUCES


def test_offline_guard_blocks_host_files_and_child_processes(tmp_path: Path) -> None:
    host_file = tmp_path / "host-secret.txt"
    host_file.write_text("host secret", encoding="utf-8")
    capsule = _capsule_with_script(
        "import pathlib, subprocess, sys\n"
        f"host=pathlib.Path({str(host_file)!r})\n"
        "try:\n"
        "    host.read_text()\n"
        "except PermissionError:\n"
        "    pass\n"
        "else:\n"
        "    raise SystemExit(2)\n"
        "try:\n"
        "    subprocess.run([sys.executable, '-c', 'pass'])\n"
        "except PermissionError:\n"
        "    raise SystemExit(0)\n"
        "raise SystemExit(2)\n"
    )
    report = run_predicate(
        capsule,
        PredicateSpec(("python", "predicate.py"), timeout_seconds=2),
    )
    assert report.result is PredicateResult.REPRODUCES


def test_predicate_must_be_an_embedded_python_script() -> None:
    with pytest.raises(ValueError, match="embedded Python"):
        PredicateSpec(("sh", "-c", "exit 0"))
    with pytest.raises(ValueError, match="predicate script"):
        PredicateSpec(("python", "../../outside.py"))


def test_predicate_output_is_hashed_not_retained_and_cache_key_is_complete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canary = "PREDICATE-OUTPUT-CANARY"
    capsule = _capsule_with_script(f"print({canary!r})\nraise SystemExit(0)\n")
    report = run_predicate(
        capsule,
        PredicateSpec(("python", "predicate.py"), timeout_seconds=2),
    )
    assert canary not in repr(report)
    assert report.attempts[0].stdout_sha256

    spec = PredicateSpec(("python", "predicate.py"), timeout_seconds=2)
    first = predicate_cache_key(capsule, spec)
    assert first != predicate_cache_key(capsule, replace(spec, timeout_seconds=3))
    assert first != predicate_cache_key(capsule, replace(spec, output_limit_bytes=2048))
    assert first != predicate_cache_key(capsule, replace(spec, process_limit=2))
    assert first != predicate_cache_key(capsule, replace(spec, trials=3))
    assert first != predicate_cache_key(
        capsule,
        replace(spec, trials=3, required_reproductions=2),
    )
    assert first != predicate_cache_key(
        capsule,
        PredicateSpec(("python", "other.py"), timeout_seconds=2),
    )
    assert first != predicate_cache_key(
        replace(capsule, workspace={**capsule.workspace, "extra.txt": "value"}),
        spec,
    )
    assert first != predicate_cache_key(replace(capsule, environment={"OTHER": "1"}), spec)
