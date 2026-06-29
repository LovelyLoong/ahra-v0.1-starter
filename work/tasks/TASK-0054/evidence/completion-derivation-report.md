---
type: Evidence
id: EVD-TASK-0054-0001
schema_version: awkp/0.1
title: TASK-0054 completion derivation report
description: Producer evidence describing evidence-derived Goal completion.
status: review
owner: agent:codex-dynamic-kernel-operator
created_at: 2026-06-29T11:45:00Z
created_by: agent:codex-dynamic-kernel-operator
task_id: TASK-0054
---

# TASK-0054 completion derivation report

## Summary

TASK-0054 replaces the default GoalOperation hardcoded completion path with
completion derived from current `EvidenceV2` records through
`evaluate_completion()`.

The default scheduler now creates `DeterministicGoalVerificationService` from
the request `goal_ref` and `required_claim_refs`, with a live evidence provider
bound to the same `VerificationExecutor` that records gate-run backed
`EvidenceV2`. `GoalOperationService._finish_goal_if_ready()` consumes the
derived `CompletionGateResult` and passes `completion.complete` into
`PlanExecutionService.complete_goal()` instead of unconditional `True`.

## Implementation notes

- `src/ahra/goal_operations.py` builds a minimal `ClaimGraph` from
  `GoalExecutionRequest.required_claim_refs` and evaluates completion from the
  executor's current evidence records.
- Missing completion inputs fail closed. A missing claim graph or unavailable
  scheduler completion result returns `complete=False`.
- `src/ahra/plan_execution.py` runs the selected goal verification gate before
  calling `verification_service.complete()`, so the gate's own `EvidenceV2` can
  participate in final completion.
- The goal verification context no longer injects `completionComplete` metadata.
  The dynamic fixture gate was updated to decide its goal-completion gate from
  dependency evidence coverage instead of trusting that metadata.
- `src/ahra/m1_experiment.py` now wires the default deterministic verification
  service through `from_required_claim_refs(...)` so deterministic M1 smoke
  still completes through real evidence coverage.
- `tests/test_goal_operations.py` covers both a failing evidence case that
  returns `complete=False` and a PlanExecution-succeeded case that does not mark
  the GoalExecution succeeded when derived completion is incomplete.

## Boundaries

`rg` confirms no `completion_complete=True` remains in
`src/ahra/goal_operations.py`. Remaining direct `completion_complete=True`
occurrences are in `src/ahra/m1_experiment.py` experiment/negative-helper code,
not the default GoalOperation completion path named by TASK-0054.

`src/ahra/goal_operations.py` still uses project-local ports, contracts,
evidence, planning, scheduling, and verification modules. No provider SDK,
cloud adapter, or model client import was introduced.

## Verification

- `uv run python -B -m unittest tests.test_goal_operations tests.test_verification tests.test_plan_execution -v`: passed, 50 tests.
- `uv run python -B scripts\check.py --test`: passed, 218 tests, 1 skipped.
- `uv run python -B scripts\check.py --lint`: passed.
- `git diff --check`: passed.

An earlier `uv run python -B scripts\check.py --test` attempt failed because
the dynamic fixture goal-completion gate still depended on precomputed
`completionComplete` metadata. That fixture was corrected to use dependency
evidence coverage, and the final reruns above passed.
