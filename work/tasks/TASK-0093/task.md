---
type: WorkItem
id: TASK-0093
schema_version: awkp/0.1
title: "Acceptance-first serial drafting with ClaimGraph digest freeze in alignment_session"
description: "Per ADR-0010, draft_request must run the Acceptance Agent first against the frozen boundary contract, digest-freeze the resulting ClaimGraph, then run the Requirement Agent with read-only visibility of the frozen ClaimGraph. The planner has no write path into acceptance. Executed by Workflow B alone through examples/goals/task-0093-serial-drafting.yaml."
context_id: "CTX-self-hosting-loop"
priority: "P1"
risk_level: "R1"
requester: "human:maintainer"
reviewer: "agent:independent-verifier"
created_at: 2026-07-03T07:30:58.038856Z
depends_on: ["TASK-0092"]
input_refs: ["architecture/decisions/ADR-0010-boundary-contract-acceptance-first-alignment.md", "src/ahra/alignment_session.py", "examples/goals/task-0093-serial-drafting.yaml"]
output_contract:
  - kind: "ahra/artifact/code-change/0.1"
  - kind: "ahra/evidence/test-report/0.1"
---

# Goal

Per ADR-0010, draft_request must run the Acceptance Agent first against the frozen boundary contract, digest-freeze the resulting ClaimGraph, then run the Requirement Agent with read-only visibility of the frozen ClaimGraph. The planner has no write path into acceptance. Executed by Workflow B alone through examples/goals/task-0093-serial-drafting.yaml.

# Acceptance criteria

- [ ] draft_request runs the Acceptance Agent first, reading only the frozen boundary contract; every Claim criterionRefs entry references a boundary entry ID; the ClaimGraph digest is captured in the session snapshot before the Requirement Agent is invoked, covered by tests.
- [ ] The Requirement Agent payload includes the boundary contract and the frozen ClaimGraph as read-only input; the accepted RequestDraft ClaimGraph is byte-identical to the frozen digest, and any divergence rejects the draft as untrusted input, covered by tests.
- [ ] A PlanDraft node claimRef that does not resolve to a claim ID in the frozen ClaimGraph rejects the draft with a structured error naming the unresolved refs, covered by tests.
- [ ] The change is produced by a Workflow B development-bounded GoalExecution with kernel-derived completion, then approved through the AWKP EvidenceGate by an independent verifier.
