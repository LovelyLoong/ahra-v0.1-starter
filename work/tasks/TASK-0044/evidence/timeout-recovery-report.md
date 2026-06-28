---
type: Evidence
id: EVD-TASK-0044-0001
schema_version: awkp/0.1
task_id: TASK-0044
title: TASK-0044 timeout recovery report
description: Producer report for isolated timeout partial-run recovery and GoalExecution finalization fix.
status: review
owner: agent:codex-dynamic-kernel-operator
source_refs:
  - ../task.md
  - ../../../scripts/run_real_agent_pilot.py
  - ../../../src/ahra/real_agent_pilot.py
  - ../../../src/ahra/goal_operations.py
  - ../../../tests/test_real_agent_pilot.py
  - ../../../tests/test_goal_operations.py
evidence_refs:
  - EVD-TASK-0044-0002
confidence: producer-reviewed
last_verified_at: 2026-06-28T07:45:35.840769Z
review_after: 2026-09-28T00:00:00Z
tags: [task-0044, mode-c, timeout-recovery, evidence]
---

# TASK-0044 Timeout Recovery Report

Producer: agent:codex-dynamic-kernel-operator

Status: review requested; not completed by producer.

## Summary

TASK-0044 implements the follow-up required by TASK-0043's approved no-go evidence package. It does not promote Mode C. It fixes the audit/runtime recovery path so an isolated child-process timeout no longer has to publish a synthetic `planner=skipped` and `execution=skipped` run when the child already wrote durable GoalExecution state.

## Code Changes

- `scripts/run_real_agent_pilot.py`: the isolated `subprocess.TimeoutExpired` branch now calls `RealAgentPilotRunner.recover_timeout_run` instead of directly creating a synthetic timeout run.
- `src/ahra/goal_operations.py`: added `finish_active_plan_if_terminal`, a normal service-path helper that finalizes a GoalExecution when its active PlanExecution is already terminal.
- `src/ahra/real_agent_pilot.py`: added partial timeout recovery that loads `goal-run-request.yaml`, inspects `.ahra/goal-control.sqlite3`, finalizes a terminal active PlanExecution, reconstructs Planner status from preserved artifacts, and writes a recovered run-result.
- `tests/test_real_agent_pilot.py` and `tests/test_goal_operations.py`: added regression coverage for recovered timeout state, no-state fallback, script timeout hook routing, and direct GoalExecution finalization.

Code commit: `11a31f51c6a63aa177ce01b3b8b9dfbe6e64613e`

## Behavior

If `goal-run-request.yaml` and `.ahra/goal-control.sqlite3` exist after an isolated timeout, recovery now prefers the durable child-run state. A failed terminal PlanExecution is reflected as a failed recovered run with actual `goalExecutionId`, `planExecutionId`, `goalStatus`, `planStatus`, metrics and failure class.

If durable state is absent, the previous synthetic `runner_timeout` blocked run remains unchanged.

Provider token/cost behavior is unchanged: unavailable provider usage remains `null`, not `0.0`.

## Verification

- Focused tests: 18 passed.
- Full tests: 199 passed, 2 skipped.
- Lint: passed.
- AWKP lint: passed.
- Whitespace diff check: passed.

## Recommendation

Move TASK-0044 to independent EvidenceGate review. Do not treat this as Mode C approval; it is only the recovery/audit fix required before any future authorized combined-mode pilot.
