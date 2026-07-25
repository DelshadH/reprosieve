from scripts.gates._verify import verify_gate

_SUPPORT = "2ed3d8ca8f51d6d8790a39abba8588110273229997156ac258d70abb62be53b9"

if __name__ == "__main__":
    raise SystemExit(
        verify_gate(
            gate="RS-G03",
            assertions=(
                "capsule-hash-repeatable",
                "member-hashes-verified",
                "traversal-rejected",
                "archive-bomb-rejected",
                "malformed-reference-rejected",
            ),
            pytest_nodes=("tests/test_capsule.py", "tests/test_schema.py"),
            expected_support_sha256=_SUPPORT,
        )
    )
