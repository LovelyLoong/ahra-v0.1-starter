---
type: Evidence
id: EVD-TASK-0038-0001
schema_version: awkp/0.1
task_id: TASK-0038
kind: implementation_report
title: TASK-0038 implementation report
description: Producer implementation report for the generic Goal operation CLI and deterministic M1 profile.
owner: agent:codex-dynamic-kernel-operator
status: review
created_by: agent:codex-dynamic-kernel-operator
created_at: 2026-06-26T09:38:02Z
---

# TASK-0038 Implementation Report

## Summary

Implemented a generic deterministic Goal operation path behind `GoalOperationService` and `ahra goal ...`.
The CLI now validates a `GoalExecutionRequest`, compiles PlanDraft to admitted PlanIR, starts durable SQLite-backed GoalExecution state, inspects state and metrics, resumes by durable GoalExecution id plus immutable request profile, and cancels non-terminal Goals.

The producer moved implementation evidence toward review only. This report is not a completion claim.

## Changed Contracts And Entry Points

- Added `contracts/schemas/goal-execution-request.schema.json`.
- Added `examples/m1/goal-run-request.yaml`.
- Added `src/ahra/goal_operations.py` with schema versions:
  - `ahra/goal-operation/0.1`
  - `ahra/goal-operation-validation/0.1`
  - `ahra/goal-operation-plan/0.1`
  - `ahra/goal-operation-start/0.1`
  - `ahra/goal-operation-resume/0.1`
  - `ahra/goal-operation-inspect/0.1`
  - `ahra/goal-operation-cancel/0.1`
- Added `GoalOperationPort` in `src/ahra/ports.py`.
- Added CLI commands:
  - `goal validate`
  - `goal plan`
  - `goal start`
  - `goal inspect`
  - `goal resume`
  - `goal cancel`
- Kept `fixture dynamic-repair` explicit and regression-only.
- Changed package-level dynamic fixture exports to lazy compatibility exports so `goal validate` does not import `ahra.dynamic_fixture`.

## Service Boundary

The argparse handlers only instantiate and call `GoalOperationService`. Planning, scheduling, GateRunner wiring, NodeExecutor registration, SQLite store access, capability admission, and resume/cancel state transitions are in the service layer.

Known direct CLI boundary check:

- `src/ahra/cli.py` imports `GoalOperationService`.
- `src/ahra/cli.py` does not import `NodeExecutorRegistry`, `GateRunnerRegistry`, `DeterministicGateRunner`, `run_ready_nodes_once`, or `run_until_terminal`.

## M1 Profile

The default generic profile is explicit and immutable:

- profile: `profile/m1-deterministic@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`
- planner: `planner/inline-plan-draft@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb`
- executor: `executor/deterministic-file-effect@sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc`
- gate runner: `gate-runner/deterministic@sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd`
- runtime: `runtime/local-goal@sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee`
- store: `sqlite`

Unknown profile, adapter, runtime, and store refs fail closed before side effects.

## Acceptance Mapping

- GoalExecutionRequest validates without importing `dynamic_fixture.py`: `tests/test_goal_operations.py::test_goal_validate_does_not_import_dynamic_fixture`.
- `goal plan` emits request, PlanDraft, validation report, and PlanIR without execution: SG-8 smoke `cli-plan.json` and `.ahra/artifacts/plan-ir.json`.
- `goal start` creates durable GoalExecution and begins the shared service path: SG-8 smoke `cli-start-run-once.json`.
- `goal inspect` reports Goal, Plan, Node, Evidence, capability and metrics: SG-8 smoke `cli-inspect.json`.
- `goal resume` continues from SQLite in a new process: `tests/test_goal_operations.py::test_validate_plan_start_resume_inspect_and_terminal_cancel` and SG-8 smoke `cli-resume.json`.
- `goal cancel` propagates through non-terminal GoalExecution, PlanExecution and NodeRuns in tests; terminal cancel fails closed in SG-8 smoke.
- Unknown refs fail closed with structured error codes: `tests/test_goal_operations.py::test_unknown_and_invalid_goal_request_refs_fail_closed`.
- CLI contains no direct NodeExecutor or GateRunner orchestration: source check in this report plus tests.
- Default docs and Skill now identify `ahra goal ...` as the generic path and retain fixture as regression-only.
- SG-8 smoke passed: `work/tasks/TASK-0038/evidence/sg8-smoke/sg8-smoke-summary.json`.

## Verification

Commands run:

- `uv run python -B -m unittest tests.test_goal_operations tests.test_cli`
- `uv run python -B scripts/check.py --test`
- `uv run python -B scripts/lint_contracts.py`
- `uv run python -B scripts/check.py --lint`
- `uv run ahra goal validate examples/m1/goal-run-request.yaml`
- `git diff --check`
- `uv run python -B scripts/check.py`

Results:

- Focused unittest: 13 tests passed.
- Full check: 183 tests passed, 1 environment-specific symlink test skipped.
- Lint contracts: 0 failures.
- `git diff --check`: passed.
- Console script smoke: `uv run ahra goal validate examples/m1/goal-run-request.yaml` returned `ok: true`.

## Metrics

- SG-8 smoke GoalExecution: `GEXEC-8c810c234a600c6c`.
- PlanExecution count: 1.
- NodeRun count: 2.
- Node status counts: `succeeded: 2`.
- Evidence refs: 2.
- Capability grant refs: 1.
- Missing artifact findings: 0.
- Terminal cancel negative: exit code 2, error code `cancel_terminal_goal`.
- Approximate goal start to first executor side-effect audit: 1.20 seconds in SG-8 smoke.
- Fixture-specific imports in generic validate path: 0 observed by test.

## Known Limits

- This is a deterministic local M1 operation profile, not a distributed scheduler.
- Resume still requires the immutable request profile path to reconstruct the PlanIR; durable progress and terminal state come from SQLite.
- Real Planner, real Executor Agent, and provider adapters remain explicit non-default paths for later tasks.
- AWKP Task completion is unchanged and still requires independent EvidenceGate review.
