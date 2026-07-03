---
type: WorkItem
id: TASK-0064
schema_version: awkp/0.1
title: RequestDraft admission checks
description: Implement the admission layer that verifies a RequestDraft's digests resolve, capabilities are in the allowed set, and ClaimGraph is structurally valid, rejecting bad drafts with structured reasons before any human authorization step.
context_id: CTX-phase1-intent-closure
priority: P0
risk_level: R2
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-30T10:00:00Z
depends_on: [TASK-0063]
input_refs:
  - ../../../src/ahra/alignment_engine.py
  - ../../../src/ahra/goal_operations.py
  - ../../../src/ahra/capabilities.py
  - ../../../docs/roadmaps/phase1-minimal-loop-intent-roadmap.md
output_contract:
  - kind: request_draft_admission_report
  - kind: verification_summary
  - kind: handoff
---

# Goal

Gate untrusted RequestDrafts before human authorization. Implement the admission
checks (isomorphic to PlanDraft -> PlanIR) that verify every digest resolves to
a real artifact, every capability is in the allowed set and not silently
high-risk, and the ClaimGraph is structurally valid. Reject bad drafts with
structured reasons before wasting a human's time.

# Scope

- Implement `RequestDraftAdmission` in `src/ahra/request_admission.py`.
- Check 1: every digest reference resolves (profile, adapter, release digests).
- Check 2: every declared capability is in the allowed set; high-risk
  capabilities (network, secret, production) without explicit policy fail.
- Check 3: ClaimGraph is structurally valid (no cycles, all claim refs resolve).
- Emit structured rejection reasons on failure.

# Non-goals

- Do not implement the human authorization gate here (that is TASK-0065).
- Do not implement network or subjective gates here (those come later).
- Do not self-complete this task; EvidenceGate decides completion.

# Acceptance criteria

- [ ] `RequestDraftAdmission` performs the three checks (digest resolution,
  capability allowed-set, ClaimGraph validity) and rejects bad drafts with
  structured reasons, covered by tests.
- [ ] A draft with an unknown digest is rejected (test asserts this).
- [ ] A draft declaring a high-risk capability without policy is rejected (test
  asserts this).
- [ ] A draft with a cyclic ClaimGraph is rejected (test asserts this).
- [ ] The domain module imports no adapter/model/cloud dependency (lint passes).
- [ ] Unit tests, lint, and diff checks pass: `.\.venv\Scripts\python.exe -B -m
  unittest tests.test_request_admission -v` and `.\.venv\Scripts\python.exe -B
  scripts\check.py --lint` green.
- [ ] Producer moves TASK-0064 only to review; EvidenceGate decides completion.

# Verification method

- .\.venv\Scripts\python.exe -B -m unittest tests.test_request_admission -v
- .\.venv\Scripts\python.exe -B scripts\check.py --lint
- git diff --check

# Required evidence and handoff

- Publish `evidence/request-draft-admission-report.md` describing the three
  checks and the rejection test outcomes.
- Publish `evidence/verification-summary.json`.
- Publish `handoffs/HANDOFF-0001.md` with one exact next action for TASK-0065.
