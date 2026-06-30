---
type: EvidenceReport
id: ART-TASK-0062-0002
schema_version: awkp/0.1
title: TASK-0062 IntentDraft contract report
description: Producer evidence for the IntentDraft schema, domain round-trip, and example intent.
status: review
owner: agent:codex-implementation
created_at: 2026-06-30T10:00:00Z
created_by: agent:codex-implementation
---

# IntentDraft Contract Report

TASK-0062 implementation adds `IntentDraft` as the Phase 1 input contract.

Implemented:
- `contracts/schemas/intent-draft.schema.json` validates `apiVersion`, `kind`, metadata, abstract goal, constraints, capability needs, context, and risk hints.
- `src/ahra/intent_draft.py` provides frozen domain objects for `IntentDraft`, `IntentCapabilityNeed`, and `IntentConstraint`.
- `examples/intents/phase1-example-intent.yaml` is the canonical example intent.
- `tests/test_intent_draft.py` covers schema validation, domain round-trip, and additive extension tolerance.

Boundary:
- This task defines the intent contract only. It does not admit, approve, or execute a GoalExecutionRequest.
- Producer evidence is ready for independent EvidenceGate review.
