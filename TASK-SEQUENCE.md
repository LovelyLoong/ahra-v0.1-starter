# Proposed task sequence for CTX-ahra-dynamic-kernel

> These files are proposals, not yet authoritative `work/tasks/*` records. `TASK-0021` must confirm IDs, create state/events/manifests through AWKP rules, and record any conflict before execution.

## Strict order

| Order | Task | Outcome | Stage Gate |
|---:|---|---|---|
| 1 | TASK-0021 | Repository reconciliation and baseline truth | |
| 2 | TASK-0022 | Architecture authority and lifecycle policy integrated | SG-0 |
| 3 | TASK-0023 | Goal/Claim/Gate contracts | |
| 4 | TASK-0024 | Evidence validity and invalidation | |
| 5 | TASK-0025 | Layered verification, Defect and selective rerun | SG-1 |
| 6 | TASK-0026 | PlanDraft/PlanIR compiler and validator | |
| 7 | TASK-0027 | Capability admission and reference monitor skeleton | |
| 8 | TASK-0028 | Node executor registry and bounded_task primitive | |
| 9 | TASK-0029 | Static PlanIR DAG scheduler and state wiring | SG-2 |
| 10 | TASK-0030 | Planner adapter and bounded replan protocol | |
| 11 | TASK-0031 | Fixture end-to-end dynamic repair loop | SG-3 |
| 12 | TASK-0032 | Legacy cleanup and repository consolidation | SG-4 |

## Operating procedure for each task

1. Create/claim the actual AWKP task using CAS and an append-only event.
2. Read `AGENTS.md`, the master plan, relevant architecture docs, and the task file.
3. Record baseline commands and failures before changing code.
4. Work only inside an isolated branch/worktree.
5. Do not implement acceptance criteria belonging to later tasks.
6. Publish implementation Artifact, deterministic Evidence, semantic review Evidence where required, and an immutable Handoff.
7. An independent Verifier maps every task criterion to Evidence.
8. EvidenceGate, not the producer, changes the task to completed.
9. Run the named Stage Gate before starting the next stage.

## Use of current workflow

The existing `standard-harness` may be used as a bounded execution path when it is stable for the task. Do not use `loop-engineering` to auto-generate this entire roadmap. Each migration task is deliberately bounded so failures can be diagnosed. The new dynamic planner is introduced only in TASK-0030.

## Failed task handling

A failed task does not cause earlier completed tasks to be rerun automatically. Create a Defect/Handoff that identifies:

- failed criterion;
- exact command/result;
- affected files and contracts;
- which prior Evidence may now be stale;
- one exact next action.

Only rerun prior Stage Gates when the changed files affect their contracts or evidence fingerprints.
