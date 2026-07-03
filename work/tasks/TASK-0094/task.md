---
type: WorkItem
id: TASK-0094
schema_version: awkp/0.1
title: "Deterministic cross-alignment gate with bounded redrafts before RequestDraft admission"
description: "Per ADR-0010, add a deterministic cross-alignment validator that checks referential integrity across boundary entries, Claims, and PlanNodes before Human Gate 2 and RequestDraft admission. Failures fail closed with a structured mismatch report and bounded redraft attempts. Executed by Workflow B alone through examples/goals/task-0094-cross-alignment-gate.yaml."
context_id: "CTX-self-hosting-loop"
priority: "P1"
risk_level: "R1"
requester: "human:maintainer"
reviewer: "agent:independent-verifier"
created_at: 2026-07-03T07:31:15.837984Z
depends_on: ["TASK-0093"]
input_refs: ["architecture/decisions/ADR-0010-boundary-contract-acceptance-first-alignment.md", "docs/architecture/intent-alignment-workflow.md", "src/ahra/alignment_session.py", "examples/goals/task-0094-cross-alignment-gate.yaml"]
output_contract:
  - kind: "ahra/artifact/code-change/0.1"
  - kind: "ahra/evidence/test-report/0.1"
---

# Goal

Per ADR-0010, add a deterministic cross-alignment validator that checks referential integrity across boundary entries, Claims, and PlanNodes before Human Gate 2 and RequestDraft admission. Failures fail closed with a structured mismatch report and bounded redraft attempts. Executed by Workflow B alone through examples/goals/task-0094-cross-alignment-gate.yaml.

# Acceptance criteria

- [ ] A deterministic validator rejects drafts where any must, must_not, or completion_signal boundary entry lacks a covering Claim, any Claim references a free_zone entry, any required Claim lacks a covering PlanNode claimRef, any PlanNode claimRef does not resolve in the frozen ClaimGraph, or any open_question entry remains; each failure class is covered by a unit test.
- [ ] Validation failure fails closed before Human Gate 2: the RequestDraft is rejected with a structured mismatch report recorded in the session snapshot, redraft attempts are bounded, and exhausting the bound terminates the session with a recorded failure instead of silently proceeding, covered by tests.
- [ ] The validator runs in the alignment session exit path ahead of RequestDraftAdmission, and its behavior matches the cross-alignment gate row in docs/architecture/intent-alignment-workflow.md.
- [ ] The change is produced by a Workflow B development-bounded GoalExecution with kernel-derived completion, then approved through the AWKP EvidenceGate by an independent verifier.
