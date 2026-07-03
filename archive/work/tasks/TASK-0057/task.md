---
type: WorkItem
id: TASK-0057
schema_version: awkp/0.1
title: Add governed CAS writer for AWKP task state transitions
description: Provide governed, compare-and-swap-protected transitions for ready to working (with lease and fencing), working to review, and changes_requested back to working, on the default surface, ending hand-edited state.json.
context_id: CTX-workflow-autonomy
priority: P0
risk_level: R2
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-29T11:00:00Z
depends_on: [TASK-0056]
input_refs:
  - ../../../src/ahra/evidence_gate.py
  - ../../../src/ahra/reference_runner/awkp_task.py
  - ../../../src/ahra/cli.py
  - ../../../scripts/lint_awkp.py
output_contract:
  - kind: governed_state_writer_report
  - kind: verification_summary
  - kind: handoff
---

# Goal

End hand-edited AWKP state. Today only `evidence-gate evaluate` writes task
state with a compare-and-swap (`expected_version`); the other transitions are
hand-edited, and the only programmatic writer (`reference_runner/awkp_task.py`)
is legacy-only and has no CAS. Provide a governed, CAS-protected state writer
for the non-final transitions so a task can move ready -> working -> review and
changes_requested -> working safely and reproducibly.

# Scope

- Implement a governed state writer (domain module, not legacy reference_runner)
  for: `ready -> working` (acquire lease + fencing token), `working -> review`,
  and `changes_requested -> working` (re-claim).
- Every write is compare-and-swap against `state_version` (mirror the
  `expected_version` discipline already in `evidence_gate.py`) and appends an
  append-only event with a unique idempotency key and monotonic timestamp.
- `working` writes must record a lease; re-claim must check the fencing token.
- Keep the writer stdlib-only and offline (no adapter/model dependency), so
  `scripts/lint_awkp.py` continues to pass.

# Non-goals

- Do not add the create/claim CLI command here (that is TASK-0058).
- Do not build the producer/verifier orchestrator here (that is TASK-0059).
- Do not change `evidence-gate evaluate` semantics for the final review
  decision.
- Do not weaken or bypass the EvidenceGate completion authority.
- Do not self-complete this task; EvidenceGate decides completion.

# Acceptance criteria

- [ ] A governed writer performs `ready -> working`, `working -> review`, and
  `changes_requested -> working`, each as a compare-and-swap against
  `state_version`, rejecting a stale `expected_version` with a clear error.
- [ ] `ready -> working` records a lease with a fencing token; a re-claim or
  conflicting write with a stale fencing token is rejected, covered by a test.
- [ ] Every transition appends an append-only event with a unique
  `idempotency_key` and a monotonic `occurred_at`; duplicate idempotency keys
  are rejected.
- [ ] A concurrent/stale write attempt does not silently clobber state (CAS
  failure is surfaced), covered by a test.
- [ ] The writer is stdlib-only and offline; `.\.venv\Scripts\python.exe -B
  scripts\lint_awkp.py` passes.
- [ ] Targeted tests, lint, and diff checks pass, or any failure is recorded as
  a blocker with exact command output.
- [ ] Producer moves TASK-0057 only to review; EvidenceGate decides completion.

# Verification method

- .\.venv\Scripts\python.exe -B -m unittest tests.test_evidence_gate -v
- .\.venv\Scripts\python.exe -B scripts\lint_awkp.py
- .\.venv\Scripts\python.exe -B scripts\check.py --lint
- git diff --check

# Required evidence and handoff

- Publish `evidence/governed-state-writer-report.md` describing each transition,
  the CAS and fencing checks, and the concurrency-safety test outcomes.
- Publish `evidence/verification-summary.json`.
- Publish `handoffs/HANDOFF-0001.md` with one exact next action for TASK-0058.
