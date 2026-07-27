from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import tempfile
import warnings
import zipfile
from pathlib import Path

import pytest

from reprosieve.capsule import CapsuleLimits, capsule_bytes, load_capsule, write_capsule
from reprosieve.safeio import read_regular_file_bounded
from tests.helpers import rewrite_capsule_members, sample_capsule


def test_capsule_is_deterministic_validated_and_immutable(tmp_path: Path) -> None:
    capsule = sample_capsule()
    first = capsule_bytes(capsule, redaction_report={"replacements": 2})
    second = capsule_bytes(capsule, redaction_report={"replacements": 2})
    assert first == second
    assert hashlib.sha256(first).hexdigest() == hashlib.sha256(second).hexdigest()

    path = tmp_path / "source.reprosieve"
    info = write_capsule(capsule, path, redaction_report={"replacements": 2})
    assert info.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert load_capsule(path) == capsule
    with pytest.raises(FileExistsError):
        write_capsule(capsule, path)


def test_manifest_covers_every_payload_and_corruption_is_rejected(tmp_path: Path) -> None:
    data = capsule_bytes(sample_capsule())
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        names = set(archive.namelist()) - {"manifest.json"}
        assert set(manifest["entries"]) == names
        for name in names:
            payload = archive.read(name)
            assert manifest["entries"][name]["sha256"] == hashlib.sha256(payload).hexdigest()
            assert manifest["entries"][name]["size"] == len(payload)

    source = tmp_path / "source.reprosieve"
    source.write_bytes(data)
    corrupted = bytearray(data)
    corrupted[-30] ^= 0x01
    bad = tmp_path / "corrupt.reprosieve"
    bad.write_bytes(corrupted)
    with pytest.raises(ValueError, match="corrupt|hash|archive"):
        load_capsule(bad)


def test_manifest_covered_members_outside_the_public_schema_are_rejected(
    tmp_path: Path,
) -> None:
    source = tmp_path / "unknown-member.reprosieve"
    source.write_bytes(
        rewrite_capsule_members(
            capsule_bytes(sample_capsule()),
            {"unexpected/opaque.bin": b"manifest-covered but undefined"},
        )
    )

    with pytest.raises(ValueError, match="unsupported capsule member"):
        load_capsule(source)


@pytest.mark.parametrize("member", ["../escape", "/absolute", "C:/drive", "a/../../b"])
def test_archive_traversal_is_rejected(tmp_path: Path, member: str) -> None:
    path = tmp_path / "hostile.reprosieve"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(member, b"x")
    with pytest.raises(ValueError, match="unsafe archive member"):
        load_capsule(path)


def test_duplicate_symlink_bomb_and_oversize_archives_are_rejected(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.reprosieve"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(duplicate, "w") as archive:
            archive.writestr("events/v1.json", b"{}")
            archive.writestr("events/v1.json", b"{}")
    with pytest.raises(ValueError, match="duplicate"):
        load_capsule(duplicate)

    symlink = tmp_path / "symlink.reprosieve"
    info = zipfile.ZipInfo("workspace/link")
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(symlink, "w") as archive:
        archive.writestr(info, b"../../outside")
    with pytest.raises(ValueError, match="symlink"):
        load_capsule(symlink)

    bomb = tmp_path / "bomb.reprosieve"
    with zipfile.ZipFile(bomb, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("huge", b"0" * 50_000)
    with pytest.raises(ValueError, match="expansion|size"):
        load_capsule(bomb, limits=CapsuleLimits(max_member_bytes=100_000, max_ratio=5))

    source = tmp_path / "source.reprosieve"
    source.write_bytes(capsule_bytes(sample_capsule()))
    with pytest.raises(ValueError, match="archive size"):
        load_capsule(source, limits=CapsuleLimits(max_archive_bytes=10))


def test_oversized_capsule_is_rejected_before_path_read_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "oversized.reprosieve"
    source.write_bytes(b"x" * 4096)

    def forbidden_read_bytes(_path: Path) -> bytes:
        raise AssertionError("oversized capsule reached unbounded Path.read_bytes")

    monkeypatch.setattr(Path, "read_bytes", forbidden_read_bytes)
    with pytest.raises(ValueError, match="archive size"):
        load_capsule(source, limits=CapsuleLimits(max_archive_bytes=1))


def test_bounded_read_rejects_an_ancestor_swapped_during_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    declared_root = tmp_path / "declared"
    declared_root.mkdir()
    declared = declared_root / "fixture.txt"
    declared.write_text("safe", encoding="utf-8")
    host_root = tmp_path / "host"
    host_root.mkdir()
    (host_root / "fixture.txt").write_text("HOST-SECRET-CANARY", encoding="utf-8")
    moved_root = tmp_path / "moved"
    try:
        probe = tmp_path / "symlink-probe"
        probe.symlink_to(host_root, target_is_directory=True)
        probe.unlink()
    except OSError:
        pytest.skip("directory symlink creation is unavailable")

    original_open = os.open
    swapped = False

    def swap_before_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
    ) -> int:
        nonlocal swapped
        if not swapped and Path(path) == declared:
            swapped = True
            declared_root.rename(moved_root)
            declared_root.symlink_to(host_root, target_is_directory=True)
        return original_open(path, flags)

    monkeypatch.setattr(os, "open", swap_before_open)
    try:
        with pytest.raises(ValueError, match="changed while it was opened"):
            read_regular_file_bounded(
                declared,
                max_bytes=1024,
                label="declared workspace path",
            )
    finally:
        if declared_root.is_symlink():
            declared_root.unlink()
        if moved_root.exists():
            moved_root.rename(declared_root)


def test_canary_never_reaches_capsule_bytes_or_errors() -> None:
    canary = "CAPSULE-SECRET-CANARY"
    from reprosieve.redact import RedactionPolicy, redact_with_report

    raw = sample_capsule()
    metadata, report = redact_with_report(
        {"nested": canary, "authorization": f"Bearer {canary}"},
        policy=RedactionPolicy(salt=b"fixture", exact_canaries=(canary,)),
    )
    safe = type(raw)(
        schema_version=raw.schema_version,
        trace_id=raw.trace_id,
        events=raw.events,
        metadata=metadata,
        workspace=raw.workspace,
        environment=raw.environment,
    )
    data = capsule_bytes(safe, redaction_report=report.to_json())
    assert canary.encode() not in data


def test_capsule_paths_reject_symlink_ancestors(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    with pytest.raises(ValueError, match="symlink|junction"):
        write_capsule(sample_capsule(), linked / "escape.reprosieve")


def test_capsule_paths_reject_an_environment_selected_symlinked_temp_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from reprosieve import safeio

    temp_root = tmp_path / "system-temp"
    temp_root.mkdir()
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(temp_root))
    monkeypatch.setattr(
        safeio,
        "is_link_like",
        lambda path: path == temp_root,
    )

    with pytest.raises(ValueError, match="symlink|junction"):
        write_capsule(sample_capsule(), temp_root / "escape.reprosieve")
