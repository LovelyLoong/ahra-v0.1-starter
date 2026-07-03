---
type: WorkItem
id: TASK-0068
schema_version: awkp/0.1
title: End-to-end Phase 1 intent-to-completion demonstration (simple Goal first)
description: Demonstrate the full Phase 1 flow end-to-end with one simple, objectively verifiable Goal - abstract intent through alignment, admission, authorization, and autonomous execution to completion - validating the integrated chain before the comprehensive Phase 1 verification.
context_id: CTX-phase1-intent-closure
priority: P0
risk_level: R2
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-30T10:00:00Z
depends_on: [TASK-0067]
input_refs:
  - ../../../src/ahra/intent_draft.py
  - ../../../src/ahra/alignment_engine.py
  - ../../../src/ahra/request_admission.py
  - ../../../src/ahra/approval_service.py
  - ../../../src/ahra/goal_operations.py
  - ../../../docs/roadmaps/phase1-minimal-loop-intent-roadmap.md
output_contract:
  - kind: phase1_e2e_demonstration_report
  - kind: verification_summary
  - kind: handoff
---

# Goal

Prove the Phase 1 chain works end-to-end with a simple objective Goal. Flow an
abstract human intent through alignment, RequestDraft admission, human
authorization, and autonomous execution to completion. Use a simple,
objectively-verifiable Goal first (e.g. a small framework chore) to validate
integration before TASK-0069's comprehensive Phase 1 verification.

# Scope

- Pick one simple, objectively-verifiable real Goal (small self-contained
  framework task).
- Execute the full sequence: IntentDraft -> alignment (TASK-0063) ->
  RequestDraft -> admission (TASK-0064) -> waiting_auth -> human approval
  (TASK-0065) -> frozen GoalExecutionRequest -> autonomous execution (via
  57-61 path) -> completion.
- Capture the run so it is reproducible and encoded as a non-skipped test.
- Confirm no step was hand-patched or bypassed; all transitions went through
  the governed components.

# Non-goals

- Do not require the Goal to involve network access or subjective judgment (save
  those for TASK-0069's comprehensive tests).
- Do not weaken any capability / gate / authorization boundary to make it pass.
- Do not self-complete this task; EvidenceGate decides completion.

# Acceptance criteria

- [ ] One simple objective Goal flows IntentDraft -> alignment -> admission ->
  approval -> autonomous execution -> completion, captured as evidence.
- [ ] Every step used the governed components (alignment engine, admission,
  ApprovalService, 57-61 orchestrator); no hand-patching, verifiable from logs.
- [ ] The authorization gate was explicitly invoked; the Goal did not freeze
  without approval, covered by the run log.
- [ ] The end-to-end path is encoded as a non-skipped automated test.
- [ ] `.\.venv\Scripts\python.exe -B scripts\check.py` (full lint + test) passes.
- [ ] Producer moves TASK-0068 only to review; EvidenceGate decides completion.

# Verification method

- .\.venv\Scripts\python.exe -B -m unittest tests.test_phase1_e2e -v
- .\.venv\Scripts\python.exe -B scripts\check.py
- git diff --check

# Required evidence and handoff

- Publish `evidence/phase1-e2e-demonstration-report.md` showing the full
  intent-to-completion sequence, proof that every step was governed, and the
  explicit authorization.
- Publish `evidence/verification-summary.json`.
- Publish `handoffs/HANDOFF-0001.md` with one exact next action for TASK-0069.
