---
type: EvidenceReport
id: ART-TASK-0064-0002
schema_version: awkp/0.1
title: TASK-0064 RequestDraft admission report
description: Producer evidence for RequestDraft digest, capability, and ClaimGraph admission checks.
status: review
owner: agent:codex-implementation
created_at: 2026-06-30T10:00:00Z
created_by: agent:codex-implementation
---

# RequestDraft Admission Report

TASK-0064 implementation adds fail-closed admission for untrusted `RequestDraft` objects before they can become GoalExecutionRequests.

Implemented checks:
- Profile/runtime/adapter refs must match the selected operation profile.
- Runtime, node type, and gate digests must resolve from the trusted local registry, not only from RequestDraft-supplied registry maps.
- ClaimGraph and PlanDraft references must be internally consistent and acyclic.
- Capability requests must be allowed by the profile; high-risk capabilities require declared policy refs.
- Accepted drafts compile through `compile_plan_draft` and return a PlanIR digest.

Tests:
- Unknown digest rejection.
- Trusted-registry mismatch rejection for forged node and gate digests.
- High-risk capability without policy rejection.
- Cyclic ClaimGraph rejection.
- Valid draft acceptance with PlanIR digest.

Boundary:
- Admission does not authorize execution. Approval remains TASK-0065.
- Producer evidence is ready for independent EvidenceGate review.
