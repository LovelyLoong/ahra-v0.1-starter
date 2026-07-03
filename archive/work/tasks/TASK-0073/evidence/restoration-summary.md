---
type: Evidence
id: EVD-TASK-0073-RESTORE-0001
schema_version: awkp/0.1
title: TASK-0073 restoration summary
description: Producer evidence for reconstructing TASK-0073 profile-derived scheduler lease budgeting after data loss.
status: current
owner: agent:codex-restoration
source_refs: [../task.md, ../../../../src/ahra/goal_operations.py, ../../../../src/ahra/plan_execution.py, ../../../../examples/goals/dogfood-a-alignment-session.yaml]
confidence: produced
last_verified_at: 2026-07-01T12:30:00Z
review_after: 2026-10-01T00:00:00Z
tags: [task-0073, restoration, lease, budget]
---

# TASK-0073 Restoration Summary

Restored code paths:

- `DEVELOPMENT_BOUNDED_NODE_BUDGET.max_wall_seconds` is 900.
- `GoalOperationService._scheduler` passes
  `_scheduler_lease_ttl_seconds(profile)` instead of a hardcoded 300.
- `_scheduler_lease_ttl_seconds` preserves 300 as the default for profiles
  without a larger default node budget.
- `examples/goals/dogfood-a-alignment-session.yaml` uses a 900 second node
  budget and timeout for `NODE-alignment-session`.

This evidence is a restoration artifact. It does not claim a fresh EvidenceGate
approval.
