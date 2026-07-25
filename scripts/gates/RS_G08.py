from scripts.gates._verify import verify_gate

_SUPPORT = "2ed3d8ca8f51d6d8790a39abba8588110273229997156ac258d70abb62be53b9"

if __name__ == "__main__":
    raise SystemExit(
        verify_gate(
            gate="RS-G08",
            assertions=(
                "span-reduction",
                "message-reduction",
                "tool-pair-reduction",
                "json-field-reduction",
                "text-reduction",
                "file-reduction",
                "environment-reduction",
            ),
            pytest_nodes=(
                "tests/test_hierarchy.py::test_each_hierarchy_level_accepts_a_real_reduction",
            ),
            expected_support_sha256=_SUPPORT,
        )
    )
