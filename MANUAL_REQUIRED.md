# Manual actions required

Source of truth: `MANUAL_REQUIRED.json`. It currently contains no open items.

Manual work is allowed only at final release task `RS-080` and only for one of these machine-enforced kinds: `github_authentication`, `repository_ownership`, `registry_authentication`, `registry_2fa`, `legal_identity`, `paid_infrastructure`, or `protected_settings`.

Every item must use ID `HUMAN-NNN` and include: `kind`, `status`, concrete `reason`, concrete `why_human_only`, `detected_at`, a failing `probe` with argv/exit/output excerpt, non-empty `exact_steps`, `blocks_tasks: ["RS-080"]`, `blocks_release: true`, and `unblock_check: {"argv": [...], "expected_exit_code": 0}`. The release gate reruns every resolved check without a shell and rejects any mismatch or working-tree mutation. Resolved items also require `resolved_at` and `resolution_evidence`. Routine engineering decisions, local tooling, test failures, design ambiguity, and ordinary implementation work are rejected by the contract validator.
