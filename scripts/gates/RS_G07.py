from __future__ import annotations

from scripts.gates._verify import verify_gate

_SUPPORT_SHA256 = "2ed3d8ca8f51d6d8790a39abba8588110273229997156ac258d70abb62be53b9"


if __name__ == "__main__":
    raise SystemExit(
        verify_gate(
            gate="RS-G07",
            assertions=(
                "reproduces-distinct",
                "absent-distinct",
                "invalid-distinct",
                "timeout-invalid",
                "signal-invalid",
            ),
            pytest_nodes=(
                "tests/test_predicate.py::test_exit_protocol_is_strict",
                "tests/test_predicate.py::test_timeout_output_limit_and_signal_are_invalid",
                "tests/test_hierarchy.py::test_invalid_candidates_are_never_accepted",
            ),
            expected_support_sha256=_SUPPORT_SHA256,
        )
    )
