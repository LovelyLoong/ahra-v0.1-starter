---
type: Evidence
id: EVD-TASK-0072-RESTORE-0001
schema_version: awkp/0.1
title: TASK-0072 restoration summary
description: Producer evidence for reconstructing TASK-0072 lease and timeout fixes after data loss.
status: current
owner: agent:codex-restoration
source_refs: [../task.md, ../../../../src/ahra/plan_execution.py, ../../../../src/ahra/reference_runner/bounded_task.py, ../../../../src/ahra/sqlite_control_store.py, ../../../../src/ahra/goal_operations.py]
confidence: produced
last_verified_at: 2026-07-01T12:30:00Z
review_after: 2026-10-01T00:00:00Z
tags: [task-0072, restoration, lease, timeout]
---

# TASK-0072 Restoration Summary

Restored code paths:

- `StaticPlanScheduler` now uses `_node_agent_timeout_seconds` and
  `_node_lease_ttl_seconds` so the effective Agent timeout and node lease are
  derived from the same node wall budget.
- Scheduler timeout now records `agent_timeout`, terminal failure refs, and a
  `DefectRecord`.
- Expired RUNNING SQLite NodeRuns without durable idempotency results now fail
  as `node_lease_expired`.
- `reconcile_plan_execution` flags expired RUNNING leases as `error`.
- `BoundedTaskExecutor` caps TaskHarness `ExecutionPolicy` by PlanIR node
  timeout/maxWallSeconds and records the effective policy in result details.

This evidence is a restoration artifact. It does not claim a fresh EvidenceGate
approval.
