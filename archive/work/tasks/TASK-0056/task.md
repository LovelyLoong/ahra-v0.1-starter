---
type: WorkItem
id: TASK-0056
schema_version: awkp/0.1
title: Demonstrate a real failing gate end-to-end
description: Wire a real command gate into the M1 example and prove the chain bites - a genuine FAIL produces a defect and a non-completed goal, then a fix turns it PASS, encoded as a non-skipped test.
context_id: CTX-verification-teeth
priority: P0
risk_level: R2
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-29T10:00:00Z
depends_on: [TASK-0055]
input_refs:
  - ../../../examples/m1/goal-run-request.yaml
  - ../../../src/ahra/goal_operations.py
  - ../../../src/ahra/verification.py
  - ../../../tests/test_real_agent_pilot.py
  - ../../../scripts/run_real_agent_pilot.py
output_contract:
  - kind: failing_gate_demonstration_report
  - kind: verification_summary
  - kind: handoff
---

# Goal

Prove the teeth. With the engine (TASK-0053), honest completion (TASK-0054), and
lineage review (TASK-0055) in place, demonstrate the full chain end-to-end: a
real command gate that genuinely FAILS produces a `DefectRecord` and a goal that
is NOT completed, then a fix turns the same gate PASS and the goal completes.
This is the credibility slice and also fills the currently skipped Mode C real
path coverage.

# Scope

- Wire a real command gate into the M1 example (or a sibling example) using the
  `CommandGateRunner` and the GateDefinition `command` + `expectation`.
- Produce a reproducible run where the command gate FAILS, yielding
  `GateExecutionStatus.FAILED`, a `DefectRecord`, `complete=False`, and a goal
  that is not marked completed, with all of it captured as evidence.
- Then apply the fix so the same gate PASSes and the goal completes.
- Encode the deliberate-failure scenario as a non-skipped automated test.

# Non-goals

- Do not weaken any capability / gate / budget / timeout / scheduler /
  EvidenceGate boundary to make the pass case work.
- Do not promote anything new to the default path beyond what the chain
  requires.
- Do not self-complete this task; EvidenceGate decides completion.

# Acceptance criteria

- [ ] A reproducible run exists where a real command gate FAILS, producing
  `GateExecutionStatus.FAILED`, at least one `DefectRecord`, `complete=False`,
  and a goal that is not marked completed - all captured as evidence.
- [ ] After the fix, the same command gate PASSes and the goal completes,
  captured as evidence.
- [ ] The deliberate-failure scenario is encoded as a non-skipped automated
  test (no `skip` decorator on the failing-gate case).
- [ ] `.\.venv\Scripts\python.exe -B scripts\check.py` (full lint + test) passes.
- [ ] Evidence is published per AWKP (report + verification-summary + handoff).
- [ ] Producer moves TASK-0056 only to review; EvidenceGate decides completion.

# Verification method

- .\.venv\Scripts\python.exe -B -m unittest tests.test_real_agent_pilot tests.test_verification tests.test_goal_operations -v
- .\.venv\Scripts\python.exe -B scripts\check.py
- git diff --check

# Required evidence and handoff

- Publish `evidence/failing-gate-demonstration-report.md` showing the FAIL ->
  defect -> not-completed sequence and the subsequent PASS -> completed sequence
  with concrete artifacts.
- Publish `evidence/verification-summary.json`.
- Publish `handoffs/HANDOFF-0001.md` with one exact next action.
