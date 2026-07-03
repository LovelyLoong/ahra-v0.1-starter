---
type: WorkItem
id: TASK-0078
schema_version: awkp/0.1
title: "Harden Workflow A session gates"
description: "Remove implicit template fallback from alignment_session and enforce ADR-0009 Human Gate 1 plus ApprovalService Gate 2 before Workflow B request freeze."
context_id: "CTX-workflow-a-hardening"
priority: "P0"
risk_level: "R2"
requester: "human:maintainer"
reviewer: "agent:independent-verifier"
created_at: 2026-07-01T11:01:30.989560Z
depends_on: ["TASK-0077"]
input_refs: ["architecture/decisions/ADR-0009-agent-driven-intent-alignment-front-workflow.md", "docs/architecture/intent-alignment-workflow.md"]
output_contract:
  - kind: "ahra/artifact/code-change/0.1"
  - kind: "ahra/evidence/test-report/0.1"
---

# Goal

Remove implicit template fallback from alignment_session and enforce ADR-0009 Human Gate 1 plus ApprovalService Gate 2 before Workflow B request freeze.

# Acceptance criteria

- [ ] Requirement Agent output without an explicit PlanDraft fails closed and cannot be filled from alignment_engine template helpers.
- [ ] Acceptance Agent output without an explicit ClaimGraph fails closed and cannot be filled from alignment_engine template helpers.
- [ ] Alignment Agent convergence leaves the session waiting for human requirement approval; draft_request fails before Human Gate 1.
- [ ] draft_request can request ApprovalService authorization for Gate 2 but cannot freeze a GoalExecutionRequest before human approval.
