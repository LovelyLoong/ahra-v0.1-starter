---
type: Roadmap
id: ROADMAP-dynamic-kernel-m1-sequence
schema_version: awkp/0.1
title: Dynamic kernel M1 implementation roadmap
description: Orders the bounded implementation steps from fixture-scoped integration to a durable generic Goal loop and a small real-Agent pilot.
status: proposed
owner: human:maintainer
source_refs:
  - ../../AHRA_dynamic_kernel_m1_master_plan_2026-06-26.md
  - ../../work/proposed/TASK-SEQUENCE-0033-0040.md
evidence_refs: []
confidence: draft
last_verified_at: 2026-06-26T00:00:00Z
review_after: 2026-09-26T00:00:00Z
tags: [roadmap, m1, dynamic-kernel]
---

# Non-negotiable order

```text
Actual Gate execution
  -> Mandatory Capability Admission
  -> Current Evidence and Defect semantics
  -> Unified repair scheduling
  -> Durable local recovery
  -> Generic Goal operation
  -> Deterministic M1 experiment
  -> Real-Agent pilot
```

# Why this order

- Verification must be real before repair can be trusted.
- Capability must be enforced before more execution paths are added.
- Evidence supersession must be correct before historical failed Evidence
  accumulates.
- Repair must use the same Scheduler before recovery is implemented.
- Recovery must be durable before a generic CLI claims resume support.
- Deterministic M1 must pass before model nondeterminism is introduced.

# Stage Gates

## SG-5 after TASK-0033

- selected Gates actually execute;
- terminal GateRuns exist;
- Evidence has GateRun lineage;
- missing/failed Gate blocks success.

## SG-6 after TASK-0035

- every side effect has a real admitted grant;
- Completion resolves supersession/current-set correctly;
- Defects support direct and affected Claims;
- historical Evidence remains auditable.

## SG-7 after TASK-0036

- initial and repair plans both use PlanExecution;
- repair and L2 nodes are Scheduler-driven;
- no direct executor call remains in the dynamic orchestrator;
- bounded repair cycles are enforced.

## SG-8 after TASK-0038

- SQLite-backed process restart works;
- generic Goal CLI drives the same services;
- fixture-specific code is an adapter/profile, not the operation core.

## SG-9 after TASK-0039

- twenty deterministic M1 runs satisfy all safety/correctness metrics;
- selective verification executes a cheaper actual Gate set;
- a release baseline and experiment scorecard exist.

## SG-10 after TASK-0040

- real Planner and real Executor pilots have run independently;
- combined mode runs only if safety preconditions pass;
- all safety invariants remain perfect;
- quality and cost are measured honestly.

# Deferred work

Do not add before SG-9:

- distributed workers;
- remote object storage;
- production secret broker;
- multi-tenant control plane;
- visual editor;
- arbitrary Agent spawning;
- framework self-modification;
- Memory-driven autonomous planning.
