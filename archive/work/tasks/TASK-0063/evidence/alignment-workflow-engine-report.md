---
type: EvidenceReport
id: ART-TASK-0063-0002
schema_version: awkp/0.1
title: TASK-0063 alignment workflow engine report
description: Producer evidence for the multi-turn IntentDraft to RequestDraft alignment workflow.
status: review
owner: agent:codex-implementation
created_at: 2026-06-30T10:00:00Z
created_by: agent:codex-implementation
---

# Alignment Workflow Engine Report

TASK-0063 implementation adds the multi-turn alignment workflow that transforms an `IntentDraft` into an untrusted `RequestDraft`.

Implemented:
- `src/ahra/alignment_engine.py` models alignment sessions, turns, and deterministic stage advancement.
- `RequestDraft` includes profile refs, runtime refs, ClaimGraph content, PlanDraft content, declared capability policies, and metadata.
- Digest resolution is registry-backed; unknown profile refs fail closed instead of fabricating digests.
- `tests/test_alignment_engine.py` covers multi-turn progression and unknown-profile rejection.

Boundary:
- The alignment engine drafts requests only. Admission and authorization remain separate tasks.
- Producer evidence is ready for independent EvidenceGate review.
