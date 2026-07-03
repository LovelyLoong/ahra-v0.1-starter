---
type: WorkItem
id: TASK-0055
schema_version: awkp/0.1
title: AWKP EvidenceGate reviews kernel evidence lineage
description: Upgrade the AWKP EvidenceGate so command-backed acceptance criteria are approved only when they reference kernel CommandGateRunner EvidenceV2 with valid gate-run lineage and fingerprint, instead of trusting a self-reported command status.
context_id: CTX-verification-teeth
priority: P0
risk_level: R2
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-29T10:00:00Z
depends_on: [TASK-0054]
input_refs:
  - ../../../src/ahra/evidence_gate.py
  - ../../../src/ahra/evidence_v2.py
  - ../../../scripts/lint_awkp.py
output_contract:
  - kind: gate_lineage_review_report
  - kind: verification_summary
  - kind: handoff
---

# Goal

Fuse the two verification surfaces. The AWKP EvidenceGate is structurally strong
(producer != verifier, SHA-256 recompute, criterion to evidence mapping, CAS,
append-only) but it trusts the verifier-agent's self-reported `command.status`.
Upgrade it so that, for command-backed criteria, approval requires the
referenced evidence to be kernel `CommandGateRunner` `EvidenceV2` with valid
gate-run lineage and a matching fingerprint. Command execution still happens in
exactly one place (the kernel runner); the AWKP gate stays offline and
stdlib-only and becomes a lineage reviewer.

# Scope

- In `src/ahra/evidence_gate.py`, on the `approve` path, require command-backed
  criteria to reference an `EvidenceV2` record that carries gate-run lineage and
  whose stored fingerprint matches, rather than trusting a self-reported
  `command.status`.
- Fail closed when a criterion claims passed but has no valid gate-run lineage,
  or when the fingerprint is stale or mismatched.
- Preserve all existing EvidenceGate guarantees (producer != verifier, SHA-256
  recompute, CAS state version, append-only events, blocker handling).
- Keep `evidence_gate.py` offline and stdlib-only (no execution / subprocess
  dependency).

# Non-goals

- Do not make the AWKP gate execute commands itself.
- Do not build the end-to-end fail-then-fix demonstration here (TASK-0056).
- Do not weaken any existing EvidenceGate invariant.
- Do not self-complete this task; EvidenceGate decides completion.

# Acceptance criteria

- [ ] On `approve`, a command-backed criterion is accepted only when its
  referenced evidence carries valid gate-run lineage and a matching fingerprint.
- [ ] A report that claims a command-backed criterion passed but provides no
  valid gate-run lineage causes an `EvidenceGateError` (fail closed), covered by
  a test.
- [ ] A stale or mismatched fingerprint on the referenced evidence causes the
  gate to fail closed, covered by a test.
- [ ] The existing guarantees still hold: producer != verifier rejection,
  artifact SHA-256 recompute, CAS state_version check, and append-only event
  emission (regression tests pass).
- [ ] `src/ahra/evidence_gate.py` introduces no execution / subprocess
  dependency and remains stdlib-only.
- [ ] `.\.venv\Scripts\python.exe -B scripts\lint_awkp.py` passes.
- [ ] Targeted tests, lint, and diff checks pass, or any failure is recorded as
  a blocker with exact command output.
- [ ] Producer moves TASK-0055 only to review; EvidenceGate decides completion.

# Verification method

- .\.venv\Scripts\python.exe -B -m unittest tests.test_evidence_gate -v
- .\.venv\Scripts\python.exe -B scripts\lint_awkp.py
- .\.venv\Scripts\python.exe -B scripts\check.py --lint
- git diff --check

# Required evidence and handoff

- Publish `evidence/gate-lineage-review-report.md` describing the lineage and
  fingerprint checks and the fail-closed cases.
- Publish `evidence/verification-summary.json`.
- Publish `handoffs/HANDOFF-0001.md` with one exact next action for TASK-0056.
