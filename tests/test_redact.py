from __future__ import annotations

import unittest

from runsieve.redact import redact


class RedactionTests(unittest.TestCase):
    def test_redacts_secret_keys_and_bearer_tokens(self) -> None:
        value = {
            "api_key": "sk-supersecretvalue123",
            "message": "Authorization: Bearer abcdefghijklmnop",
            "safe": "hello",
        }
        result = redact(value, salt=b"fixture")
        rendered = repr(result)
        self.assertNotIn("supersecret", rendered)
        self.assertNotIn("abcdefghijklmnop", rendered)
        self.assertEqual(result["safe"], "hello")


if __name__ == "__main__":
    unittest.main()
