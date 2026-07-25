# ADR 0003: Narrow public-API application replay for 0.5

- Status: accepted for experimental 0.5 work
- Date: 2026-07-25

## Context

ADR 0002 correctly excludes application replay from 0.1. Recorded-output
materialization and predicate reproduction do not execute an application or
SDK orchestration loop.

The OpenAI Agents SDK exposes public `Model`, `FunctionTool`, `Agent`,
`RunConfig`, and `Runner` interfaces. These are sufficient for one narrow
adapter when an application explicitly accepts injected objects.

## Decision

Introduce capture and replay sessions for one explicit asynchronous
application callback:

- capture delegates through public model and tool interfaces and records
  redacted ordered interactions;
- replay re-executes the callback and SDK Runner with recorded model and tool
  substitutes;
- exact request, schema, name, argument, order, and exhaustion matching is
  required;
- unsupported SDK behavior and redacted matching fields fail closed;
- provider resolution and original tool handlers are guarded by measured
  canaries;
- no capsule-supplied entry point executes;
- no 0.1 CLI or product promise changes.

## Consequences

The adapter genuinely executes application and SDK orchestration logic within
its declared boundary. It does not prove arbitrary application replay, isolate
trusted callback code, replay external side effects, or prevent the callback
from bypassing injected interfaces.

The frozen implementation now has independent synthetic RS-05-AR1 gate
evidence. The 0.5 claim remains pending until at least one permissioned real
case and independent human review exist. ADR 0002 remains authoritative for
0.1.
