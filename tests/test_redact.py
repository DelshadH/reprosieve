from __future__ import annotations

import unittest

from reprosieve.redact import RedactionLimits, RedactionPolicy, redact, redact_with_report


class RedactionTests(unittest.TestCase):
    def test_redacts_secret_keys_and_bearer_tokens(self) -> None:
        value = {
            "api_key": "sk-supersecretvalue123",  # pragma: allowlist secret
            "message": "Authorization: Bearer abcdefghijklmnop",
            "safe": "hello",
        }
        result = redact(value, salt=b"fixture")
        rendered = repr(result)
        self.assertNotIn("supersecret", rendered)
        self.assertNotIn("abcdefghijklmnop", rendered)
        self.assertEqual(result["safe"], "hello")

    def test_exact_canaries_regexes_paths_and_filenames_are_redacted(self) -> None:
        canary = "PRIVATE-CANARY-123"
        policy = RedactionPolicy(
            salt=b"fixture",
            exact_canaries=(canary,),
            patterns=(r"customer-\d+",),
            deny_paths=("profile.email",),
            allow_paths=("profile.session_label",),
        )
        value = {
            "profile": {
                "email": "person@example.test",
                "session_label": "ordinary",
                "note": f"{canary} customer-314",
            }
        }
        result, report = redact_with_report(value, policy=policy)
        rendered = repr(result)
        self.assertNotIn(canary, rendered)
        self.assertNotIn("customer-314", rendered)
        self.assertNotIn("person@example.test", rendered)
        self.assertIn("ordinary", rendered)
        self.assertGreaterEqual(report.replacements, 3)
        self.assertNotIn(canary, repr(report))

    def test_typed_marker_preserves_redacted_value_type(self) -> None:
        result = redact({"password": 42}, salt=b"fixture")
        marker = result["password"]
        self.assertIsInstance(marker, dict)
        self.assertEqual(marker["type"], "int")
        self.assertIn("fingerprint", marker)

    def test_bounded_traversal_rejects_deep_or_huge_payloads_without_echo(self) -> None:
        deep: object = "DO-NOT-ECHO"
        for _ in range(20):
            deep = [deep]
        policy = RedactionPolicy(salt=b"x", limits=RedactionLimits(max_depth=5, max_nodes=20))
        with self.assertRaisesRegex(ValueError, "^redaction depth limit exceeded$"):
            redact_with_report(deep, policy=policy)

        with self.assertRaisesRegex(ValueError, "^redaction node limit exceeded$"):
            redact_with_report(list(range(30)), policy=policy)

    def test_rejects_regex_forms_that_cannot_be_bounded(self) -> None:
        for pattern in (r"(a+)+$", r"a+a+a+a+Z"):
            policy = RedactionPolicy(salt=b"x", patterns=(pattern,))
            with (
                self.subTest(pattern=pattern),
                self.assertRaisesRegex(ValueError, "^invalid redaction pattern$"),
            ):
                redact_with_report("ordinary input", policy=policy)


if __name__ == "__main__":
    unittest.main()
