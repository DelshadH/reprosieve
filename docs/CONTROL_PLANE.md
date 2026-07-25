# Immutable control plane

The bootstrap commit is the local contract anchor and starts the non-resettable execution clock. The following files must remain byte-for-byte unchanged after that root commit:

- `.agent-state.json`
- `AGENTS.md`
- `CODEX_START.txt`
- `CODEX_TASKS.json`
- `GATE_REGISTRY.json`
- `docs/AUTONOMOUS_LOOP.md`
- `docs/CONTROL_PLANE.md`
- `docs/EVIDENCE_CONTRACT.md`
- `docs/PRODUCT_CONTRACT.md`
- `docs/PROOF_GATES.md`
- `docs/RELEASE_STANDARD.md`
- `scripts/bootstrap.py`
- `scripts/contract.py`
- `scripts/contract_self_test.py`
- `scripts/next_task.py`
- `scripts/release_gate.py`
- `scripts/verify.py`

Implementation, tests, gate verifiers, evidence, progress, work log, manual blockers, packaging, workflows, and non-contract documentation may evolve. Do not amend, squash away, or replace the repository root commit. A required contract change is a new reviewed skeleton version, not an implementation shortcut.

Deleting `.agent-state.json`, resetting its timestamp, amending the root commit, or starting a replacement repository is a contract failure.

This guard prevents accidental or convenience-driven weakening by the build agent. It is not a cryptographic defense against a party deliberately rewriting both repository history and the checker; external review or a signed release tag remains the final trust anchor.
