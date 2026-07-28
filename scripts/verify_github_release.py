from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

SHA256 = re.compile(r"^[0-9a-f]{64}$")
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def candidate_assets(directory: Path) -> dict[str, str]:
    wheels = tuple(directory.glob("reprosieve-*.whl"))
    sdists = tuple(directory.glob("reprosieve-*.tar.gz"))
    required = (directory / "SHA256SUMS", directory / "reprosieve.spdx.json")
    if (
        len(wheels) != 1
        or len(sdists) != 1
        or any(not path.is_file() or path.is_symlink() for path in required)
    ):
        raise ValueError("GitHub release candidate inventory is invalid")
    paths = (*wheels, *sdists, *required)
    if any(not path.is_file() or path.is_symlink() for path in paths):
        raise ValueError("GitHub release candidate contains an invalid asset")
    return {path.name: _sha256(path) for path in paths}


def validate_releases_payload(
    payload: object,
    *,
    tag: str,
    title: str,
    expected: dict[str, str],
    allow_absent: bool,
    require_complete: bool,
    require_published: bool,
) -> tuple[str, list[str]]:
    if not isinstance(payload, list):
        raise ValueError("GitHub releases payload is invalid")
    matches = [
        release
        for release in payload
        if isinstance(release, dict) and release.get("tag_name") == tag
    ]
    if not matches:
        if allow_absent:
            return "absent", sorted(expected)
        raise ValueError("GitHub release is absent")
    if len(matches) != 1:
        raise ValueError("GitHub release identity is ambiguous")
    release = matches[0]
    if (
        release.get("name") != title
        or release.get("prerelease") is not True
        or not isinstance(release.get("draft"), bool)
        or not isinstance(release.get("assets"), list)
    ):
        raise ValueError("GitHub release metadata does not match candidate")
    draft = release["draft"]
    if require_published and draft:
        raise ValueError("GitHub release is still a draft")
    actual: dict[str, str] = {}
    assets = release["assets"]
    assert isinstance(assets, list)
    for asset in assets:
        if not isinstance(asset, dict):
            raise ValueError("GitHub release asset inventory is invalid")
        name = asset.get("name")
        digest = asset.get("digest")
        if (
            not isinstance(name, str)
            or Path(name).name != name
            or name in actual
            or name not in expected
            or asset.get("state") != "uploaded"
            or not isinstance(digest, str)
            or not digest.startswith("sha256:")
            or SHA256.fullmatch(digest.removeprefix("sha256:")) is None
        ):
            raise ValueError("GitHub release asset inventory is invalid")
        actual[name] = digest.removeprefix("sha256:")
    if any(actual[name] != expected[name] for name in actual):
        raise ValueError("GitHub release asset hashes do not match candidate")
    missing = sorted(set(expected) - set(actual))
    if require_complete and missing:
        raise ValueError("GitHub release asset inventory is incomplete")
    return ("draft" if draft else "published"), missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--releases-json", type=Path, required=True)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--state-output", type=Path, required=True)
    parser.add_argument("--missing-output", type=Path, required=True)
    parser.add_argument("--allow-absent", action="store_true")
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--require-published", action="store_true")
    args = parser.parse_args(argv)
    if (
        REPOSITORY.fullmatch(args.repo) is None
        or not args.tag.startswith("v")
        or not args.title
    ):
        print("GitHub release verifier arguments are invalid", file=sys.stderr)
        return 2
    try:
        payload: object = json.loads(args.releases_json.read_bytes())
        expected = candidate_assets(args.candidate_dir)
        state, missing = validate_releases_payload(
            payload,
            tag=args.tag,
            title=args.title,
            expected=expected,
            allow_absent=args.allow_absent,
            require_complete=args.require_complete,
            require_published=args.require_published,
        )
        args.state_output.write_text(state + "\n", encoding="ascii")
        missing_paths = "".join(
            f"{args.candidate_dir / name}\n" for name in missing
        )
        args.missing_output.write_text(missing_paths, encoding="utf-8", newline="\n")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"GitHub release verification failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
