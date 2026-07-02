---
type: WorkItem
id: TASK-0088
schema_version: awkp/0.1
title: "Bound real-driver Workflow A turns with a timeout"
description: "Fix WF-A-FORMAL-003: workflow-a advance and draft must bound real AgentDriver calls with a configurable timeout at the alignment session layer, recording a structured timeout failure that keeps the session snapshot consistent and resumable, without changing the AgentDriver port. Executed by Workflow B alone through examples/goals/task-0088-workflow-a-turn-timeout.yaml."
context_id: "CTX-self-hosting-loop"
priority: "P1"
risk_level: "R1"
requester: "human:maintainer"
reviewer: "agent:independent-verifier"
created_at: 2026-07-02T04:07:14.481367Z
depends_on: ["TASK-0085"]
input_refs: ["src/ahra/alignment_session.py", "src/ahra/workflow_a_cli.py", "src/ahra/cli.py", "artifacts/workflow-a-formal/20260701T222019+0800/formal-supervision-report.md", "examples/goals/task-0088-workflow-a-turn-timeout.yaml"]
output_contract:
  - kind: "ahra/artifact/code-change/0.1"
  - kind: "ahra/evidence/test-report/0.1"
---

# Goal

Fix WF-A-FORMAL-003: workflow-a advance and draft must bound real AgentDriver calls with a configurable timeout at the alignment session layer, recording a structured timeout failure that keeps the session snapshot consistent and resumable, without changing the AgentDriver port. Executed by Workflow B alone through examples/goals/task-0088-workflow-a-turn-timeout.yaml.

# Acceptance criteria

- [ ] workflow-a advance and workflow-a draft accept a timeout option with a safe default and abort a hanging driver call with a structured timeout error while the session snapshot stays consistent and resumable, covered by a hanging fake-driver test.
- [ ] src/ahra/ports.py is unchanged by this task.
- [ ] The change is produced by a Workflow B development-bounded GoalExecution with kernel-derived completion, then approved through the AWKP EvidenceGate by an independent verifier.
