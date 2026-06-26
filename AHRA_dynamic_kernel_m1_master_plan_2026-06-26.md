---
type: Roadmap
id: ROADMAP-ahra-dynamic-kernel-m1
schema_version: awkp/0.1
title: AHRA dynamic kernel M1 minimal live loop plan
description: Defines the bounded path from the current deterministic fixture to a real, governed, durable, selectively verified dynamic Agent loop.
status: proposed
owner: human:maintainer
source_refs:
  - README.md
  - docs/architecture/dynamic-agent-kernel.md
  - docs/architecture/verification-system.md
  - docs/architecture/plan-ir.md
  - docs/architecture/component-inventory.json
  - work/tasks/TASK-0031/
  - work/tasks/TASK-0032/
evidence_refs: []
confidence: draft
last_verified_at: 2026-06-26T00:00:00Z
review_after: 2026-09-26T00:00:00Z
tags: [roadmap, dynamic-kernel, m1, experiment]
---

# 0. Decision

The next milestone is not another architecture expansion.

The next milestone is:

> **M1: one small Goal can be planned, admitted, executed, verified, repaired,
> selectively reverified, recovered after process restart, and completed only
> from current Evidence through one generic operation path.**

The current deterministic fixture remains useful as M0, but M1 is not reached
until the following boundaries are enforced by the runtime rather than merely
represented in objects or reports.

# 1. Current baseline

The completed migration already provides:

- GoalContract, ClaimGraph, GateDefinition, and GatePlan;
- Evidence v2 fingerprints and invalidation inputs;
- PlanDraft, PlanPatchDraft, PlanIR, compiler, and validation;
- a static PlanIR DAG Scheduler and NodeRun state;
- Capability data models, admission logic, and a local runtime gateway;
- a bounded task executor;
- a deterministic defect-repair fixture;
- repository authority, lifecycle, and legacy isolation.

The remaining critical gaps are:

1. Verification selection does not yet guarantee actual Gate execution.
2. Runtime grants can still be synthesized without invoking Capability
   Admission.
3. Repair execution can bypass PlanExecution and Scheduler.
4. Evidence supersession does not yet define a stable current Evidence set.
5. Recovery has not yet survived a real process exit.
6. The default dynamic path is fixture-specific rather than a generic Goal
   operation surface.
7. A real Agent has not yet been introduced under the completed boundaries.

# 2. M1 completion definition

M1 is complete only when all statements below are true.

## 2.1 Acceptance first

- A GoalContract is authoritative before execution planning.
- Every required Goal criterion is covered by at least one required Claim.
- Every required Claim has a Gate or explicit approval responsibility.
- Planner output cannot weaken Goal, Claim, Gate, Policy, or Approval contracts.

## 2.2 Untrusted planning

- A Planner produces only PlanDraft or PlanPatchDraft.
- A PlanDraft is never executable.
- PlanIR is content-addressed, validated, immutable per version, and bound to
  exact Goal, ClaimGraph, Gate, Runtime, and policy digests.
- Invalid, over-budget, cyclic, or privilege-widening plans fail closed.

## 2.3 Enforced capability boundary

- PlanIR contains capability intent, not self-authorized runtime privilege.
- Every runtime grant is produced by Capability Admission.
- Every side effect is bound to a Goal/Plan/Node/role/resource/expiry/policy
  decision.
- A denied action produces an audit record before the side effect.
- No Scheduler or fixture helper may fabricate an admitted PolicyDecision.

## 2.4 Actual layered verification

- VerificationSelection chooses Gates.
- GateRunner executes every selected Gate.
- Every terminal Gate attempt produces a GateRun record.
- Every accepted Evidence record refers to the GateRun that produced it.
- A required Gate that is missing, failed, blocked, stale, or unexecutable
  prevents Node or Goal success.
- L0 is cheap and local, L1 protects integration boundaries, and L2 evaluates
  logical coverage of all required Claims.

## 2.5 Unified repair

- A failed Gate creates a Defect with reproduction, direct Claims, affected
  Claims, and a repair boundary.
- RepairPlanner produces only PlanPatchDraft.
- A repaired PlanIR creates a new PlanExecution under the same GoalExecution.
- Repair, revalidation, selective Gate execution, and terminal Goal verification
  all use the same Scheduler.
- Unchanged nodes are reused only through current Evidence, never by assertion.

## 2.6 Durable local execution

- GoalExecution, PlanExecution, NodeRun, Checkpoint, GateRun, Evidence refs,
  capability decisions, and idempotency records survive process restart.
- Resume does not repeat a completed non-idempotent action.
- Expired leases and stale fencing tokens are rejected.
- Local durability may use SQLite; M1 does not require distributed deployment.

## 2.7 Generic operation

The default local operation surface supports:

```text
ahra goal validate
ahra goal plan
ahra goal start
ahra goal inspect
ahra goal resume
ahra goal cancel
```

The CLI wraps Python services and contains no workflow logic.

# 3. Target runtime flow

```text
Human GoalContract
        │
        ▼
Acceptance Planner or project acceptance adapter
        │
        ▼
ClaimGraph + GatePlan
        │
        ▼
Execution Planner
        │
        ▼
Untrusted PlanDraft
        │
        ▼
PlanCompiler + Plan Admission
        │
        ▼
Immutable PlanIR v1
        │
        ▼
GoalExecution / PlanExecution
        │
        ▼
Capability Admission per runnable Node
        │
        ▼
Static DAG Scheduler
        │
        ├── bounded_task NodeExecutor
        ├── gate_verification Node
        └── goal_verification Node
        │
        ▼
VerificationSelection
        │
        ▼
GateRunnerRegistry → actual GateRun(s)
        │
        ▼
EvidenceRegistry current set
        │
        ├── Complete
        │
        └── Defect
                │
                ▼
          Repair Planner
                │
                ▼
          PlanPatchDraft
                │
                ▼
          PlanIR v2
                │
                ▼
          PlanExecution v2 through the same Scheduler
                │
                ▼
          selected GateRun(s) + L2 Completion
```

# 4. Authority model

The following responsibilities must remain separate.

| Authority | May do | Must not do |
|---|---|---|
| Human Goal owner | Set objective, scope, criteria, risk, approval and budget | Directly falsify Evidence |
| Acceptance Planner | Propose Claims and Gates | Execute tools or weaken Goal |
| Execution Planner | Propose PlanDraft / PlanPatchDraft | Grant itself capabilities or declare completion |
| Plan Compiler / Admission | Validate and materialize PlanIR | Invent business criteria |
| Capability Admission | Narrow and issue runtime grants | Expand Goal or policy scope |
| Scheduler | Dispatch admitted Nodes and enforce state/budget/lease | Treat selection as verification success |
| Executor | Produce bounded Artifact and observations | Change acceptance or complete Goal |
| GateRunner | Execute one declared verification contract | Mutate production work unless explicitly designed as a test fixture |
| Evidence Registry | Resolve current Evidence and history | Turn a failed observation into passed Evidence |
| Completion Service | Decide logical completion from current Evidence | Ignore open Defects or stale Evidence |
| EvidenceGate verifier | Approve AWKP Task completion | Act as the producing identity |

# 5. Work sequence

| Order | Task | Primary outcome | Stage Gate |
|---:|---|---|---|
| 1 | TASK-0033 | Selected Gates actually execute and produce GateRun/Evidence | SG-5 |
| 2 | TASK-0034 | Capability Admission is mandatory in the runtime path | |
| 3 | TASK-0035 | Evidence current-set and Defect semantics are correct | SG-6 |
| 4 | TASK-0036 | Repair PlanIR runs through the same Scheduler | SG-7 |
| 5 | TASK-0037 | SQLite durability and real process restart work | |
| 6 | TASK-0038 | Generic Goal CLI and GoalExecution operation path | SG-8 |
| 7 | TASK-0039 | Deterministic M1 end-to-end experiment and baseline | SG-9 |
| 8 | TASK-0040 | Small real-Agent pilot under M1 boundaries | SG-10 |

# 6. Stage Gates

## SG-5: Executable verification

- Every selected Gate has a real GateRun.
- A missing or failed Gate blocks Node/Goal success.
- Evidence is generated from GateRun, not hand-authored as passed.

## SG-6: Enforced trust and current Evidence

- Every runtime grant traces to Capability Admission.
- There are no synthetic PolicyDecision or grant records in the default path.
- Completion evaluates only the resolved current Evidence set.
- Superseded history remains auditable but cannot incorrectly block or satisfy
  completion.

## SG-7: Unified repair

- Initial and repair Plan versions both create PlanExecution records.
- The Scheduler executes repair and re-verification nodes.
- No orchestrator calls NodeExecutor directly.
- Reused Evidence is validated against unchanged digests.

## SG-8: Durable generic operation

- The process can exit after at least one side effect and resume from SQLite.
- Completed Nodes are not repeated.
- Generic Goal CLI commands operate without fixture-specific imports.
- GoalExecution links all PlanExecution versions and repair cycles.

## SG-9: Deterministic M1

Twenty consecutive deterministic runs must have:

- zero false completion;
- 100% selected-Gate execution integrity;
- 100% required-Claim current coverage at completion;
- zero unadmitted side effects;
- zero repair-boundary escapes;
- zero duplicate effects after resume;
- stable normalized semantic results.

## SG-10: Real-Agent pilot

- At least one real Planner path and one real Executor path run through M1.
- Planner output is always admitted or rejected before execution.
- Safety invariants remain perfect even when quality varies.
- Token, cost, latency, failure classes, and repair cycles are recorded.

# 7. Core metrics

The milestone uses six non-negotiable metrics.

| Metric | Formula | Required result |
|---|---|---:|
| False Completion Count | completed runs lacking all required current Evidence | 0 |
| Gate Execution Integrity | selected Gates with terminal GateRun / selected Gates | 100% |
| Current Claim Coverage | required Claims with current passed Evidence / required Claims | 100% |
| Capability Admission Coverage | executed side effects with admitted grant / executed side effects | 100% |
| Repair Boundary Compliance | changed repair paths inside approved boundary / all repair paths | 100% |
| Resume Duplicate Effect Count | repeated committed effects after restart | 0 |

Efficiency is measured, but it must never override correctness:

```text
Weighted Verification Saving
  = 1 - selected_verification_cost / full_verification_cost
```

The cost vector should include wall time, model calls, tokens, tool calls, and
monetary cost where available.

# 8. Experiment ladder

## E0: Existing fixture stability

Run the existing deterministic fixture repeatedly and normalize UUID/time fields.
This gives a baseline only; it does not prove M1.

## E1: Actual Gate execution

Use deterministic runners and assert GateRun and Evidence lineage.

## E2: Enforced Capability Admission

Attempt approved, widened, expired, wrong-role, wrong-node, and path-escape
actions.

## E3: Unified repair

Create a deterministic failure, compile PlanIR v2, and run it through Scheduler.

## E4: Process restart

Terminate after one Node commits an idempotent effect. Restart a new process and
finish without duplicate execution.

## E5: Deterministic generic Goal operation

Use the generic CLI and all M1 boundaries without a model.

## E6: Real Agent pilot

Open uncertainty one dimension at a time:

1. real Planner + deterministic Executor;
2. deterministic Planner + real Executor;
3. real Planner + real Executor only after the first two are safe.

# 9. Non-goals

M1 does not require:

- distributed queues or multi-host scheduling;
- production credentials;
- irreversible external effects;
- arbitrary dynamic recursive Agent spawning;
- visual workflow building;
- long-term Memory;
- framework self-iteration;
- automatic deployment;
- broad model/provider support.

# 10. Stop conditions

Stop and create a Defect/Handoff when:

- a Gate is selected but cannot produce a terminal GateRun;
- any runtime privilege exists without an AdmissionDecision;
- a repair path bypasses Scheduler;
- a restart repeats a committed effect;
- Completion accepts missing, stale, superseded, or fabricated Evidence;
- the same Defect recurs after the repair-cycle budget;
- a Task can pass only by weakening an approved Claim or Gate;
- fixture-only logic leaks into the generic Goal service;
- nondeterminism prevents reliable Evidence reuse.

# 11. Completion statement

The project may claim **M1 minimal live dynamic loop** only after `TASK-0039`
passes EvidenceGate.

`TASK-0040` is the first model-driven pilot. It evaluates model quality but must
not redefine the M1 safety boundary.
