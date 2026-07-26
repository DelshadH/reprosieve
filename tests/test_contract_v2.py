from __future__ import annotations

import copy
import hashlib
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.bootstrap import validate_bootstrap_contract, write_bootstrap_documents
from scripts.contract import (
    CONTRACT_V2_PREDECESSOR,
    CONTRACT_VERSION_PATH,
    CONTROL_PLANE_FILES,
    canonical_json,
    control_plane_bundle_identity,
    validate_contract_version,
    validate_evidence_window,
    validate_state_shape,
)
from scripts.contract_self_test import (
    all_pending_state,
    coherent_all_passed_state,
    must_reject,
    run_contract_self_tests,
)
from scripts.gates.RS_G12 import assert_evidence_files_tracked


class ContractV2Tests(unittest.TestCase):
    def test_bootstrap_writes_control_state_with_canonical_lf_bytes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="reprosieve-bootstrap-bytes-") as raw:
            root = Path(raw)
            (root / "PROGRESS.json").write_text(
                '{"updated_at":"1970-01-01T00:00:00Z"}\n',
                encoding="utf-8",
                newline="\n",
            )
            state = {
                "schema_version": 1,
                "project": "runsieve",
                "started_at": "2026-07-25T12:00:00Z",
            }
            write_bootstrap_documents(root, state)
            self.assertNotIn(b"\r", (root / ".agent-state.json").read_bytes())
            self.assertNotIn(b"\r", (root / "PROGRESS.json").read_bytes())

    def test_bootstrap_refuses_to_initialize_without_contract_v2_identity(self) -> None:
        with tempfile.TemporaryDirectory(prefix="reprosieve-bootstrap-test-") as raw:
            root = Path(raw)
            with self.assertRaisesRegex(ValueError, "CONTRACT_VERSION"):
                validate_bootstrap_contract(root)

    def test_control_bundle_lists_sorted_paths_and_hashes_exact_bytes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="reprosieve-bundle-test-") as raw:
            root = Path(raw)
            expected = hashlib.sha256()
            for relative in sorted(CONTROL_PLANE_FILES):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                if relative == CONTRACT_VERSION_PATH:
                    data = canonical_json(
                        {
                            "contract_version": 2,
                            "predecessor_root": CONTRACT_V2_PREDECESSOR,
                            "project": "runsieve",
                            "schema_version": 1,
                        }
                    )
                else:
                    data = f"{relative}\n".encode()
                target.write_bytes(data)
                expected.update(relative.encode())
                expected.update(b"\0")
                expected.update(data)
                expected.update(b"\0")
            bundle = control_plane_bundle_identity(root)
            self.assertEqual(bundle["aggregate_sha256"], expected.hexdigest())
            self.assertEqual(
                [entry["path"] for entry in bundle["files"]],
                sorted(CONTROL_PLANE_FILES),
            )
            self.assertEqual(
                set(bundle),
                {
                    "aggregate_algorithm",
                    "aggregate_sha256",
                    "contract_version",
                    "files",
                    "predecessor_root",
                    "project",
                    "schema_version",
                },
            )

    def test_contract_identity_is_exact_and_rejects_unknown_fields(self) -> None:
        identity = {
            "contract_version": 2,
            "predecessor_root": CONTRACT_V2_PREDECESSOR,
            "project": "runsieve",
            "schema_version": 1,
        }
        self.assertEqual(validate_contract_version(identity), identity)
        extra = {**identity, "unexpected": True}
        with self.assertRaisesRegex(ValueError, "keys"):
            validate_contract_version(extra)

    def test_explicit_pending_and_coherent_passed_states_are_valid(self) -> None:
        pending = all_pending_state()
        passed = coherent_all_passed_state()
        validate_state_shape(**pending)
        validate_state_shape(**passed)
        self.assertTrue(all(value["status"] == "pending" for value in pending["progress"]["tasks"].values()))
        self.assertTrue(all(value["status"] == "passed" for value in passed["progress"]["gates"].values()))

    def test_rejection_helper_refuses_a_no_op_mutation(self) -> None:
        with self.assertRaisesRegex(AssertionError, "no change"):
            must_reject("no-op", all_pending_state(), lambda state: None)

    def test_complete_self_test_accepts_a_live_all_passed_state(self) -> None:
        run_contract_self_tests(coherent_all_passed_state()["progress"])

    def test_evidence_window_rejects_prebootstrap_and_future_proof_times(self) -> None:
        bootstrap = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
        now = bootstrap + timedelta(hours=1)
        validate_evidence_window(
            bootstrap=bootstrap,
            proof_started=bootstrap,
            proof_finished=bootstrap + timedelta(minutes=1),
            deadline_hour=2,
            now=now,
            label="RS-G01",
        )
        with self.assertRaisesRegex(ValueError, "predates"):
            validate_evidence_window(
                bootstrap=bootstrap,
                proof_started=bootstrap - timedelta(microseconds=1),
                proof_finished=bootstrap,
                deadline_hour=2,
                now=now,
                label="RS-G01",
            )
        with self.assertRaisesRegex(ValueError, "future"):
            validate_evidence_window(
                bootstrap=bootstrap,
                proof_started=bootstrap,
                proof_finished=now + timedelta(minutes=6),
                deadline_hour=2,
                now=now,
                label="RS-G01",
            )

    def test_duplicate_evidence_reference_is_rejected(self) -> None:
        state = coherent_all_passed_state()
        duplicate = copy.deepcopy(state["progress"]["gates"]["RS-G01"]["evidence"][0])
        state["progress"]["gates"]["RS-G01"]["evidence"].append(duplicate)
        with self.assertRaisesRegex(ValueError, "duplicate evidence"):
            validate_state_shape(**state)

    def test_release_evidence_rejects_ignored_untracked_artifacts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="reprosieve-tracked-evidence-") as raw:
            root = Path(raw)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            evidence = root / ".evidence" / "RS-G10" / "run"
            evidence.mkdir(parents=True)
            manifest_path = evidence / "manifest.json"
            stream = evidence / "command.stdout"
            capsule = evidence / "capsule.reprosieve"
            verifier = root / "scripts" / "gates" / "RS_G10.py"
            verifier.parent.mkdir(parents=True)
            for path in (manifest_path, stream, capsule, verifier):
                path.write_bytes(b"evidence\n")
            (root / ".gitignore").write_text("*.reprosieve\n", encoding="utf-8")
            subprocess.run(
                [
                    "git",
                    "add",
                    ".gitignore",
                    manifest_path.relative_to(root),
                    stream.relative_to(root),
                    verifier.relative_to(root),
                ],
                cwd=root,
                check=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=ReproSieve Test",
                    "-c",
                    "user.email=reprosieve@example.invalid",
                    "commit",
                    "-qm",
                    "tracked evidence fixture",
                ],
                cwd=root,
                check=True,
            )
            manifest = {
                "artifacts": [{"path": "capsule.reprosieve"}],
                "commands": [
                    {
                        "stderr": {"path": "command.stdout"},
                        "stdout": {"path": "command.stdout"},
                    }
                ],
                "verifier": {"path": "scripts/gates/RS_G10.py"},
            }

            with self.assertRaisesRegex(ValueError, "not Git-tracked"):
                assert_evidence_files_tracked(
                    root=root,
                    gate="RS-G10",
                    manifest_path=manifest_path,
                    manifest=manifest,
                )

            subprocess.run(
                ["git", "add", "-f", capsule.relative_to(root)],
                cwd=root,
                check=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=ReproSieve Test",
                    "-c",
                    "user.email=reprosieve@example.invalid",
                    "commit",
                    "-qm",
                    "track capsule",
                ],
                cwd=root,
                check=True,
            )
            assert_evidence_files_tracked(
                root=root,
                gate="RS-G10",
                manifest_path=manifest_path,
                manifest=manifest,
            )


if __name__ == "__main__":
    unittest.main()
