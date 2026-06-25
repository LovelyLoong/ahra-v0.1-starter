---
type: Handoff
id: HANDOFF-TASK-0029-0001
schema_version: awkp/0.1
title: TASK-0029 static PlanIR scheduler ready for review
description: Producer handoff for static PlanIR DAG scheduling, PlanExecution and NodeRun state wiring, checkpoint recovery, cancellation, projection, and reconciler checks.
status: active
owner: agent:codex-dynamic-kernel-operator
source_refs: [../task.md, ../state.json, ../artifact-manifest.json, ../evidence-manifest.json]
evidence_refs: [EVD-TASK-0029-0001, EVD-TASK-0029-0002, EVD-TASK-0029-0003]
confidence: reviewed
last_verified_at: 2026-06-25T13:37:32Z
review_after: 2026-09-25T00:00:00Z
tags: [handoff, task-0029, plan-execution, scheduler]
---

# Summary

TASK-0029 implementation is ready for independent verifier review and EvidenceGate. The producing agent did not mark the task completed.

# Completed Work

- Added `src/ahra/plan_execution.py` with PlanExecution, NodeRun, checkpoint, static scheduler, AWKP projection, and reconciler records.
- Enforced admitted PlanIR digest binding, CAS writes, lease/fencing checks, DAG dependency scheduling, concurrency limit, budget snapshots, wall-clock budget timeout, deadline failure, retry attempts, checkpoint resume, and cancellation propagation.
- Invoked VerificationService at declared node/goal boundaries while leaving final Task completion to EvidenceGate.
- Exported the new API and added lint coverage for the new module.
- Added `tests/test_plan_execution.py` with 9 focused tests.

# Verification

- `.venv/Scripts/python.exe -B -m unittest tests.test_plan_execution -v`: passed, 9 tests OK.
- `.venv/Scripts/python.exe -B scripts/check.py`: passed, 133 tests OK with 2 environment skips.
- `git diff --check`: passed with no output.

# Known Limits

- The PlanExecution store is in-memory reference infrastructure, not a distributed queue or remote worker runtime.
- Dynamic Planner adapter and bounded replan remain TASK-0030 scope.
- TASK-0032 remains responsible for legacy cleanup after the new path passes end-to-end acceptance.

# Next Action

Run independent EvidenceGate review for TASK-0029 at the current `state_version`. Do not mark the task completed from this handoff alone.
