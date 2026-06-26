---
type: Handoff
id: HANDOFF-TASK-0037-0001
schema_version: awkp/0.1
title: TASK-0037 SQLite control-plane recovery handoff
description: Producer handoff for independent EvidenceGate review of local SQLite persistence and process restart recovery.
status: review
owner: agent:codex-dynamic-kernel-operator
task_id: TASK-0037
created_by: agent:codex-dynamic-kernel-operator
created_at: 2026-06-26T08:53:08.585615Z
---

# TASK-0037 Handoff

Producer: `agent:codex-dynamic-kernel-operator`

State requested: `review`

## Summary

TASK-0037 introduces `SQLiteControlStore`, a local durable control-plane profile
for GoalExecution, PlanExecution, NodeRun, Checkpoint, idempotency and recovery
events. The Scheduler can now resume a committed executor result from SQLite and
finish declared Gate verification without re-invoking the NodeExecutor.

## Evidence

- `work/tasks/TASK-0037/evidence/implementation-report.json`
- `work/tasks/TASK-0037/evidence/verification-report.json`
- `work/tasks/TASK-0037/evidence/subprocess-crash-resume-report.json`
- `work/tasks/TASK-0037/evidence/subprocess-terminal-resume-report.json`

## Verification

- `uv run python -B -m unittest tests.test_sqlite_control_store -v`
- `uv run python -B -m unittest tests.test_plan_execution -v`
- `uv run python -B -m unittest tests.test_dynamic_fixture -v`
- `uv run python -B scripts/check.py`
- `uv run python -B scripts/check.py --lint`
- `git diff --check`
- `uv run python -B -m ahra.sqlite_recovery_fixture --phase crash-after-idempotency ...`
- `uv run python -B -m ahra.sqlite_recovery_fixture --phase stop-after-terminal ...`

## Reviewer Notes

- The producer has not marked the task completed. Completion requires
  independent EvidenceGate review.
- The SQLite schema version is `ahra/sqlite-control-store/0.1`.
- Crash-after-effect recovery reported `duplicateEffectCount=0`,
  `resumeExecutorCallCount=0`, `checkpointLoadSuccess=true`, and one recovered
  idempotent NodeRun.
- Terminal-before-next-dispatch recovery reported `duplicateEffectCount=0`,
  `resumeExecutorCallCount=0`, and no recovered NodeRun because the completed
  NodeRun was already terminal in SQLite.
- The local profile remains single-host SQLite and does not claim distributed
  exactly-once semantics.

## Exact Next Action

Run independent EvidenceGate review for `TASK-0037` SQLite persistence,
transaction/CAS, recovery, lineage, and subprocess restart criteria.
