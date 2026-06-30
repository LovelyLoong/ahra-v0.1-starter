---
type: WorkItem
id: TASK-0065
schema_version: awkp/0.1
title: Human authorization gate (ApprovalService and waiting_auth)
description: Implement the ApprovalService and waiting_auth state so a human must explicitly approve the acceptance criteria and capability boundary before a RequestDraft freezes into an immutable GoalExecutionRequest, preventing Agents from self-authorizing scope.
context_id: CTX-phase1-intent-closure
priority: P0
risk_level: R3
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-30T10:00:00Z
depends_on: [TASK-0064]
input_refs:
  - ../../../src/ahra/request_admission.py
  - ../../../src/ahra/goal_operations.py
  - ../../../docs/roadmaps/phase1-minimal-loop-intent-roadmap.md
output_contract:
  - kind: approval_service_report
  - kind: verification_summary
  - kind: handoff
---

# Goal

Install the safety gate: no Agent can freeze its own acceptance criteria or
capability boundary. Implement `ApprovalService` and the `waiting_auth` state so
a human must explicitly approve a RequestDraft's acceptance and capabilities
before it becomes an immutable GoalExecutionRequest. This is the non-negotiable
boundary that prevents scope creep and self-authorization.

# Scope

- Implement `ApprovalService` in `src/ahra/approval_service.py`.
- Implement the `waiting_auth` state in the AWKP state machine (or Goal state).
- An admitted RequestDraft enters `waiting_auth`; only explicit human approval
  (via a CLI command or API) can freeze it into a GoalExecutionRequest.
- An attempt to freeze without approval is rejected with a clear error.
- Record the approval event with actor and timestamp.

# Non-goals

- Do not implement network or subjective gates here (those come next).
- Do not weaken the producer != verifier boundary.
- Do not self-complete this task; EvidenceGate decides completion.

# Acceptance criteria

- [ ] `ApprovalService` implements the approval workflow: RequestDraft ->
  waiting_auth -> approve -> frozen GoalExecutionRequest, covered by tests.
- [ ] An attempt to freeze a RequestDraft without approval is rejected with a
  clear error, covered by a test.
- [ ] The approval event is recorded with actor and timestamp in an append-only
  log, covered by a test.
- [ ] The domain module imports no adapter/model/cloud dependency (lint passes).
- [ ] Unit tests, lint, and diff checks pass: `.\.venv\Scripts\python.exe -B -m
  unittest tests.test_approval_service -v` and `.\.venv\Scripts\python.exe -B
  scripts\check.py --lint` green.
- [ ] Producer moves TASK-0065 only to review; EvidenceGate decides completion.

# Verification method

- .\.venv\Scripts\python.exe -B -m unittest tests.test_approval_service -v
- .\.venv\Scripts\python.exe -B scripts\check.py --lint
- git diff --check

# Required evidence and handoff

- Publish `evidence/approval-service-report.md` describing the waiting_auth
  flow, the rejection test, and the approval audit trail.
- Publish `evidence/verification-summary.json`.
- Publish `handoffs/HANDOFF-0001.md` with one exact next action for TASK-0066.
