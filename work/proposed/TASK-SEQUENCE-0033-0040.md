---
type: WorkSequence
id: SEQ-ahra-dynamic-kernel-m1
schema_version: awkp/0.1
title: Proposed task sequence for the M1 minimal live dynamic loop
description: Defines the strict proposed execution order for TASK-0033 through TASK-0040 before promotion into authoritative AWKP task records.
status: proposed
owner: human:maintainer
source_refs:
  - ../../AHRA_dynamic_kernel_m1_master_plan_2026-06-26.md
  - tasks/TASK-0033.md
  - tasks/TASK-0040.md
evidence_refs: []
confidence: draft
last_verified_at: 2026-06-26T00:00:00Z
review_after: 2026-09-26T00:00:00Z
tags: [work, planning, dynamic-kernel, m1]
---

# Proposed sequence

> These files are proposals. Before execution, confirm IDs and promote each
> Task through AWKP state/event/manifest rules. Do not create all leases or
> implementation branches in advance.

## Strict order

| Order | Task | Outcome | Stage Gate |
|---:|---|---|---|
| 1 | TASK-0033 | Actual Gate execution and GateRun/Evidence lineage | SG-5 |
| 2 | TASK-0034 | Mandatory Capability Admission in runtime path | |
| 3 | TASK-0035 | Evidence current-set, supersession and multi-Claim Defects | SG-6 |
| 4 | TASK-0036 | Unified Scheduler-driven repair lifecycle | SG-7 |
| 5 | TASK-0037 | SQLite durability and real process restart | |
| 6 | TASK-0038 | Generic Goal CLI and operation profile | SG-8 |
| 7 | TASK-0039 | Twenty-run deterministic M1 experiment | SG-9 |
| 8 | TASK-0040 | Small real-Agent pilot | SG-10 |

## Execution protocol

For every Task:

1. Confirm the previous Task is completed by EvidenceGate.
2. Create or claim the actual Task with CAS.
3. Read only the current Task and its input refs.
4. Run and record the baseline before modification.
5. Use an isolated branch/worktree.
6. Change contracts before implementations when semantics change.
7. Implement the smallest vertical slice satisfying this Task only.
8. Run named negative tests, not only happy-path tests.
9. Publish implementation Artifact, deterministic Evidence, metrics and an
   immutable Handoff.
10. Use an independent verifier.
11. Run the named Stage Gate before starting the next stage.

## Anti-overlap rule

- TASK-0033 must not add SQLite or a Goal CLI.
- TASK-0034 must not redesign Evidence supersession.
- TASK-0035 must not directly execute repair.
- TASK-0036 may use in-memory stores; durability belongs to TASK-0037.
- TASK-0037 must not add model-driven behavior.
- TASK-0038 must expose existing services, not embed orchestration in CLI.
- TASK-0039 must remain deterministic.
- TASK-0040 must not weaken safety thresholds to improve model success.

## Failed Task handling

Do not restart the entire roadmap.

Create a Defect/Handoff containing:

- failed acceptance criterion;
- failed GateRun or command;
- exact affected contracts/files;
- current and stale Evidence refs;
- whether the Stage Gate remains valid;
- one exact next action.

Only rerun prior Stage Gates when changed digests invalidate their Evidence.
