---
type: EvidenceReport
id: ART-TASK-0067-0002
schema_version: awkp/0.1
title: TASK-0067 subjective gate runners report
description: Producer evidence for semantic_review and human_approval gate runners.
status: review
owner: agent:codex-implementation
created_at: 2026-06-30T10:00:00Z
created_by: agent:codex-implementation
---

# Subjective Gate Runners Report

TASK-0067 implementation adds real gate runner boundaries for subjective semantic review and human approval.

Implemented:
- `SubjectiveGateDecision` records verdict, confidence, actor, notes, and raw evidence refs.
- `SemanticReviewGateRunner` uses an injected judge provider and maps PASS/FAIL/BLOCKED outcomes into gate execution results.
- `HumanApprovalGateRunner` uses an injected decision provider and blocks until a human approval/rejection is supplied.
- Both runners enforce producer/verifier separation and preserve lineage in result artifacts.
- Human approval decisions preserve `decision_at` on `GateExecutionResult` and the executor-produced `GateRunV2`.

Tests:
- Semantic review maps pass and fail decisions with lineage.
- Human approval blocks without a decision, records the approving actor, and preserves the decision timestamp.
- Producer/verifier identity conflicts fail closed for both semantic review and human approval.

Boundary:
- Providers are injected for deterministic tests; no external model or human system is hidden inside the runner.
- Producer evidence is ready for independent EvidenceGate review.
