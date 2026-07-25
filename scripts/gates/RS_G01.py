from scripts.gates._verify import verify_gate

_SUPPORT = "2ed3d8ca8f51d6d8790a39abba8588110273229997156ac258d70abb62be53b9"

if __name__ == "__main__":
    raise SystemExit(
        verify_gate(
            gate="RS-G01",
            assertions=(
                "public-processor-only",
                "default-exporter-replaced",
                "no-duplicate-export",
                "sdk-private-import-scan",
                "synthetic-trace-captured",
            ),
            pytest_nodes=("tests/test_openai_adapter.py",),
            expected_support_sha256=_SUPPORT,
        )
    )
