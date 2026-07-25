# ADR 0002: Defer application replay beyond 0.1

- Status: accepted
- Date: 2026-07-25

## Decision

RunSieve 0.1 supports trace reduction, recorded-output materialization, and
offline predicate reproduction. It does not claim application or orchestration
replay. Capsules containing the experimental `application_replay` declaration
fail closed during predicate execution and export.

The pre-0.1 `replay` command is a warning alias for `materialize`. The pre-0.1
`minimize` command is a warning alias for `reduce`.

## Rationale

The earlier adapter executed a user script that manually consumed extracted
JSON values. It did not intercept a framework provider/tool boundary, enforce a
single ordered interaction stream with exact arguments, detect all unused or
extra interactions, or measure intercepted calls. Calling that application
replay overstated the evidence.

## Reconsideration criteria

Application replay may be introduced at maturity level 0.5 after one narrow
framework adapter demonstrates:

- a real application entry point rerun from a fresh trial directory;
- provider and tool substitution at the interfaces used by that application;
- strict order and argument matching;
- explicit unused, extra, and mismatch failures with divergence location;
- measured intercepted-call counts and application exit status;
- no live provider or original-tool invocation;
- an end-to-end publishable fixture and independent verifier evidence.
