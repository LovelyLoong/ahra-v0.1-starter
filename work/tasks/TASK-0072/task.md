---
type: WorkItem
id: TASK-0072
schema_version: awkp/0.1
title: Fix lease/timeout budget-sinking and terminal-failure fallout for real Agent nodes
description: Align real Agent node lease and timeout budgets, and make lease expiry converge to terminal structured failure instead of a zombie running state.
context_id: CTX-workflow-b-reliability
priority: P0
risk_level: R3
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-07-01T02:30:00Z
depends_on: [TASK-0071]
input_refs:
  - ../../../src/ahra/plan_execution.py
  - ../../../src/ahra/goal_operations.py
  - ../../../src/ahra/reference_runner/bounded_task.py
  - ../../../src/ahra/sqlite_control_store.py
  - ../../../examples/goals/dogfood-a-alignment-session.yaml
output_contract:
  - kind: lease_timeout_fix_report
  - kind: verification_summary
  - kind: handoff
---

# Goal

The first real dogfood run exposed two framework defects:

- NodeRun lease and TaskHarness agent timeout budgets could diverge, so the real
  Agent could continue under a longer harness timeout after the scheduler lease
  expired.
- Lease expiry on a non-terminal NodeRun could remain a warning and mask the
  real timeout cause with a bare `lease expired` error.

# Acceptance Criteria

- [ ] The NodeRun lease TTL and TaskHarness attempt/run timeouts are derived from
  a single authoritative node budget; a test asserts Agent timeout is never
  greater than node lease TTL for the same node.
- [ ] A non-terminal expired NodeRun lease reaches terminal failure with a
  structured failure class such as `node_lease_expired` or `agent_timeout`.
- [ ] PlanExecution and GoalExecution converge to terminal state rather than
  remaining `running`.
- [ ] The surfaced failure preserves the Agent-timeout cause instead of only
  `lease expired`.
- [ ] `reconcile_plan_execution` flags expired RUNNING node leases as terminal
  failure risk rather than a mere warning.
- [ ] Existing lease/fencing/recovery tests still pass.
- [ ] `src/ahra/plan_execution.py` imports no adapter/model/cloud dependency.
- [ ] Producer moves the task only to review; EvidenceGate decides completion.

# Restoration Note

This directory was reconstructed after the uncommitted TASK-0072 records were
lost by a `git reset --hard` plus `git clean -fd` during dogfood execution.
The restored state is intentionally `review`, not `completed`, until an
independent EvidenceGate run re-approves the restored artifacts.
