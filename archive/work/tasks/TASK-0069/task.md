---
type: WorkItem
id: TASK-0069
schema_version: awkp/0.1
title: Phase 1 comprehensive integration verification
description: The final, most complete verification of Phase 1 - integrate all deliverables (IntentDraft through subjective gates) and execute a comprehensive test suite covering objective Goals, network-requiring Goals, and subjectively-judged Goals, proving the full intent-closure loop is production-ready.
context_id: CTX-phase1-intent-closure
priority: P0
risk_level: R3
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-30T10:00:00Z
depends_on: [TASK-0068]
input_refs:
  - ../../../src/ahra/intent_draft.py
  - ../../../src/ahra/alignment_engine.py
  - ../../../src/ahra/request_admission.py
  - ../../../src/ahra/approval_service.py
  - ../../../src/ahra/capabilities.py
  - ../../../src/ahra/verification.py
  - ../../../src/ahra/goal_operations.py
  - ../../../docs/roadmaps/phase1-minimal-loop-intent-roadmap.md
output_contract:
  - kind: phase1_comprehensive_verification_report
  - kind: verification_summary
  - kind: handoff
---

# Goal

The comprehensive, final validation that Phase 1 is complete and production-ready.
Integrate all Phase 1 deliverables (IntentDraft contract through subjective gate
runners) and execute a complete test suite that covers:
- Objective Goals (command-gate-verified)
- Network-requiring Goals (governed network.access)
- Subjectively-judged Goals (semantic_review / human_approval)
- Authorization boundary enforcement (no self-authorization)
- End-to-end intent-to-completion loops

This is the task with the MOST COMPLETE acceptance criteria. Every earlier task
(0062-0068) had simplified unit-boundary verification; this task proves the
integrated system works.

# Scope

- Build a comprehensive integration test suite that exercises all Phase 1 paths.
- Test scenario 1: Objective Goal (filesystem writes, command gates only).
- Test scenario 2: Network-requiring Goal (governed network.access, audit trail).
- Test scenario 3: Subjectively-judged Goal (semantic_review gate, producer !=
  judge).
- Test scenario 4: Authorization boundary (attempt to freeze without approval
  fails, attempt to self-authorize fails).
- Test scenario 5: Multi-turn alignment (refining scope, rejecting
  out-of-envelope requests).
- Capture all runs as non-skipped tests; publish comprehensive evidence report.

# Non-goals

- Do not weaken any boundary to make tests pass; if a test fails, the
  deliverable is incomplete.
- Do not self-complete this task; EvidenceGate decides completion.

# Acceptance criteria

- [ ] Test scenario 1 (objective Goal) passes: IntentDraft -> alignment ->
  admission -> approval -> execution with command gates only -> completion,
  non-skipped test.
- [ ] Test scenario 2 (network Goal) passes: network.access is admitted with
  audit, execution succeeds, evidence captures network summary, non-skipped test.
- [ ] Test scenario 3 (subjective Goal) passes: semantic_review gate judges
  artifact, producer != judge enforced, decision recorded with lineage,
  non-skipped test.
- [ ] Test scenario 4 (authorization boundary) passes: freeze without approval
  is rejected, self-authorization is rejected, non-skipped tests.
- [ ] Test scenario 5 (multi-turn alignment) passes: alignment engine refines
  scope over multiple turns, rejects out-of-envelope request with structured
  reason, non-skipped test.
- [ ] All Phase 1 components integrate without patching: IntentDraft,
  AlignmentWorkflowEngine, RequestDraftAdmission, ApprovalService,
  network.access gate, SemanticReviewGateRunner, HumanApprovalGateRunner, 57-61
  orchestrator.
- [ ] `.\.venv\Scripts\python.exe -B scripts\check.py` (full lint + all tests)
  passes with zero errors.
- [ ] A comprehensive evidence report documents all five scenarios with concrete
  artifacts, logs, and audit trails.
- [ ] Producer moves TASK-0069 only to review; EvidenceGate decides completion.

# Verification method

- .\.venv\Scripts\python.exe -B -m unittest tests.test_phase1_comprehensive -v
- .\.venv\Scripts\python.exe -B scripts\check.py
- git diff --check

# Required evidence and handoff

- Publish `evidence/phase1-comprehensive-verification-report.md` documenting all
  five test scenarios with concrete artifacts, audit trails, and proof of
  boundary enforcement.
- Publish `evidence/verification-summary.json`.
- Publish `handoffs/HANDOFF-0001.md` with the conclusion: Phase 1 is complete,
  or specific gaps remain.
