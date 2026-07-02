---
type: WorkItem
id: TASK-0086
schema_version: awkp/0.1
title: "Materialize Workflow A session workspace paths on start"
description: "Fix WF-A-FORMAL-001: ahra workflow-a start must materialize or fail closed on the session workspace, artifact, and store parent directories instead of deferring a missing-directory failure to later lifecycle stages. Executed by Workflow B alone through examples/goals/task-0086-workflow-a-start-workspace.yaml."
context_id: "CTX-self-hosting-loop"
priority: "P1"
risk_level: "R1"
requester: "human:maintainer"
reviewer: "agent:independent-verifier"
created_at: 2026-07-02T04:06:50.210378Z
depends_on: ["TASK-0085"]
input_refs: ["src/ahra/workflow_a_cli.py", "src/ahra/cli.py", "artifacts/workflow-a-formal/20260701T222019+0800/formal-supervision-report.md", "examples/goals/task-0086-workflow-a-start-workspace.yaml"]
output_contract:
  - kind: "ahra/artifact/code-change/0.1"
  - kind: "ahra/evidence/test-report/0.1"
---

# Goal

Fix WF-A-FORMAL-001: ahra workflow-a start must materialize or fail closed on the session workspace, artifact, and store parent directories instead of deferring a missing-directory failure to later lifecycle stages. Executed by Workflow B alone through examples/goals/task-0086-workflow-a-start-workspace.yaml.

# Acceptance criteria

- [ ] ahra workflow-a start creates the session workspace, artifact, and store parent directories when missing, or fails closed with a structured error naming the offending path, covered by a test reproducing WF-A-FORMAL-001.
- [ ] The full test suite passes and uv run python -B scripts/check.py --test is recorded in the run evidence.
- [ ] The change is produced by a Workflow B development-bounded GoalExecution with kernel-derived completion, then approved through the AWKP EvidenceGate by an independent verifier.
