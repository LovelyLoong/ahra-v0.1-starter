---
type: Architecture
id: ARCH-goal-execution-lifecycle
schema_version: awkp/0.1
title: Goal execution lifecycle
description: Defines the durable parent lifecycle that links Goal, multiple immutable Plan versions, Defects, repair cycles, Evidence, and final completion.
status: proposed
owner: team:platform
source_refs:
  - dynamic-agent-kernel.md
  - plan-ir.md
  - gate-execution-pipeline.md
  - ../../src/ahra/plan_execution.py
evidence_refs: []
confidence: draft
last_verified_at: 2026-06-26T00:00:00Z
review_after: 2026-09-26T00:00:00Z
tags: [architecture, goal, execution, recovery]
---

# Summary

A PlanExecution belongs to one immutable PlanIR version. A dynamic repair loop
may create multiple PlanIR versions. Therefore a stable parent record is needed
to represent the entire operation from Goal admission to completion.

That parent is `GoalExecution`.

# Object boundaries

| Object | Meaning | Lifecycle |
|---|---|---|
| GoalContract | Human-reviewable objective and acceptance authority | Versioned, stable |
| GoalExecution | One governed attempt to complete a Goal across plan versions | Spans planning, repair and completion |
| PlanIR | One immutable admitted execution plan version | Never mutated |
| PlanExecution | Runtime execution of one PlanIR version | One child of GoalExecution |
| NodeRun | Attempt to execute one Plan node | Child of PlanExecution |
| GateRun | Attempt to execute one Gate | Bound to NodeRun or GoalExecution |
| Defect | Verified mismatch requiring repair or escalation | Spans plan versions |
| Evidence | Verifiable result bound to exact subjects and environment | Append-only/current-set resolved |

# GoalExecution minimum fields

```yaml
schema_version: ahra/goal-execution/0.1
goal_execution_id: GEXEC-...
goal_ref: GOAL-...
goal_digest: sha256:...
claim_graph_ref: CLAIMGRAPH-...
claim_graph_digest: sha256:...
status: admitted
status_version: 0
active_plan_execution_ref: null
plan_execution_refs: []
open_defect_refs: []
resolved_defect_refs: []
repair_cycle: 0
max_repair_cycles: 2
budget:
  max_model_calls: 40
  max_tool_calls: 80
  max_cost_usd: 5.0
  deadline_at: ...
usage: {}
workspace_ref: ...
store_ref: sqlite-local
checkpoint_ref: null
artifact_refs: []
evidence_refs: []
approval_refs: []
created_at: ...
updated_at: ...
```

# State machine

```text
created
   ↓
admitted
   ↓
planning
   ↓
plan_review / awaiting_approval
   ↓
running
   ↓
verifying
   ├── succeeded
   ├── repairing ──► planning ──► running
   ├── paused_input
   ├── paused_auth
   ├── failed
   ├── timed_out
   └── canceled
```

# Transition rules

1. `GoalExecution` may have only one active PlanExecution.
2. A PlanExecution is bound to an immutable PlanIR digest.
3. A repair never mutates PlanIR v1. It creates PlanIR v2 with
   `parent_plan_digest`.
4. A PlanExecution may succeed at the DAG level while GoalExecution remains in
   verification.
5. GoalExecution succeeds only from the Completion Service.
6. An open Defect prevents GoalExecution success.
7. `repair_cycle` increments before a new repair PlanExecution is admitted.
8. Exceeding `max_repair_cycles` produces `failed` or `paused_input`, never an
   unbounded loop.
9. A PlanExecution failure that is not repairable produces an immutable Handoff.
10. State writes use expected version / transaction semantics.

# Unified repair flow

```text
PlanExecution v1
      ↓
actual failed GateRun
      ↓
Defect OPEN
      ↓
RepairPlanner → PlanPatchDraft
      ↓
PlanCompiler / Admission
      ↓
PlanIR v2
      ↓
PlanExecution v2
      ↓
Scheduler executes repair + selected Gate nodes + terminal L2 node
      ↓
Defect RESOLVED only after required GateRuns pass
      ↓
Completion
```

The orchestration layer must not call a NodeExecutor directly.

# Reuse semantics

A PlanPatch may name unchanged nodes and reusable Evidence, but reuse is accepted
only when:

- the unchanged node definition digest matches;
- its input/subject/dependency digests remain unchanged;
- the Evidence is in the resolved current set;
- Policy, Runtime, test definition and verifier release remain compatible;
- no changed Claim dependency invalidates it;
- the reuse decision is recorded in the new PlanExecution.

# Durable resume

A resumable GoalExecution must persist:

- current state/version;
- active PlanExecution;
- every NodeRun state and attempt;
- leases and fencing tokens;
- checkpoints;
- completed side-effect idempotency records;
- GateRun and Evidence refs;
- open Defects;
- capability decisions/grants;
- usage and remaining budget;
- pending input/approval.

On restart:

1. load GoalExecution and active PlanExecution;
2. reconcile leases and in-flight NodeRuns;
3. reject stale workers;
4. do not repeat completed idempotent records;
5. requeue only safe, incomplete attempts;
6. emit a recovery event;
7. continue through the same Scheduler.

# Task projection

GoalExecution and PlanExecution do not directly mark an AWKP Task completed.

Recommended projection:

| GoalExecution | AWKP Task recommendation |
|---|---|
| admitted/planning/running/repairing | working |
| paused_input | waiting_input |
| paused_auth | waiting_auth |
| verifying/succeeded | review |
| failed | changes_requested or failed by policy |
| canceled | canceled |

EvidenceGate remains the authority for `review -> completed`.
