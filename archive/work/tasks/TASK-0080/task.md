---
type: WorkItem
id: TASK-0080
schema_version: awkp/0.1
title: "Task-scope dogfood artifact and store paths"
description: "Move Workflow A dogfood GoalExecution artifact/store locations away from examples/goals/.ahra-shaped runtime directories into task-scoped run storage."
context_id: "CTX-dogfood-run-paths"
priority: "P1"
risk_level: "R1"
requester: "human:maintainer"
reviewer: "agent:independent-verifier"
created_at: 2026-07-01T11:01:55.945726Z
depends_on: ["TASK-0078"]
input_refs: ["examples/goals/dogfood-a-alignment-session.yaml", "docs/architecture/framework-entrypoints.md"]
output_contract:
  - kind: "ahra/artifact/code-change/0.1"
  - kind: "ahra/evidence/test-report/0.1"
---

# Goal

Move Workflow A dogfood GoalExecution artifact/store locations away from examples/goals/.ahra-shaped runtime directories into task-scoped run storage.

# Acceptance criteria

- [ ] Dogfood GoalExecution requests do not write artifactDir or store paths under examples/goals/.ahra or example-local runtime state.
- [ ] Artifact and SQLite store paths are derived from the owning task/run identity, with deterministic paths recorded in task evidence or runtime run records.
- [ ] Tests or validation commands prove goal validate/plan/start consume the new task-scoped paths without breaking inspect/resume.
