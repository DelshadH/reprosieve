from pathlib import Path

from scripts.contract import canonical_json, sha256, verify_evidence_reference


def blob_reference(path: Path, *, relative_to: Path) -> dict[str, object]:
    source = path.resolve(strict=True)
    base = relative_to.resolve(strict=True)
    relative = source.relative_to(base).as_posix()
    data = source.read_bytes()
    return {"bytes": len(data), "path": relative, "sha256": sha256(data)}


def write_canonical_json(path: Path, value: object) -> None:
    path.write_bytes(canonical_json(value))


__all__ = [
    "blob_reference",
    "canonical_json",
    "sha256",
    "verify_evidence_reference",
    "write_canonical_json",
]
