---
type: EvidenceReport
id: ART-TASK-0065-0002
schema_version: awkp/0.1
title: TASK-0065 ApprovalService report
description: Producer evidence for waiting_auth approval, freeze, and self-authorization rejection.
status: review
owner: agent:codex-implementation
created_at: 2026-06-30T10:00:00Z
created_by: agent:codex-implementation
---

# ApprovalService Report

TASK-0065 implementation adds the authorization boundary between accepted RequestDrafts and frozen GoalExecutionRequests.

Implemented:
- `src/ahra/approval_service.py` records `waiting_auth` approval requests.
- `src/ahra/ports.py` declares the actual ApprovalService workflow contract: request authorization, approve/reject, freeze, status, get, and events.
- Approval requires a human actor and rejects producer self-authorization.
- Frozen GoalExecutionRequests can only be produced from approved records.
- Approval events preserve a small audit trail for request, grant, reject, and freeze operations.

Tests:
- Runtime Protocol check verifies `ApprovalService` satisfies the declared Port and can be driven through the Port.
- Unapproved freeze is rejected.
- Producer cannot self-authorize.
- Human approval freezes a GoalExecutionRequest.

Boundary:
- This is an explicit authorization service, not an EvidenceGate completion claim.
- Producer evidence is ready for independent EvidenceGate review.
