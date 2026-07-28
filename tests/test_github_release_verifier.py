from __future__ import annotations

import pytest

from scripts.verify_github_release import validate_releases_payload

EXPECTED = {
    "SHA256SUMS": "a" * 64,
    "reprosieve-0.1.0a2-py3-none-any.whl": "b" * 64,
}


def _release(*, assets: list[dict[str, object]]) -> dict[str, object]:
    return {
        "draft": False,
        "name": "ReproSieve 0.1.0a2",
        "prerelease": True,
        "tag_name": "v0.1.0a2",
        "assets": assets,
    }


def test_existing_github_release_accepts_exact_assets() -> None:
    release = _release(
        assets=[
            {"name": name, "digest": f"sha256:{digest}", "state": "uploaded"}
            for name, digest in EXPECTED.items()
        ]
    )
    state, missing = validate_releases_payload(
        [release],
        tag="v0.1.0a2",
        title="ReproSieve 0.1.0a2",
        expected=EXPECTED,
        allow_absent=False,
        require_complete=True,
        require_published=True,
    )
    assert state == "published"
    assert missing == []


def test_partial_release_returns_only_missing_assets() -> None:
    release = _release(
        assets=[
            {
                "name": "SHA256SUMS",
                "digest": f"sha256:{'a' * 64}",
                "state": "uploaded",
            }
        ]
    )
    state, missing = validate_releases_payload(
        [release],
        tag="v0.1.0a2",
        title="ReproSieve 0.1.0a2",
        expected=EXPECTED,
        allow_absent=False,
        require_complete=False,
        require_published=False,
    )
    assert state == "published"
    assert missing == ["reprosieve-0.1.0a2-py3-none-any.whl"]


def test_github_release_rejects_conflicting_assets() -> None:
    release = _release(
        assets=[
            {"name": "SHA256SUMS", "digest": f"sha256:{'c' * 64}", "state": "uploaded"}
        ]
    )
    with pytest.raises(ValueError, match="hashes"):
        validate_releases_payload(
            [release],
            tag="v0.1.0a2",
            title="ReproSieve 0.1.0a2",
            expected=EXPECTED,
            allow_absent=False,
            require_complete=False,
            require_published=False,
        )
