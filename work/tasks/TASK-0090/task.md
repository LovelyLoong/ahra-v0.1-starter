---
type: WorkItem
id: TASK-0090
schema_version: awkp/0.1
title: "First self-hosted improvement through the full A to B loop"
description: "Phase S milestone: a real-driver Workflow A alignment session turns one real project improvement into an authorized frozen GoalExecutionRequest, Workflow B executes it to kernel-derived completion, and the manual-path-as-defect rule becomes binding for subsequent work."
context_id: "CTX-self-hosting-loop"
priority: "P1"
risk_level: "R1"
requester: "human:maintainer"
reviewer: "agent:independent-verifier"
created_at: 2026-07-02T04:07:15.619935Z
depends_on: ["TASK-0086", "TASK-0087", "TASK-0088", "TASK-0089"]
input_refs: ["docs/roadmaps/development-program-overview.md", "src/ahra/workflow_a_cli.py", "examples/goals/dogfood-a-alignment-session.yaml"]
output_contract:
  - kind: "ahra/artifact/code-change/0.1"
  - kind: "ahra/evidence/test-report/0.1"
---

# Goal

Phase S milestone: a real-driver Workflow A alignment session turns one real project improvement into an authorized frozen GoalExecutionRequest, Workflow B executes it to kernel-derived completion, and the manual-path-as-defect rule becomes binding for subsequent work.

# Acceptance criteria

- [ ] The real-driver Workflow A session transcript, the frozen authorized GoalExecutionRequest, and the Workflow B execution evidence are attached as task artifacts, and the request passes admit, authorize, and goal validate.
- [ ] The improvement lands with kernel-derived completion and independent AWKP EvidenceGate approval; no gate asserts anything about dialogue content.
- [ ] The binding rule that new work defaults to the A plus B loop and that manual paths are recorded as loop defects is added to the development program overview.
