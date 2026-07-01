---
type: Handoff
id: HANDOFF-TASK-0080-0001
schema_version: awkp/0.1
title: TASK-0080 producer handoff
description: Producer handoff for task-scoped dogfood artifact and store paths.
owner: agent:codex
status: active
created_by: agent:codex
created_at: 2026-07-01T12:08:30.623896Z
---

# Summary
Moved Workflow A dogfood runtime paths into `work/tasks/TASK-0080/runs/dogfood-a-004`.

# Changes
- `examples/goals/dogfood-a-alignment-session.yaml` now records task-scoped `artifactDir` and SQLite `store.path`.
- `tests/test_goal_operations.py` asserts the dogfood request resolves outside `examples/goals/.ahra`.
- The Goal CLI lifecycle test now covers validate/plan/start/resume/inspect using task-scoped runtime paths.
- A dogfood `goal plan` run materialized artifacts under `work/tasks/TASK-0080/runs/dogfood-a-004/artifacts`.

# Verification
See `evidence/verification-summary.json`.

# Review Boundary
Producer evidence only. Do not mark TASK-0080 completed without independent EvidenceGate review.
