# Security policy

Please report suspected vulnerabilities privately through
[GitHub Security Advisories](https://github.com/DelshadH/runsieve/security/advisories/new).
Do not attach a real run capsule, credential, private source file, or personal
data. Use synthetic canaries and the smallest safe reproduction.

High-priority areas include redaction bypass, archive traversal or expansion,
replay escaping offline isolation, unintended provider or tool execution,
unbounded predicates, and unsafe exported reproduction directories.

RunSieve is pre-release software. Until version 0.1, use it only with synthetic
or disposable data. The current threat review, controls, and residual risks are
documented in [docs/security-review.md](docs/security-review.md).
