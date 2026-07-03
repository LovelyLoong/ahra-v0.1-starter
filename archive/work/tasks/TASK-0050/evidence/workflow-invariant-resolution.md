---
type: Evidence
id: EVD-TASK-0050-0001
schema_version: awkp/0.1
title: TASK-0050 workflow invariant resolution
description: Maps TASK-0049 P1 workflow risks to TASK-0050 mitigations, verification, and remaining Mode C boundaries.
status: review
owner: agent:codex-dynamic-kernel-operator
created_at: 2026-06-28T14:45:09.826267Z
created_by: agent:codex-dynamic-kernel-operator
task_id: TASK-0050
kind: workflow_invariant_resolution
---

# Summary

TASK-0050 resolved the four P1 workflow-invariant risks identified by
TASK-0049 for the real bounded Executor path. This task did not promote Mode C
to the default path, did not run a broad live Mode C pilot, and does not claim
broad Mode C stability.

# Resolved risks

## P1-1: BoundedTaskExecutor dependency lifecycle ambiguity

TASK-0049 found that default-visible `BoundedTaskExecutor` imported
`TaskHarness` directly from `standard_harness.py`, while the component inventory
classified `standard-harness` as legacy/non-default.

Mitigation:

- Added `src/ahra/reference_runner/task_harness.py` as the default-visible
  adapter entrypoint for shared TaskHarness Agent phase support.
- Updated `BoundedTaskExecutor`, package exports, loop compatibility, and tests
  to import `TaskHarness` through `task_harness.py`.
- Updated `docs/architecture/component-inventory.json` with
  `adapter:task-harness-agent-phase` and clarified that the historical
  `component:standard-harness` workflow module remains legacy.

Remaining limit:

- The implementation still physically lives in `standard_harness.py` for
  compatibility. Full extraction is deferred because the minimal lifecycle
  ambiguity is now explicit and tested.

## P1-2: Mode C pilot scorecard failure classes were too coarse

TASK-0049 found that the scorecard exposed top-level `failure_classes` but did
not provide workflow dimensions sufficient to distinguish failure layers.

Mitigation:

- Added per-run `workflow_failure_dimension`.
- Added scorecard-level `workflow_failure_dimensions` with counts and a legend
  for `contract`, `gate`, `budget`, `scheduler`, `provider_runtime`,
  `model_behavior`, `unknown`, and `none`.
- Added targeted tests for provider/runtime, model-behavior, and scheduler
  classifications.

Remaining limit:

- The dimensions are evidence classification for the pilot; they do not by
  themselves approve broader Mode C execution.

## P1-3: Real Executor budget normalization invariant was pilot-specific

TASK-0049 found that real Planner output normalization existed in the pilot but
was not exposed as a clear invariant in scorecard evidence.

Mitigation:

- Centralized the real Executor bounded-node minimums used by request expansion
  and real Planner admission writeback.
- Added `real_executor_budget_invariant` to the scorecard.
- Added the same invariant to `planner-budget-normalization.json` when real
  Planner output is normalized.
- Added targeted Mode C budget-normalization test coverage.

Remaining limit:

- The invariant is still scoped to the real-Agent pilot and GoalOperation real
  Executor profile. No separate production scheduler default has been approved.

## P1-4: Non-literal and multi-output contract coverage was under-specified

TASK-0049 found that the repaired bounded-write path covered literal
`filesystem.write` resources but did not explicitly cover globs, directories,
or multi-output expectedOutputs.

Mitigation:

- Fixed `BoundedTaskExecutor` resource normalization so directory resources such
  as `reports/` keep their trailing slash and are not misclassified as literal
  artifact files.
- Added deterministic test coverage proving multiple literal artifact resources
  generate multiple internal artifact checks.
- Added deterministic test coverage proving non-literal resources preserve
  expectedOutputs and allowed globs without generating exact artifact checks.

Remaining limit:

- Glob resource expansion into concrete filesystem write grants is not added in
  this task. Non-literal resources remain a contract boundary, not proof of a
  specific output file path.

# Verification

- PASS: `.\.venv\Scripts\python.exe -B -m unittest tests.test_real_agent_pilot tests.test_node_executor tests.test_reference_runner`
  - Result: 51 tests passed, 1 skipped.
- PASS: `.\.venv\Scripts\python.exe -B scripts\check.py --lint`
  - Result: AHRA lint 0 failures; AWKP lint 0 errors, 0 warnings.
- PASS: `.\.venv\Scripts\python.exe -B scripts\check.py --test`
  - Result: 206 tests passed, 2 skipped.
- PASS: `git diff --check`
  - Result: no whitespace errors.

# Boundary conclusion

The workflow closeout issues from TASK-0049 are addressed at the local
invariant level and are ready for independent EvidenceGate review. Mode C
remains explicit and non-default pending any future separately authorized pilot.
