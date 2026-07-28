from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import evidence


def test_gate_verifier_rejects_an_identity_only_manifest(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"gate":"RS-G07"}\n', encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, "-m", "scripts.gates.RS_G07", str(manifest)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert completed.returncode == 2
    assert "measured evidence" in completed.stderr


def test_pytest_evidence_rejects_plausible_workflow_text_without_execution(
    tmp_path: Path,
) -> None:
    support = importlib.import_module("scripts.gates._verify")
    require_pytest_pass = getattr(support, "require_pytest_pass", None)
    assert callable(require_pytest_pass)
    stdout = tmp_path / "command-00.stdout"
    stderr = tmp_path / "command-00.stderr"
    stdout.write_bytes(b"macos-latest\nall configured assertions: true\n")
    stderr.write_bytes(b"")
    manifest = {
        "commands": [
            {
                "stdout": evidence.blob_reference(stdout, relative_to=tmp_path),
                "stderr": evidence.blob_reference(stderr, relative_to=tmp_path),
            }
        ]
    }

    with pytest.raises(ValueError, match="no clean passing result"):
        require_pytest_pass(manifest, tmp_path, 0)


def test_every_gate_maps_each_registered_assertion_to_a_specific_measurement() -> None:
    registry = json.loads(Path("GATE_REGISTRY.json").read_text(encoding="utf-8"))
    for registered in registry["gates"]:
        module = importlib.import_module(
            f"scripts.gates.{registered['id'].replace('-', '_')}"
        )
        spec = getattr(module, "SPEC", None)
        assert spec is not None, registered["id"]
        assert spec.extra_validator is not None, registered["id"]
        measured = [
            assertion
            for measurement in spec.measurements
            for assertion in measurement.assertions
        ]
        assert sorted(measured) == sorted(registered["required_assertions"])
        assert len(measured) == len(set(measured))


def test_rs_g10_portable_proof_requires_measured_platform_execution() -> None:
    module = importlib.import_module("scripts.gates.RS_G10")
    validate = getattr(module, "validate_portable_proof", None)
    assert callable(validate)
    commit = "b" * 40
    proof = {
        "schema_version": 1,
        "gate": "RS-G10",
        "commit": commit,
        "collector": {
            "path": "scripts/portable_reproduction_proof.py",
            "sha256": "e" * 64,
        },
        "runner": {"os": "macos", "arch": "arm64"},
        "fresh_temporary_directory": True,
        "source_tree_present": False,
        "provider_keys_present": [],
        "command": {
            "argv": ["python", "reproduce.py", "--trust-embedded-predicate"],
            "exit_code": 0,
            "output_limit_bytes": 65536,
            "stdout": {"bytes": 35, "sha256": "a" * 64},
            "stderr": {"bytes": 0, "sha256": "b" * 64},
        },
        "export": {
            "capsule_sha256": "c" * 64,
            "reproducer_sha256": "d" * 64,
        },
    }

    assert validate(proof, expected_os="macos", expected_commit=commit) == {
        "fresh-temp-run",
        "macos-one-command",
        "no-api-key",
        "no-source-repository",
    }
    for field, value in (
        ("fresh_temporary_directory", False),
        ("source_tree_present", True),
        ("provider_keys_present", ["OPENAI_API_KEY"]),
    ):
        invalid = {**proof, field: value}
        with pytest.raises(ValueError):
            validate(invalid, expected_os="macos", expected_commit=commit)
    failed = {
        **proof,
        "command": {**proof["command"], "exit_code": 1},
    }
    with pytest.raises(ValueError):
        validate(failed, expected_os="macos", expected_commit=commit)


def test_rs_g01_scans_the_committed_adapter_for_private_sdk_imports() -> None:
    module = importlib.import_module("scripts.gates.RS_G01")
    scan = getattr(module, "scan_sdk_imports", None)
    assert callable(scan)
    adapter = Path("src/reprosieve/adapters/openai_agents.py").read_bytes()
    assert scan(adapter) == ()
    assert scan(b"from agents._internal import exporter\n") == ("agents._internal",)


def test_minimality_oracle_rejects_a_missing_final_unit_attempt() -> None:
    module = importlib.import_module("scripts.minimality_oracle_proof")
    proof = module.build_proof()
    incomplete = {
        **proof,
        "attempted_units": proof["attempted_units"][:-1],
        "exact_unit_coverage": True,
    }
    with pytest.raises(ValueError, match="exact one-unit coverage"):
        module.validate_oracle_document(incomplete)


def test_rs_g13_requires_real_clean_install_proof_for_each_python() -> None:
    module = importlib.import_module("scripts.gates.RS_G13")
    validate = getattr(module, "validate_package_proof", None)
    assert callable(validate)
    commit = "c" * 40
    wheel = "reprosieve-0.1.0a4-py3-none-any.whl"
    sdist = "reprosieve-0.1.0a4.tar.gz"
    core_flows = [
        "help",
        "demo",
        "materialize",
        "reproduce-predicate",
        "reduce",
        "verify-minimal",
        "export",
        "exported-reproduce",
    ]
    proof = {
        "schema_version": 1,
        "gate": "RS-G13",
        "commit": commit,
        "collector": {
            "path": "scripts/package_matrix_proof.py",
            "sha256": "d" * 64,
        },
        "runner": {"os": "linux", "arch": "x64", "python": "3.11.15"},
        "fresh_checkout": True,
        "clean_install_directory": True,
        "source_tree_present": False,
        "commands": [
            {
                "argv": ["python", "-m", "build"],
                "exit_code": 0,
                "stdout": {"bytes": 10, "sha256": "1" * 64},
                "stderr": {"bytes": 0, "sha256": "2" * 64},
            },
            {
                "argv": ["python", "-m", "build"],
                "exit_code": 0,
                "stdout": {"bytes": 10, "sha256": "1" * 64},
                "stderr": {"bytes": 0, "sha256": "2" * 64},
            },
            {
                "argv": [
                    "python", "scripts/installed_cli_smoke.py",
                    "--distribution", wheel,
                ],
                "exit_code": 0,
                "stdout": {"bytes": 10, "sha256": "3" * 64},
                "stderr": {"bytes": 0, "sha256": "4" * 64},
            },
            {
                "argv": [
                    "python", "scripts/installed_cli_smoke.py",
                    "--distribution", sdist,
                ],
                "exit_code": 0,
                "stdout": {"bytes": 10, "sha256": "5" * 64},
                "stderr": {"bytes": 0, "sha256": "6" * 64},
            },
            {
                "argv": [
                    "python", "scripts/installed_cli_smoke.py",
                    "--distribution", wheel, "--with-openai",
                ],
                "exit_code": 0,
                "stdout": {"bytes": 100, "sha256": "7" * 64},
                "stderr": {"bytes": 0, "sha256": "8" * 64},
            },
        ],
        "artifacts": {
            "rebuild_wheel": {
                "bytes": 1000,
                "name": f"rebuild-{wheel}",
                "sha256": "9" * 64,
            },
            "rebuild_sdist": {
                "bytes": 1100,
                "name": f"rebuild-{sdist}",
                "sha256": "a" * 64,
            },
            "wheel": {"bytes": 1000, "name": wheel, "sha256": "9" * 64},
            "sdist": {
                "bytes": 1100,
                "name": sdist,
                "sha256": "a" * 64,
            },
        },
        "members": {
            "sdist": [
                "reprosieve-0.1.0a4/README.md",
                "reprosieve-0.1.0a4/pyproject.toml",
                "reprosieve-0.1.0a4/src/reprosieve/__init__.py",
            ],
            "wheel": [
                "reprosieve-0.1.0a4.dist-info/METADATA",
                "reprosieve/__init__.py",
            ],
        },
        "installed_flows": {
            "sdist_core": core_flows,
            "wheel_core": core_flows,
            "wheel_openai": [*core_flows, "capture"],
        },
        "reproducible_artifacts": True,
        "semantic_checks": {
            "core_dependencies_empty": True,
            "entry_point": True,
            "extras": ["dev", "openai"],
            "name": "reprosieve",
            "python_requires": "<3.14,>=3.11",
            "schema_names": [
                "capsule-v1.schema.json",
                "case-study-v1.schema.json",
                "materialization-v1.schema.json",
                "predicate-report-v1.schema.json",
                "reduction-report-v1.schema.json",
            ],
            "sdist_schema_parity": True,
            "version": "0.1.0a4",
            "wheel_schema_parity": True,
        },
        "source_date_epoch": "1753460000",
        "supply_chain": {
            "checksums": {
                "bytes": 200,
                "name": "SHA256SUMS",
                "sha256": "c" * 64,
            },
            "sbom": {
                "bytes": 500,
                "name": "reprosieve.spdx.json",
                "sha256": "e" * 64,
            },
        },
    }

    assert validate(
        proof,
        expected_python="3.11",
        expected_commit=commit,
    ) == {
        "clean-install-py311",
        "wheel-sdist-smoke",
        "cli-smoke",
    }
    for field, value in (
        ("fresh_checkout", False),
        ("clean_install_directory", False),
        ("source_tree_present", True),
    ):
        with pytest.raises(ValueError):
            validate(
                {**proof, field: value},
                expected_python="3.11",
                expected_commit=commit,
            )
    failed = {
        **proof,
        "commands": [
            *proof["commands"][:4],
            {**proof["commands"][4], "exit_code": 1},
        ],
    }
    with pytest.raises(ValueError):
        validate(failed, expected_python="3.11", expected_commit=commit)
    with pytest.raises(ValueError):
        validate(
            {**proof, "reproducible_artifacts": False},
            expected_python="3.11",
            expected_commit=commit,
        )
    divergent = {
        **proof,
        "artifacts": {
            **proof["artifacts"],
            "rebuild_wheel": {
                **proof["artifacts"]["rebuild_wheel"],
                "sha256": "b" * 64,
            },
        },
    }
    with pytest.raises(ValueError):
        validate(divergent, expected_python="3.11", expected_commit=commit)
    leaking = {
        **proof,
        "members": {
            **proof["members"],
            "sdist": [
                *proof["members"]["sdist"],
                "reprosieve-0.1.0a4/.evidence/RS-G13/proof.json",
            ],
        },
    }
    with pytest.raises(ValueError):
        validate(leaking, expected_python="3.11", expected_commit=commit)


def test_rs_g12_requires_full_verification_and_structured_demo_output() -> None:
    module = importlib.import_module("scripts.gates.RS_G12")
    validate = getattr(module, "validate_release_outputs", None)
    assert callable(validate)
    verification = (
        b"RunSieve contract-v2 self-tests passed\n"
        b"92 passed, 2 subtests passed in 40.00s\n"
        b"All checks passed!\n"
        b"Success: no issues found in 16 source files\n"
    )
    demo = (
        b"reduced 247 events to 5; 1-minimal; 52 predicate calls\n"
        b"wrote deterministic recorded-output materialization\n"
        b'{"result":"reproduces"}\n'
        b"exported one-command offline issue reproduction\n"
        b"killer demo passed in 12.454s\n"
    )

    assert validate(verification, demo) == {
        "clean-checkout",
        "full-tests",
        "killer-reduce",
        "recorded-values-materialize",
        "predicate-reproduce",
        "repro-export",
        "minimality-verify",
        "terminal-demo-duration",
    }
    with pytest.raises(ValueError):
        validate(b"All checks passed!\n", demo)
    with pytest.raises(ValueError):
        validate(verification, demo.replace(b"12.454s", b"20.001s"))


def test_evidence_generator_consumes_three_distinct_package_proofs(
    tmp_path: Path,
) -> None:
    generator = importlib.import_module("scripts.generate_gate_evidence")
    package_inputs = getattr(generator, "_package_inputs", None)
    assert callable(package_inputs)
    gate = importlib.import_module("scripts.gates.RS_G13").SPEC
    commit = "d" * 40
    inputs: list[Path] = []
    for minor in ("3.11", "3.12", "3.13"):
        source = tmp_path / f"input-{minor}"
        source.mkdir()
        wheel = "reprosieve-0.1.0a4-py3-none-any.whl"
        sdist = "reprosieve-0.1.0a4.tar.gz"
        rebuilt_wheel = f"rebuild-{wheel}"
        rebuilt_sdist = f"rebuild-{sdist}"
        commands = []
        argvs = (
            ["python", "-m", "build"],
            ["python", "-m", "build"],
            ["python", "scripts/installed_cli_smoke.py", "--distribution", wheel],
            ["python", "scripts/installed_cli_smoke.py", "--distribution", sdist],
            [
                "python", "scripts/installed_cli_smoke.py",
                "--distribution", wheel, "--with-openai",
            ],
        )
        for index, argv in enumerate(argvs):
            stdout = b'{"flows":["passed"]}\n' if index >= 2 else b"passed\n"
            stderr = b""
            (source / f"command-{index:02d}.stdout").write_bytes(stdout)
            (source / f"command-{index:02d}.stderr").write_bytes(stderr)
            commands.append(
                {
                    "argv": argv,
                    "exit_code": 0,
                    "stdout": {
                        "bytes": len(stdout),
                        "sha256": hashlib.sha256(stdout).hexdigest(),
                    },
                    "stderr": {
                        "bytes": 0,
                        "sha256": hashlib.sha256(stderr).hexdigest(),
                    },
                }
            )
        (source / wheel).write_bytes(b"wheel")
        (source / sdist).write_bytes(b"sdist")
        (source / rebuilt_wheel).write_bytes(b"wheel")
        (source / rebuilt_sdist).write_bytes(b"sdist")
        (source / "SHA256SUMS").write_bytes(b"checksums")
        (source / "reprosieve.spdx.json").write_bytes(b"sbom")
        core_flows = [
            "help",
            "demo",
            "materialize",
            "reproduce-predicate",
            "reduce",
            "verify-minimal",
            "export",
            "exported-reproduce",
        ]
        proof = {
            "schema_version": 1,
            "gate": "RS-G13",
            "commit": commit,
            "collector": {
                "path": "scripts/package_matrix_proof.py",
                "sha256": "e" * 64,
            },
            "runner": {"os": "linux", "arch": "x64", "python": f"{minor}.9"},
            "fresh_checkout": True,
            "clean_install_directory": True,
            "source_tree_present": False,
            "commands": commands,
            "artifacts": {
                "rebuild_wheel": {
                    "bytes": 5,
                    "name": rebuilt_wheel,
                    "sha256": hashlib.sha256(b"wheel").hexdigest(),
                },
                "rebuild_sdist": {
                    "bytes": 5,
                    "name": rebuilt_sdist,
                    "sha256": hashlib.sha256(b"sdist").hexdigest(),
                },
                "wheel": {
                    "bytes": 5,
                    "name": wheel,
                    "sha256": hashlib.sha256(b"wheel").hexdigest(),
                },
                "sdist": {
                    "bytes": 5,
                    "name": sdist,
                    "sha256": hashlib.sha256(b"sdist").hexdigest(),
                },
            },
            "members": {
                "sdist": [
                    "reprosieve-0.1.0a4/README.md",
                    "reprosieve-0.1.0a4/pyproject.toml",
                ],
                "wheel": [
                    "reprosieve-0.1.0a4.dist-info/METADATA",
                    "reprosieve/__init__.py",
                ],
            },
            "installed_flows": {
                "sdist_core": core_flows,
                "wheel_core": core_flows,
                "wheel_openai": [*core_flows, "capture"],
            },
            "reproducible_artifacts": True,
            "semantic_checks": {
                "core_dependencies_empty": True,
                "entry_point": True,
                "extras": ["dev", "openai"],
                "name": "reprosieve",
                "python_requires": "<3.14,>=3.11",
                "schema_names": [
                    "capsule-v1.schema.json",
                    "case-study-v1.schema.json",
                    "materialization-v1.schema.json",
                    "predicate-report-v1.schema.json",
                    "reduction-report-v1.schema.json",
                ],
                "sdist_schema_parity": True,
                "version": "0.1.0a4",
                "wheel_schema_parity": True,
            },
            "source_date_epoch": "1753460000",
            "supply_chain": {
                "checksums": {
                    "bytes": 9,
                    "name": "SHA256SUMS",
                    "sha256": hashlib.sha256(b"checksums").hexdigest(),
                },
                "sbom": {
                    "bytes": 4,
                    "name": "reprosieve.spdx.json",
                    "sha256": hashlib.sha256(b"sbom").hexdigest(),
                },
            },
        }
        (source / "proof.json").write_text(json.dumps(proof), encoding="utf-8")
        inputs.append(source)
    destination = tmp_path / "evidence"
    destination.mkdir()

    commands, artifacts = package_inputs(
        gate,
        commit=commit,
        directory=destination,
        proof_inputs=tuple(inputs),
    )

    assert len(commands) == 3
    assert len(artifacts) == 45
    assert {
        path.name for path in destination.iterdir()
    } == {"package-py311", "package-py312", "package-py313"}


def test_evidence_helpers_write_canonical_hashed_references(tmp_path: Path) -> None:
    blob_reference = getattr(evidence, "blob_reference", None)
    write_canonical_json = getattr(evidence, "write_canonical_json", None)
    assert callable(blob_reference)
    assert callable(write_canonical_json)

    artifact = tmp_path / "artifact.txt"
    artifact.write_bytes(b"proof\n")
    assert blob_reference(artifact, relative_to=tmp_path) == {
        "bytes": 6,
        "path": "artifact.txt",
        "sha256": "f6ed42a9d765eeb230a069bbc3d5dc346b2669594bb0b83cc6d14d5d967b8961",
    }

    manifest = tmp_path / "manifest.json"
    write_canonical_json(manifest, {"z": 1, "a": True})
    assert manifest.read_bytes() == b'{"a":true,"z":1}\n'


def test_evidence_generator_builds_the_exact_manifest_shape() -> None:
    spec = importlib.util.find_spec("scripts.generate_gate_evidence")
    assert spec is not None
    module = importlib.import_module("scripts.generate_gate_evidence")
    build_manifest = getattr(module, "build_manifest", None)
    assert callable(build_manifest)

    reference = {"bytes": 6, "path": "proof.json", "sha256": "a" * 64}
    manifest = build_manifest(
        gate="RS-G07",
        commit="b" * 40,
        started_at="2026-07-25T07:00:00Z",
        finished_at="2026-07-25T07:00:01Z",
        environment={"python": "3.13.1", "os": "test"},
        assertions=("reproduces-distinct",),
        command={
            "argv": ["python", "-m", "scripts.gates.RS_G07"],
            "exit_code": 0,
            "stdout": reference,
            "stderr": reference,
        },
        artifacts=(reference,),
        verifier={
            "argv": ["python", "-m", "scripts.gates.RS_G07"],
            "bytes": 10,
            "exit_code": 0,
            "path": "scripts/gates/RS_G07.py",
            "sha256": "c" * 64,
        },
    )
    assert set(manifest) == {
        "artifacts",
        "assertions",
        "commands",
        "commit",
        "dirty",
        "environment",
        "finished_at",
        "gate",
        "project",
        "result",
        "schema_version",
        "started_at",
        "verifier",
    }
    assert manifest["dirty"] is False
    assert manifest["result"] == "passed"


def test_evidence_generator_derives_proof_records_from_gate_measurements() -> None:
    module = importlib.import_module("scripts.generate_gate_evidence")
    build_measurement_proof = getattr(module, "build_measurement_proof", None)
    assert callable(build_measurement_proof)
    gate = importlib.import_module("scripts.gates.RS_G07").SPEC
    commands = tuple(
        {
            "argv": list(measurement.argv),
            "exit_code": 0,
            "stdout": {
                "bytes": 4,
                "path": f"command-{index:02d}.stdout",
                "sha256": "a" * 64,
            },
            "stderr": {
                "bytes": 0,
                "path": f"command-{index:02d}.stderr",
                "sha256": "b" * 64,
            },
        }
        for index, measurement in enumerate(gate.measurements)
    )

    proof = build_measurement_proof(
        gate,
        commit="c" * 40,
        commands=commands,
    )

    assert proof["schema_version"] == 1
    assert proof["gate"] == "RS-G07"
    assert proof["commit"] == "c" * 40
    assert len(proof["measurements"]) == len(gate.measurements)
    for record, measurement in zip(
        proof["measurements"],
        gate.measurements,
        strict=True,
    ):
        assert record == {
            "argv": list(measurement.argv),
            "assertions": list(measurement.assertions),
            "exit_code": 0,
            "kind": "pytest",
            "platform": None,
            "stderr_sha256": "b" * 64,
            "stdout_sha256": "a" * 64,
        }


def test_evidence_generator_executes_the_registered_minimality_oracle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator = importlib.import_module("scripts.generate_gate_evidence")
    support = importlib.import_module("scripts.gates._verify")
    spec = support.GateSpec(
        gate="RS-G06",
        measurements=(
            support.Measurement(
                assertions=("every-unit-removal-checked",),
                argv=("python", "-m", "scripts.minimality_oracle_proof"),
                kind="minimality-oracle",
            ),
        ),
        expected_support_sha256="a" * 64,
    )
    monkeypatch.setattr(
        generator.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            0,
            stdout=b'{"passed":true}\n',
            stderr=b"",
        ),
    )

    commands, artifacts = generator._execute_measurements(
        spec,
        directory=tmp_path,
        timeout_seconds=30,
    )

    assert commands[0]["argv"] == [
        "python",
        "-m",
        "scripts.minimality_oracle_proof",
    ]
    assert artifacts == ()
