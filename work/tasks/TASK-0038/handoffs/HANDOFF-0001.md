---
type: Handoff
id: HANDOFF-TASK-0038-0001
schema_version: awkp/0.1
task_id: TASK-0038
title: TASK-0038 review handoff
description: Producer handoff for independent TASK-0038 EvidenceGate review.
owner: agent:codex-dynamic-kernel-operator
from: agent:codex-dynamic-kernel-operator
to: agent:independent-verifier
created_at: 2026-06-26T09:38:02Z
status: review
---

# TASK-0038 Review Handoff

Producer implementation is ready for independent review.

## Exact Next Action

Run independent EvidenceGate review for TASK-0038 using:

- `work/tasks/TASK-0038/task.md`
- `work/tasks/TASK-0038/state.json`
- `work/tasks/TASK-0038/artifact-manifest.json`
- `work/tasks/TASK-0038/evidence-manifest.json`
- `work/tasks/TASK-0038/evidence/implementation-report.md`
- `work/tasks/TASK-0038/evidence/metrics.json`
- `work/tasks/TASK-0038/evidence/sg8-smoke/sg8-smoke-summary.json`

## Producer Verification

- `uv run python -B -m unittest tests.test_goal_operations tests.test_cli`
- `uv run python -B scripts/check.py --test`
- `uv run python -B scripts/lint_contracts.py`
- `uv run python -B scripts/check.py --lint`
- `uv run ahra goal validate examples/m1/goal-run-request.yaml`
- `git diff --check`
- `uv run python -B scripts/check.py`

## Review Focus

- Confirm CLI handlers only call `GoalOperationService`.
- Confirm `goal validate` does not import `ahra.dynamic_fixture`.
- Confirm `goal resume` uses SQLite durable GoalExecution identity and not chat history.
- Confirm unknown profile, adapter, runtime and store refs fail closed.
- Confirm fixture command remains explicit regression-only, not the default docs path.

Producer has not marked TASK-0038 completed.
