# Evidence contract

A task or gate is not complete because an agent says it is. A release gate passes only when the repository validates the exact state, verifies content-addressed evidence, and reruns the gate-specific verifier.

A producer is not its own verifier. A hash proves byte integrity only; it does not prove authenticity, authorization, platform execution, or semantic correctness. Each gate-specific verifier must derive its assertions from the concrete artifacts required for that claim.

## Manifest v1

Every gate writes exactly one canonical JSON manifest per run at `.evidence/<gate>/<run-id>/manifest.json`:

```json
{"artifacts":[{"bytes":123,"path":"artifact.json","sha256":"64 lowercase hex"}],"assertions":[{"id":"every-unit-removal-checked","passed":true},{"id":"invalid-reasons-recorded","passed":true},{"id":"no-removable-reproducer","passed":true}],"commands":[{"argv":["python","-m","pytest"],"exit_code":0,"stderr":{"bytes":0,"path":"pytest.stderr","sha256":"64 lowercase hex"},"stdout":{"bytes":321,"path":"pytest.stdout","sha256":"64 lowercase hex"}}],"commit":"full Git SHA tested from a clean tree","dirty":false,"environment":{"python":"3.13.5","os":"linux"},"finished_at":"2026-07-24T12:00:01Z","gate":"RS-G06","project":"runsieve","result":"passed","schema_version":1,"started_at":"2026-07-24T12:00:00Z","verifier":{"argv":["python","-m","scripts.gates.RS_G06"],"bytes":1234,"exit_code":0,"path":"scripts/gates/RS_G06.py","sha256":"64 lowercase hex"}}
```

The file is UTF-8, recursively key-sorted, single-line JSON followed by one LF. `PROGRESS.json` stores `{ "path": ".evidence/.../manifest.json", "sha256": "..." }`.

## Non-bypassable rules

- Paths are relative POSIX paths. Absolute paths, `..`, empty components, backslashes, and symlinks are rejected.
- Command stdout, command stderr, and every artifact are size- and SHA-256-checked.
- Assertions are non-empty, uniquely named, explicit, and all passed. Every manifest and verifier report contains every gate-specific ID listed in `GATE_REGISTRY.json.required_assertions`.
- The recorded verifier argv must exactly match `GATE_REGISTRY.json`; its path, size, and SHA-256 must match the verifier implementation rerun at release time.
- `release-gate` requires the exact task/gate ID sets, every task proof-gated and passed with all of its owned gates, no release-blocking manual item, a clean Git tree, and an evidence commit that is an ancestor of `HEAD`.
- Evidence must be generated from a clean full commit SHA. That commit must remain an ancestor of the final verified head. A later change to measured source, assertion logic, or the relevant verifier invalidates affected evidence.
- `release-gate` reruns every gate verifier against its manifest. Stored status, prose, and recorded stdout are never sufficient.
- Proof timestamps must fall after the immutable bootstrap timestamp and before the owning task's cumulative deadline. The total release must complete within hour 72.
- The release gate also compares the immutable control-plane files in `CONTROL_PLANE.md` with the repository root commit. Rewriting or squashing that root is forbidden.
- The release gate validates `CONTRACT_VERSION.json` and independently recomputes the root/current control-plane bundle identities.
- `.evidence/` is committed so a clean clone can reproduce release verification. Keep evidence compact; large disposable traces belong in generated test fixtures or release artifacts with pinned hashes.
- Evidence is append-only. Never overwrite a run directory.

## Clean-proof sequence

1. Implement and commit the source change.
2. Run the proof from that clean commit and create the evidence directory.
3. Run the gate verifier; write its exact argv/exit status into the manifest.
4. Canonicalize and hash the manifest; update `PROGRESS.json` and commit evidence plus progress.
5. Run the full verifier and release gate. The release gate reruns the proof verifier on the current clean checkout.

A constant-pass verifier, edited progress state, screenshot, or hand-written claim is not proof.
