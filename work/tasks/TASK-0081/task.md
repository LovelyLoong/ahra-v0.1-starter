---
type: WorkItem
id: TASK-0081
schema_version: awkp/0.1
title: "Expose formal Workflow A CLI lifecycle"
description: "Add a governed Workflow A CLI/session lifecycle for start, advance, snapshot, draft, admit, and authorize without putting the experimental component on the default path."
context_id: "CTX-workflow-a-cli"
priority: "P1"
risk_level: "R2"
requester: "human:maintainer"
reviewer: "agent:independent-verifier"
created_at: 2026-07-01T11:02:07.534401Z
depends_on: ["TASK-0078"]
input_refs: ["docs/architecture/intent-alignment-workflow.md", "architecture/decisions/ADR-0009-agent-driven-intent-alignment-front-workflow.md", "src/ahra/alignment_session.py"]
output_contract:
  - kind: "ahra/artifact/code-change/0.1"
  - kind: "ahra/evidence/test-report/0.1"
---

# Goal

Add a governed Workflow A CLI/session lifecycle for start, advance, snapshot, draft, admit, and authorize without putting the experimental component on the default path.

# Acceptance criteria

- [ ] CLI exposes Workflow A start, advance, snapshot, draft, admit, and authorize operations with durable session snapshots.
- [ ] draft requires Human Gate 1 approval, admit runs RequestDraftAdmission, and authorize uses ApprovalService so agents cannot freeze a GoalExecutionRequest themselves.
- [ ] The CLI remains explicitly experimental/non-default in component inventory and framework entrypoints until EvidenceGate promotion tasks approve it.
