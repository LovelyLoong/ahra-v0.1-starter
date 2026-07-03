---
type: WorkItem
id: TASK-0036
schema_version: awkp/0.1
title: Run repair plans through one GoalExecution and the same Scheduler
description: Introduce a durable parent GoalExecution lifecycle and remove direct repair executor calls so initial, repair and re-verification plans use one governed path.
context_id: CTX-ahra-dynamic-kernel
priority: P0
risk_level: R2
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-26T00:00:00Z
depends_on: [TASK-0035]
input_refs:
  - ../../../docs/architecture/goal-execution-lifecycle.md
  - ../../../docs/architecture/plan-ir.md
  - ../../../src/ahra/planning.py
  - ../../../src/ahra/plan_execution.py
  - ../../../src/ahra/dynamic_fixture.py
  - ../../../src/ahra/verification.py
output_contract:
  - kind: goal_execution_record
  - kind: goal_execution_service
  - kind: plan_version_lineage
  - kind: scheduler_driven_repair
  - kind: repair_cycle_enforcement
  - kind: reuse_validation
  - kind: end_to_end_repair_report
---

# Goal

Create one governed GoalExecution that can run PlanIR v1, create a Defect, admit PlanIR v2, schedule repair/reverification Nodes, and complete without any direct NodeExecutor call from orchestration code.

# Why now

The current fixture validates a repair PlanIR but executes the repair Node directly. That bypasses PlanExecution state, Scheduler, lease, budget, checkpoint and terminal goal verification.

# Scope

- Add GoalExecutionRecord and service with explicit state/version and plan lineage.
- Link each PlanExecution to one GoalExecution and one immutable PlanIR version.
- On repair, create PlanIR v2 and PlanExecution v2 instead of mutating v1.
- Dispatch repair, selected Gate and terminal goal verification Nodes through StaticPlanScheduler.
- Record reused unchanged Node/Evidence decisions in PlanExecution v2.
- Resolve Defects only after actual required GateRuns pass.
- Enforce maximum repair cycles, budgets and escalation.
- Remove direct executor.execute calls from dynamic orchestration and fixture code.

# Non-goals

- Do not implement SQLite persistence.
- Do not add generic CLI commands.
- Do not add recursive Agent spawning.
- Do not support more than the bounded repair triggers already defined.

# Architectural invariants

- A PlanIR version is immutable.
- Only one PlanExecution is active for a GoalExecution.
- Repair creates a child PlanExecution with parent plan digest lineage.
- All executable Nodes are Scheduler-dispatched.
- Unchanged work is reused only through current validated Evidence.
- A Defect is not resolved merely because a repair Node returned accepted.
- GoalExecution success comes only from Completion.

# Implementation slices

1. Define GoalExecution schema/state service.
2. Bind PlanExecution to GoalExecution.
3. Add repair transition and PlanExecution v2 creation.
4. Schedule repair and reverify Nodes.
5. Connect Defect lifecycle to Gate results.
6. Migrate deterministic fixture and remove bypass helpers.

# Acceptance criteria

- [ ] A single GoalExecution links initial and repaired PlanExecution records.
- [ ] The repaired PlanIR retains parent_plan_digest and increments version without mutating v1.
- [ ] Repair Node, selected Gate Nodes and terminal Goal verification Node all have Scheduler-created NodeRuns.
- [ ] No dynamic orchestrator or fixture calls NodeExecutor directly.
- [ ] A repair Node success without required Gate success leaves the Defect open and Goal incomplete.
- [ ] Unchanged Nodes are not re-executed, and reused Evidence passes current-set validation.
- [ ] Repair cycles stop at the configured maximum and create a terminal failure or pause/handoff.
- [ ] PlanExecution v2 cannot start if Capability Admission, Plan validation or GateRunner registration fails.
- [ ] SG-7 unified-repair tests and full checks pass.

# Required negative and adversarial cases

- invalid PlanPatch parent digest
- repair Node accepted but reverify Gate failed
- reused Evidence became stale before v2 start
- repair cycle budget exhausted
- second active PlanExecution attempt
- direct executor bypass regression scan
- terminal goal node missing from repaired plan

# Verification method

- python scripts/check.py
- python scripts/lint_awkp.py
- git diff --check
- GoalExecution state/transition tests
- initial-fail to PlanExecution-v2 integration test
- scheduler dispatch lineage assertions
- no-direct-executor-call static regression test
- SG-7 unified-repair review

# Required metrics

- GoalExecution repair cycles
- PlanExecution versions per GoalExecution
- Scheduler-dispatched Nodes / all executed Nodes
- reused Evidence count
- Defect time to resolution
- repair boundary compliance

# Stop conditions

- Stop if repair requires mutating the original PlanIR.
- Stop if any repair or verification Node must bypass Scheduler.
- Stop if GoalExecution can succeed while a linked Defect remains open.

# Required evidence and handoff

- Publish an implementation/change report with exact files, contracts, schema
  versions, migrations, known limitations and unresolved items.
- Preserve deterministic command outputs or structured summaries with content
  digests.
- Map every acceptance criterion to one or more Evidence IDs.
- Record producer Agent Release, Context Manifest, workspace/branch, base
  commit, final commit or rejected patch.
- Publish the required metrics for this Task.
- Create an immutable Handoff with one exact next action when blocked, failed,
  paused or returned for changes.
- The producer must not mark this Task completed; an independent verifier and
  EvidenceGate decide completion.

# Rollback and compatibility

- Do not silently overwrite released contracts or historical events.
- Use a new schema version when field meaning changes or compatibility breaks.
- Keep legacy adapters explicit and outside the default path.
- A rollback must preserve Artifact/Evidence references and explain state
  projection changes.

# Risk and approvals

Risk level: **R2**. This connects multiple state authorities and changes the dynamic repair runtime. Independent review must verify CAS/state lineage and failure recovery.
