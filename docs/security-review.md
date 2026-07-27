# Security review

Review date: 2026-07-24. Scope: the pre-0.1 source tree, capsule format,
OpenAI adapter, predicate runner, reducer, exporter, packaging, and CI.

## Threats and controls

| Boundary | Threat | Control |
|---|---|---|
| Trace conversion | Secret reaches disk or backend exporter | In-memory bounded conversion, exact/default redaction, default `set_trace_processors()`, discarded target output, canary byte scans. |
| Capsule reader | Traversal, symlink, unknown member, duplicate, bomb, corruption | Strict public member allowlist, no extraction, normalized names, reparse-point rejection, member/total/ratio limits, duplicate detection, canonical manifest and SHA-256 verification. |
| Graph | Dangling or misleading materialization references | Prior-parent/dependency validation and exact request/response and call/result producer rules. |
| Predicate command | Shell injection or path escape | Embedded Python script only, normalized workspace-relative path, `shell=False`, direct argument vector. |
| Predicate process | Network, host-file, process, native-code, resource abuse | Fresh directory, minimal environment, provider/proxy removal, socket denial, audit hook, OS resource limits, output hashing/cap, timeout, cancellation, process-group termination. |
| Reduction | Invalid candidate accepted as absent | Tri-state enum, accept only `REPRODUCES`, structural validation before execution. |
| Export | Unsafe overwrite, split validation, or silent arbitrary-code execution | New non-link directory only, one immutable validated source snapshot, standalone validation parity, embedded predicate requirement, and explicit `--trust-embedded-predicate` authorization. |
| Supply chain | Vulnerable dependency, secret, unsafe action | Zero core dependencies, bounded optional SDK range, exact dev pins, pip-audit, Bandit, custom secret/shell/action scan, license report, SHA-pinned Actions. |

## Residual risks

- Python audit hooks are not an OS sandbox. A CPython vulnerability, native
  interpreter exploit, or unhandled audit event could escape the intended
  boundary. `os.exec` is denied as defense in depth, but the explicit trust flag
  remains the security boundary. Run only predicates you are prepared to execute
  as your user.
- Capture necessarily holds raw SDK values briefly in process memory. A debugger,
  memory dump, compromised interpreter, or target crash reporter can observe them.
- Redaction cannot identify arbitrary personal or proprietary information.
- The parent application may write its own secrets before ReproSieve sees a trace.
- Windows does not expose every POSIX resource limit. Timeout, output, direct
  command, clean directory, environment, network, filesystem, process, and native
  loading controls still apply.
- K-of-N evidence measures the embedded predicate over one recorded trajectory;
  it is not evidence about live model probability.

No high or critical known dependency vulnerabilities were present when the
documented audit was run. This is a point-in-time result, not a warranty.

## Experimental application-replay boundary

The 0.5 adapter reruns an explicit trusted in-process callback through the
OpenAI Agents SDK Runner. It substitutes the public model and declared
function-tool interfaces, requires ordered exact interaction matching, and
measures provider-resolution and supplied-original-tool canaries. Capsules
never supply a command or entry point to execute.

This is not an arbitrary-code sandbox. The callback can use unrelated file,
network, process, or object references outside the injected interfaces. The
no-live-call result applies only to the injected provider and supplied original
tools measured by the adapter and evidence verifier. Redaction of a matching
field makes a capsule replay-ineligible rather than accepting approximate
equality.

Permissioned case-study packages are treated as untrusted data. Their
structural verifier reads bounded regular files, rejects link/path escapes and
uninventoried files, and checks hashes without executing the declared predicate
or application. Permission authenticity and disclosure safety cannot be
established by that verifier.

## Contract-v2 secret-classification review

On 2026-07-25, a fresh all-files scan was compared against an exact reviewed
set before `.secrets.baseline` was written. The 21 findings are non-secret
contract/root SHA-256 values, the shared gate-verifier support hash, one
deliberate verifier-fixture hash, and the secret-check regression keyword.
Generation aborts if any finding is added, removed, moved, or changed; the
repository check also fails on every new unreviewed finding.

## Release checks

CI uses current immutable action commit SHAs, read-only repository permissions,
disabled checkout credentials, a Python 3.11–3.13 matrix, package smoke tests,
`pip-audit`, high-severity Bandit checks, tracked-file secret/shell/action scans,
and a license inventory.
