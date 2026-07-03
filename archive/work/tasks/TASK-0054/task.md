---
type: WorkItem
id: TASK-0054
schema_version: awkp/0.1
title: Derive goal completion from real gate evidence
description: Replace the two hardcoded-PASS completion paths so goal completion is derived from real EvidenceV2 via evaluate_completion, not from a constant True.
context_id: CTX-verification-teeth
priority: P0
risk_level: R2
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-29T10:00:00Z
depends_on: [TASK-0053]
input_refs:
  - ../../../src/ahra/goal_operations.py
  - ../../../src/ahra/verification.py
  - ../../../src/ahra/plan_execution.py
  - ../../../examples/m1/goal-run-request.yaml
output_contract:
  - kind: completion_derivation_report
  - kind: verification_summary
  - kind: handoff
---

# Goal

Make completion honest. Two paths currently hardcode success:
`DeterministicGoalVerificationService.complete()` returns
`complete=True, coverage=1.0`, and `_finish_goal_if_ready` calls
`complete_goal(completion_complete=True)` whenever the plan status is SUCCEEDED.
Replace both so completion is derived from the execution's real `EvidenceV2`
through the already-real `evaluate_completion()`.

# Scope

- Change the goal verification service so `complete()` returns a
  `CompletionGateResult` derived from the execution's real evidence records via
  `evaluate_completion()`, with `current_claim_coverage` reflecting actual claim
  coverage.
- Change `_finish_goal_if_ready` so `completion_complete` is the derived value,
  not an unconditional `True`.
- Preserve the existing deterministic M1 smoke path so it still completes when
  its gates genuinely pass.

# Non-goals

- Do not change the AWKP EvidenceGate here (that is TASK-0055).
- Do not build the end-to-end fail-then-fix demonstration here (TASK-0056).
- Do not weaken `evaluate_completion`, coverage math, or defect handling.
- Do not self-complete this task; EvidenceGate decides completion.

# Acceptance criteria

- [ ] `complete()` returns a `CompletionGateResult` derived from the execution's
  real `EvidenceV2` through `evaluate_completion()`, and `current_claim_coverage`
  reflects the actually covered required claims (not a hardcoded 1.0).
- [ ] A goal with a failing gate yields `complete=False` with populated
  `uncovered_claim_refs` or `missing_claim_refs`, and the goal is NOT marked
  completed, covered by a test.
- [ ] A goal whose gates all pass yields `complete=True` and the goal is marked
  completed, covered by a test.
- [ ] `_finish_goal_if_ready` no longer passes an unconditional
  `completion_complete=True`; it passes the derived completion value.
- [ ] The existing deterministic M1 smoke path still completes (regression).
- [ ] `src/ahra/goal_operations.py` imports no adapter/model/cloud dependency.
- [ ] Targeted tests, lint, and diff checks pass, or any failure is recorded as
  a blocker with exact command output.
- [ ] Producer moves TASK-0054 only to review; EvidenceGate decides completion.

# Verification method

- .\.venv\Scripts\python.exe -B -m unittest tests.test_goal_operations tests.test_verification tests.test_plan_execution -v
- .\.venv\Scripts\python.exe -B scripts\check.py --test
- .\.venv\Scripts\python.exe -B scripts\check.py --lint
- git diff --check

# Required evidence and handoff

- Publish `evidence/completion-derivation-report.md` describing both replaced
  paths and the failing-gate and passing-gate test outcomes.
- Publish `evidence/verification-summary.json`.
- Publish `handoffs/HANDOFF-0001.md` with one exact next action for TASK-0055.
