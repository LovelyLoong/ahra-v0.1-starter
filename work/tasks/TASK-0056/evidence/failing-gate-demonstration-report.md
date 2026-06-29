---
type: Evidence
id: EVD-TASK-0056-0001
schema_version: awkp/0.1
title: TASK-0056 failing gate demonstration report
description: Producer evidence for the real command Gate FAIL to defect and fixed-input PASS demonstration.
status: review
owner: agent:codex-dynamic-kernel-operator
created_at: 2026-06-29T13:48:48Z
created_by: agent:codex-dynamic-kernel-operator
task_id: TASK-0056
---

# TASK-0056 Failing Gate Demonstration Report

Generated at: 2026-06-29T13:48:48Z
Producer: agent:codex-dynamic-kernel-operator

## Scope

TASK-0056 required a real command Gate to fail end-to-end, produce a failed
GateExecution result, create a DefectRecord, keep the GoalExecution
non-completed, then pass after the input is fixed. The demonstration is encoded
as a normal unittest, not a skipped test.

## Implementation

- Added `examples/m1/goal-run-request-command-gate.yaml` as a sibling M1
  request using `gate-runner/command@sha256:555...`.
- Extended `GoalExecutionRequest` loading to accept inline `GateDefinition`
  records, bind each definition to `registry.gateRefs` via
  `_gate_definition_digest`, and reject mismatched or unregistered definitions.
- Registered `CommandGateRunner` for the command GateDefinition evidence kinds
  declared by the request, so command Gates do not fall through to the
  deterministic `*/*` runner.
- Added local command runtime and artifact storage for GoalOperation command
  Gates. Raw command output is written under the request artifact directory.
- Recorded failed verification reports as `DefectRecord` entries and passed
  open defect refs into GoalExecution finalization.
- Added `completion` and `defects` to GoalOperation start/resume reports so
  `complete=false` is directly visible when a command Gate fails.

## Demonstrated Failure

Test:
`tests.test_goal_operations.GoalOperationCliTests.test_real_command_gate_failure_records_defect_then_fixed_input_completes_goal`

Failure setup:

- The test copies `examples/m1/goal-run-request-command-gate.yaml` to a temp
  request directory.
- It writes `workspace/inputs/command-gate.txt` with `broken`.
- The command Gate runs:
  `python -c <sentinel check>`.

Asserted failure facts:

- `planStatus == "failed"`.
- `goalStatus == "repairing"`, not `succeeded`.
- `completion.complete == false`.
- One open `DefectRecord` is returned for `GATE-command-sentinel`.
- The command Gate node is `failed` with `failure_class == "gate_execution_failed"`.
- Raw command output artifact has:
  - `status == "failed"`
  - `failureClass == "unexpected_exit_code"`
  - `exitCode == 1`
  - stdout contains `COMMAND_GATE_BAD:broken`

## Demonstrated Fix

Repair setup:

- The same request shape is copied to a fresh temp request directory.
- It writes `workspace/inputs/command-gate.txt` with `fixed`.

Asserted repair facts:

- `planStatus == "succeeded"`.
- `goalStatus == "succeeded"`.
- `completion.complete == true`.
- No defects remain in the start report or GoalExecution open defect refs.
- The command Gate node is `succeeded`.
- Raw command output artifact has:
  - `status == "passed"`
  - `failureClass == null`
  - `exitCode == 0`
  - stdout contains `COMMAND_GATE_OK`

## Verification

Commands run from `D:\Work\ahra-v0.1-starter`:

- `.\.venv\Scripts\python.exe -B -m unittest tests.test_goal_operations -v`
  - Result: passed, 9 tests.
- `.\.venv\Scripts\python.exe -B -m unittest tests.test_real_agent_pilot tests.test_verification tests.test_goal_operations -v`
  - Result: passed, 49 tests.
- `.\.venv\Scripts\python.exe -B scripts\check.py`
  - Result: passed.
  - AWKP lint: 0 errors, 0 warnings.
  - AHRA lint: 0 failures.
  - unittest discovery: 222 tests, 2 skipped.
- `git diff --check`
  - Result: exit code 0.
  - Non-blocking warnings were emitted for pre-existing dirty TASK-0055 CRLF/LF
    normalization files; no TASK-0056 whitespace errors were reported.

## Producer Boundary

This report does not declare TASK-0056 completed. The producer moved the task
only to review. Independent EvidenceGate review remains the authority for
completion.
