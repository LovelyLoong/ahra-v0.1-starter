---
type: WorkItem
id: TASK-0067
schema_version: awkp/0.1
title: Real semantic_review and human_approval gate runners
description: Implement semantic_review and human_approval as real gate runners (not just enum values) so subjective artifacts can pass or fail verification through a recorded gate decision with lineage, while preserving producer not equal to verifier.
context_id: CTX-phase1-intent-closure
priority: P1
risk_level: R2
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-30T10:00:00Z
depends_on: [TASK-0066]
input_refs:
  - ../../../src/ahra/verification.py
  - ../../../src/ahra/goal_operations.py
  - ../../../docs/roadmaps/phase1-minimal-loop-intent-roadmap.md
output_contract:
  - kind: subjective_gate_runners_report
  - kind: verification_summary
  - kind: handoff
---

# Goal

Make subjective judgment verifiable. Today semantic_review and human_approval
are enum values with no implementation. Build them as real gate runners so
artifacts without exit-0 commands (reports, analyses, designs) can pass or fail
verification through a recorded gate decision with lineage, while the
producer != verifier boundary still holds.

# Scope

- Implement `SemanticReviewGateRunner` in `src/ahra/verification.py` that
  invokes an LLM judge against acceptance criteria, records the decision with
  lineage, and maps confidence to PASS/UNCERTAIN/FAIL.
- Implement `HumanApprovalGateRunner` that blocks until a human provides a
  decision via CLI or API, records it with actor and timestamp.
- Both runners satisfy `GateRunnerPort` and are registrable in
  `GateRunnerRegistry`.
- Producer != verifier holds: the judge/human identity must differ from the
  producer identity.

# Non-goals

- Do not collapse producer and verifier identities.
- Do not make semantic_review the only gate (command gates remain primary for
  objective criteria).
- Do not self-complete this task; EvidenceGate decides completion.

# Acceptance criteria

- [ ] `SemanticReviewGateRunner` exists, implements GateRunnerPort, invokes an
  LLM judge, and records decisions with lineage, covered by fixture tests on
  PASS/FAIL routing.
- [ ] `HumanApprovalGateRunner` exists, blocks for human input, records the
  decision with actor and timestamp, covered by tests.
- [ ] Both runners enforce producer != verifier; an attempt to use a producer
  identity as the judge/human is rejected, covered by tests.
- [ ] The domain module imports no adapter/model/cloud dependency in the port
  definitions (implementations may adapt, lint passes).
- [ ] Unit tests, lint, and diff checks pass: `.\.venv\Scripts\python.exe -B -m
  unittest tests.test_verification -v` and `.\.venv\Scripts\python.exe -B
  scripts\check.py --lint` green.
- [ ] Producer moves TASK-0067 only to review; EvidenceGate decides completion.

# Verification method

- .\.venv\Scripts\python.exe -B -m unittest tests.test_verification -v
- .\.venv\Scripts\python.exe -B scripts\check.py --lint
- git diff --check

# Required evidence and handoff

- Publish `evidence/subjective-gate-runners-report.md` describing the two
  runners, the fixture PASS/FAIL tests, and the producer != verifier enforcement.
- Publish `evidence/verification-summary.json`.
- Publish `handoffs/HANDOFF-0001.md` with one exact next action for TASK-0068.
