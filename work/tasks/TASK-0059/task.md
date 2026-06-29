---
type: WorkItem
id: TASK-0059
schema_version: awkp/0.1
title: Build the producer-to-verifier task orchestrator
description: Drive a unit of work from working through review to an EvidenceGate decision automatically, invoking the gate under a distinct verifier identity and handling the changes_requested loop, while preserving producer not equal to verifier.
context_id: CTX-workflow-autonomy
priority: P0
risk_level: R2
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-29T11:00:00Z
depends_on: [TASK-0058]
input_refs:
  - ../../../src/ahra/evidence_gate.py
  - ../../../src/ahra/cli.py
  - ../../../work/tasks/TASK-0045/events.jsonl
  - ../../../docs/architecture/authority-map.md
output_contract:
  - kind: orchestrator_report
  - kind: verification_summary
  - kind: handoff
---

# Goal

Remove the manual producer-to-verifier handoff that causes the "stall." Today
the handoff is two separate hand-run CLI invocations under two actor strings
plus a hand-built report, and a single SHA mismatch forces a fully hand-authored
changes_requested round-trip (see TASK-0045 events 0004->0005->0006->0007).
Build an orchestrator that chains working -> review -> EvidenceGate decision
automatically, calling the gate under a distinct verifier identity and handling
the changes_requested loop, without ever collapsing the producer != verifier
boundary.

# Scope

- Implement an orchestrator that, given a task in working with published
  evidence, drives: request review (via TASK-0057 writer) -> invoke
  `evidence-gate evaluate` under a verifier identity distinct from every
  producer identity -> on approve, reach completed; on request_changes,
  re-claim to working (via TASK-0057 writer) and loop with a bounded retry.
- The verifier identity is always distinct from all producer identities
  (reuse the existing `_producer_identities` rejection in `evidence_gate.py`);
  the boundary is preserved, only the invocation is automated.
- Bound the changes_requested loop (max cycles) and surface a blocker instead of
  looping unbounded.
- Keep all existing EvidenceGate guarantees intact (hash recompute, CAS,
  append-only events, blocker handling).

# Non-goals

- Do not allow one identity to act as both producer and verifier (the
  producer != verifier rule is non-negotiable).
- Do not build the Goal-to-AWKP bridge here (that is TASK-0060).
- Do not weaken EvidenceGate verification or the CAS writer.
- Do not self-complete this task; EvidenceGate decides completion.

# Acceptance criteria

- [ ] An orchestrator drives a task from working to a terminal EvidenceGate
  decision (completed or changes_requested) without manual CLI invocation
  between steps, covered by a test.
- [ ] The verifier identity used by the orchestrator is always rejected as a
  producer identity would be if they coincided; an attempt to use a producer
  identity as verifier fails closed, covered by a test.
- [ ] On request_changes, the orchestrator re-claims to working via the
  TASK-0057 writer and re-enters review, bounded by a maximum cycle count;
  exceeding it surfaces a blocker rather than looping, covered by a test.
- [ ] All existing EvidenceGate guarantees still hold (artifact hash recompute,
  CAS state_version, append-only events) - regression tests pass.
- [ ] The orchestrator depends on real verification (TASK-0053..0056); it does
  not approve on a hollow gate.
- [ ] Targeted tests, lint, and diff checks pass, or any failure is recorded as
  a blocker with exact command output.
- [ ] Producer moves TASK-0059 only to review; EvidenceGate decides completion.

# Verification method

- .\.venv\Scripts\python.exe -B -m unittest tests.test_evidence_gate tests.test_cli -v
- .\.venv\Scripts\python.exe -B scripts\check.py
- git diff --check

# Required evidence and handoff

- Publish `evidence/orchestrator-report.md` describing the chained flow, the
  preserved producer != verifier boundary, and the bounded changes_requested
  loop with its test outcomes.
- Publish `evidence/verification-summary.json`.
- Publish `handoffs/HANDOFF-0001.md` with one exact next action for TASK-0060.
