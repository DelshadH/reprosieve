from __future__ import annotations

import pytest

from scripts.verify_pypi_release import validate_release_payload

EXPECTED = {
    "reprosieve-0.1.0a2-py3-none-any.whl": "a" * 64,
    "reprosieve-0.1.0a2.tar.gz": "b" * 64,
}


def _payload(*, wheel_hash: str = "a" * 64) -> dict[str, object]:
    return {
        "info": {"name": "reprosieve", "version": "0.1.0a2"},
        "urls": [
            {
                "filename": "reprosieve-0.1.0a2-py3-none-any.whl",
                "digests": {"sha256": wheel_hash},
            },
            {
                "filename": "reprosieve-0.1.0a2.tar.gz",
                "digests": {"sha256": "b" * 64},
            },
        ],
    }


def test_registry_payload_must_match_every_expected_distribution() -> None:
    assert validate_release_payload(
        _payload(),
        project="reprosieve",
        version="0.1.0a2",
        expected=EXPECTED,
    ) == EXPECTED


def test_registry_payload_rejects_a_hash_mismatch() -> None:
    with pytest.raises(ValueError, match="hashes"):
        validate_release_payload(
            _payload(wheel_hash="c" * 64),
            project="reprosieve",
            version="0.1.0a2",
            expected=EXPECTED,
        )


def test_registry_payload_rejects_missing_or_extra_distributions() -> None:
    payload = _payload()
    urls = payload["urls"]
    assert isinstance(urls, list)
    urls.pop()
    with pytest.raises(ValueError, match="inventory"):
        validate_release_payload(
            payload,
            project="reprosieve",
            version="0.1.0a2",
            expected=EXPECTED,
        )
