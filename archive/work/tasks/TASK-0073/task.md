---
type: WorkItem
id: TASK-0073
schema_version: awkp/0.1
title: Derive development scheduler lease TTL from profile node budget
description: Remove the remaining hardcoded 300 second scheduler lease cap for the development-bounded profile while preserving the 300 second default for M1 deterministic profiles.
context_id: CTX-workflow-b-reliability
priority: P0
risk_level: R3
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-07-01T04:00:00Z
depends_on: [TASK-0072]
input_refs:
  - ../../../src/ahra/goal_operations.py
  - ../../../src/ahra/plan_execution.py
  - ../../../examples/goals/dogfood-a-alignment-session.yaml
output_contract:
  - kind: lease_budget_derivation_report
  - kind: verification_summary
  - kind: handoff
---

# Goal

After TASK-0072, the development dogfood path still inherited a hardcoded
`lease_ttl_seconds=300` from `GoalOperationService._scheduler`. This task makes
the selected profile the authoritative scheduler lease budget source.

# Acceptance Criteria

- [ ] Scheduler lease TTL is derived from the selected profile node budget, not
  a hardcoded 300.
- [ ] `profile/development-bounded` yields a scheduler lease TTL equal to its
  `default_node_budget.max_wall_seconds`, greater than 300.
- [ ] M1 deterministic profiles still resolve to the default 300 second TTL.
- [ ] TASK-0072 invariants still hold: Agent timeout does not exceed lease TTL
  and expired lease handling still reaches terminal failure with defects.
- [ ] The dogfood alignment-session request uses 900 seconds for the real
  development node budget and timeout.
- [ ] Producer moves the task only to review; EvidenceGate decides completion.

# Restoration Note

This directory was reconstructed after the uncommitted TASK-0073 records were
lost by a `git reset --hard` plus `git clean -fd` during dogfood execution.
The restored state is intentionally `review`, not `completed`, until an
independent EvidenceGate run re-approves the restored artifacts.
