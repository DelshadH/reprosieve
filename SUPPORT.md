# Support policy

RunSieve is a pre-0.1 project. Only the behavior documented for the current
repository version is supported; there is no long-term support branch or
backward-compatibility guarantee yet.

Supported runtime combinations:

- Python 3.11, 3.12, and 3.13;
- `openai-agents>=0.18.3,<0.19` for capture;
- Linux and macOS for the exported one-command reproduction;
- synthetic or disposable inputs only.

Use the GitHub issue forms for reproducible defects. Include the RunSieve
version, platform, exact command, exit code, and a redacted synthetic capsule
when possible. Do not attach credentials, private source, personal data, or raw
production traces.

Report suspected vulnerabilities privately as described in
[SECURITY.md](SECURITY.md), not through a public issue.
