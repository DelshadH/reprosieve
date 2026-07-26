# Evidence

Use `EVIDENCE_CONTRACT.md`. ReproSieve additionally records Python/SDK/package versions, capsule/replay mode, predicate file/command hash, timeout and resource policy, network-denial method, trial seeds/results, source and reduced capsule hashes, and redaction configuration hash.

Each gate adds a verifier under `scripts/gates/RS_Gxx.py`. `PROGRESS.json` evidence entries are `{ "path": ".../manifest.json", "sha256": "..." }`, never bare paths.
