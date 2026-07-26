# ADR 0001: Separate reduction, materialization, predicate reproduction, and replay

- Status: accepted
- Date: 2026-07-25

RunSieve uses four non-interchangeable terms:

- trace reduction removes declared units while preserving graph validity;
- recorded-output materialization reconstructs retained model and tool values;
- offline predicate reproduction runs only a declared predicate against those
  values in a fresh constrained directory;
- application replay reruns application or orchestration code through
  intercepted provider and tool interfaces.

The 0.1 contract includes the first three only. A report must state exactly
which path executed. Hashes establish byte identity only; they do not establish
semantic truth, authorization, or real-world impact.
