---
type: Handoff
id: HANDOFF-TASK-0036-0001
schema_version: awkp/0.1
title: TASK-0036 unified scheduler repair handoff
description: Producer handoff for independent EvidenceGate review of GoalExecution lineage and Scheduler-driven repair execution.
status: review
owner: agent:codex-dynamic-kernel-operator
task_id: TASK-0036
created_by: agent:codex-dynamic-kernel-operator
created_at: 2026-06-26T07:36:14.797985Z
---

# TASK-0036 Handoff

Producer: `agent:codex-dynamic-kernel-operator`

State requested: `review`

## Summary

TASK-0036 introduces a minimal `GoalExecutionRecord` and service, links
PlanExecution records to one GoalExecution, records v2 parent lineage and reused
Evidence, and routes the deterministic repair PlanIR through
`StaticPlanScheduler`. The fixture no longer calls the repair NodeExecutor
directly.

## Evidence

- `work/tasks/TASK-0036/evidence/implementation-report.json`
- `work/tasks/TASK-0036/evidence/verification-report.json`
- `work/tasks/TASK-0036/evidence/dynamic-fixture-report.json`

## Verification

- `uv run python -B -m unittest tests.test_plan_execution tests.test_dynamic_fixture -v`
- `uv run python -B scripts/check.py --lint`
- `uv run python -B scripts/lint_awkp.py`
- `git diff --check`
- `uv run python -B scripts/check.py --test`
- `uv run python -B scripts/check.py`
- `uv run python -B -m ahra.cli fixture dynamic-repair --fixture tests/fixtures/dynamic-goal-project --report work/tasks/TASK-0036/evidence/dynamic-fixture-report.json`

## Reviewer Notes

- The producer has not marked the task completed. Completion requires
  independent EvidenceGate review.
- The implementation remains in-memory by design; SQLite persistence is
  explicitly deferred to TASK-0037.
- The dynamic fixture reports one GoalExecution with two PlanExecution refs,
  one repair cycle, Scheduler dispatch coverage 1.0, and no open Defects.
- The v2 PlanExecution reuses unchanged acceptance/security Nodes through
  current GateRun-backed Evidence and executes only repair plus terminal
  reverify Nodes.

## Exact Next Action

Run independent EvidenceGate review for `TASK-0036` unified repair Scheduler
criteria.
