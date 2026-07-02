---
type: WorkItem
id: TASK-0084
schema_version: awkp/0.1
title: "Smoke Workflow A handoff to Workflow B"
description: "Prove the experimental Workflow A CLI can produce an authorized GoalExecutionRequest whose output is consumable by Workflow B validate, plan, and start using a documented fixture/review-bypass conformance smoke."
context_id: "CTX-component-lifecycle"
priority: "P1"
risk_level: "R1"
requester: "human:maintainer"
reviewer: "agent:independent-verifier"
created_at: 2026-07-02T01:11:01.903404Z
depends_on: ["TASK-0083", "TASK-0081", "TASK-0082"]
input_refs: ["src/ahra/workflow_a_cli.py", "src/ahra/cli.py", "tests/test_cli.py", "docs/architecture/framework-entrypoints.md", "docs/architecture/component-inventory.json"]
output_contract:
  - kind: "ahra/artifact/code-change/0.1"
  - kind: "ahra/evidence/test-report/0.1"
---

# Goal

Prove the experimental Workflow A CLI can produce an authorized GoalExecutionRequest whose output is consumable by Workflow B validate, plan, and start using a documented fixture/review-bypass conformance smoke.

# Acceptance criteria

- [ ] Workflow A fixture/review-bypass lifecycle produces an authorized GoalExecutionRequest and records that live human/model review is bypassed for conformance only.
- [ ] The authorized request passes Workflow B goal validate, goal plan, and goal start in automated regression or equivalent task evidence.
- [ ] The result does not claim default-visible promotion or full human-gated production readiness.
