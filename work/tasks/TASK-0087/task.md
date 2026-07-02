---
type: WorkItem
id: TASK-0087
schema_version: awkp/0.1
title: "Parse Workflow A alignment outputs in the Codex driver"
description: "Fix WF-A-FORMAL-002: CodexSDKDriver must support the Workflow A expected outputs AlignmentTurnDecision, RequirementDraft, and AcceptanceDraft by prompting for and parsing the corresponding JSON, so real-driver alignment turns stop failing on unsupported output types. Executed by Workflow B alone through examples/goals/task-0087-codex-alignment-outputs.yaml."
context_id: "CTX-self-hosting-loop"
priority: "P1"
risk_level: "R1"
requester: "human:maintainer"
reviewer: "agent:independent-verifier"
created_at: 2026-07-02T04:06:50.997665Z
depends_on: ["TASK-0085"]
input_refs: ["src/ahra/adapters/codex_sdk.py", "src/ahra/alignment_session.py", "artifacts/workflow-a-formal/20260701T222019+0800/formal-supervision-report.md", "examples/goals/task-0087-codex-alignment-outputs.yaml"]
output_contract:
  - kind: "ahra/artifact/code-change/0.1"
  - kind: "ahra/evidence/test-report/0.1"
---

# Goal

Fix WF-A-FORMAL-002: CodexSDKDriver must support the Workflow A expected outputs AlignmentTurnDecision, RequirementDraft, and AcceptanceDraft by prompting for and parsing the corresponding JSON, so real-driver alignment turns stop failing on unsupported output types. Executed by Workflow B alone through examples/goals/task-0087-codex-alignment-outputs.yaml.

# Acceptance criteria

- [ ] CodexSDKDriver returns structured results for expected outputs AlignmentTurnDecision, RequirementDraft, and AcceptanceDraft, and rejects malformed model JSON with a structured error instead of an unhandled crash, covered by fake-client tests.
- [ ] No domain or workflow module imports the Codex SDK; provider prompting and parsing stay behind the AgentDriver port, verified by the existing adapter-dependency lint.
- [ ] The change is produced by a Workflow B development-bounded GoalExecution with kernel-derived completion, then approved through the AWKP EvidenceGate by an independent verifier.
