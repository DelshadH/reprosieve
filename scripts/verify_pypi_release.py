from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SHA256 = re.compile(r"^[0-9a-f]{64}$")
PROJECT = re.compile(r"^[A-Za-z0-9._-]+$")
VERSION = re.compile(r"^[A-Za-z0-9.!+_-]+$")


def read_checksums(path: Path) -> dict[str, str]:
    expected: dict[str, str] = {}
    for line in path.read_text(encoding="ascii").splitlines():
        parts = line.split()
        if len(parts) != 2 or SHA256.fullmatch(parts[0]) is None:
            raise ValueError("checksum manifest is invalid")
        name = parts[1]
        if Path(name).name != name or name in expected:
            raise ValueError("checksum filename inventory is invalid")
        expected[name] = parts[0]
    if len(expected) != 2:
        raise ValueError("checksum manifest must contain exactly two distributions")
    return expected


def validate_release_payload(
    payload: object,
    *,
    project: str,
    version: str,
    expected: dict[str, str],
) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise ValueError("PyPI release payload is invalid")
    info = payload.get("info")
    urls = payload.get("urls")
    if (
        not isinstance(info, dict)
        or info.get("name") != project
        or info.get("version") != version
        or not isinstance(urls, list)
    ):
        raise ValueError("PyPI release identity is invalid")
    actual: dict[str, str] = {}
    for item in urls:
        if not isinstance(item, dict):
            raise ValueError("PyPI distribution inventory is invalid")
        name = item.get("filename")
        digests = item.get("digests")
        digest = digests.get("sha256") if isinstance(digests, dict) else None
        if (
            not isinstance(name, str)
            or Path(name).name != name
            or name in actual
            or not isinstance(digest, str)
            or SHA256.fullmatch(digest) is None
        ):
            raise ValueError("PyPI distribution inventory is invalid")
        actual[name] = digest
    if set(actual) != set(expected):
        raise ValueError("PyPI distribution inventory does not match candidate")
    if actual != expected:
        raise ValueError("PyPI distribution hashes do not match candidate")
    return actual


def _fetch_release(project: str, version: str) -> object | None:
    project_path = urllib.parse.quote(project, safe="")
    version_path = urllib.parse.quote(version, safe="")
    request = urllib.request.Request(
        f"https://pypi.org/pypi/{project_path}/{version_path}/json",
        headers={"Accept": "application/json", "User-Agent": "reprosieve-release/1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if response.status != 200:
                raise ValueError("PyPI returned an unexpected status")
            payload: object = json.loads(response.read())
            return payload
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise ValueError(f"PyPI query failed with HTTP {error.code}") from error
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ValueError("PyPI release query failed") from error


def verify_registry_state(
    *,
    project: str,
    version: str,
    expected: dict[str, str],
    require_existing: bool,
    wait_seconds: int,
) -> str:
    deadline = time.monotonic() + wait_seconds
    while True:
        payload = _fetch_release(project, version)
        if payload is not None:
            validate_release_payload(
                payload,
                project=project,
                version=version,
                expected=expected,
            )
            return "identical"
        if not require_existing:
            return "absent"
        if time.monotonic() >= deadline:
            raise ValueError("PyPI release did not become visible before timeout")
        time.sleep(min(5, max(0.1, deadline - time.monotonic())))


def _write_outputs(path: Path | None, *, status: str) -> None:
    publish_required = "true" if status == "absent" else "false"
    output = f"registry_status={status}\npublish_required={publish_required}\n"
    if path is None:
        sys.stdout.write(output)
    else:
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--checksums", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-existing", action="store_true")
    parser.add_argument("--wait-seconds", type=int, default=0)
    args = parser.parse_args(argv)
    if (
        PROJECT.fullmatch(args.project) is None
        or VERSION.fullmatch(args.version) is None
        or args.wait_seconds < 0
        or args.wait_seconds > 300
    ):
        print("PyPI release verifier arguments are invalid", file=sys.stderr)
        return 2
    try:
        expected = read_checksums(args.checksums)
        status = verify_registry_state(
            project=args.project,
            version=args.version,
            expected=expected,
            require_existing=args.require_existing,
            wait_seconds=args.wait_seconds,
        )
        _write_outputs(args.output, status=status)
    except (OSError, ValueError) as error:
        print(f"PyPI release verification failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
