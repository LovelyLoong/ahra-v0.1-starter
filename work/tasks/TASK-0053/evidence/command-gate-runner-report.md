---
type: Evidence
id: EVD-TASK-0053-0001
schema_version: awkp/0.1
title: CommandGateRunner implementation report
description: Producer evidence for TASK-0053 command-gate runner behavior and boundaries.
status: passed
owner: agent:codex-dynamic-kernel-operator
created_at: 2026-06-29T11:05:00Z
created_by: agent:codex-dynamic-kernel-operator
task_id: TASK-0053
---

# CommandGateRunner implementation report

## Summary

TASK-0053 adds `CommandGateRunner` in `src/ahra/verification.py` without
changing `DeterministicGateRunner` behavior. The new runner is a structural
`GateRunnerPort`: it exposes `gate_kind`, `release_ref`, and async `run()`, and
is registrable through `GateRunnerRegistry`.

## Execution boundary

- `GateExecutionRequest` now carries the selected `GateDefinition.command`,
  `GateDefinition.expectation`, and admitted `process.exec` capability grants.
- `CommandGateRunner` refuses to execute when the command is absent or when no
  current `process.exec` grant exactly matches the command vector rendered as
  its resource string.
- When a matching grant exists, execution happens only through the injected
  `RuntimeProvider.exec()` call. `src/ahra/verification.py` has no `subprocess`
  import and does not call process APIs directly.
- `StaticPlanScheduler` now passes node admission grants into
  `VerificationExecutionContext`, so command gates can use the same explicit
  admission boundary as executable nodes.

## Status mapping

The runner judges the runtime result against the TASK-0052 expectation contract:

| Runtime outcome | Gate status | Failure class |
|---|---|---|
| Exit code matches expected exit code and optional output match succeeds | `passed` | none |
| Exit code differs from expected exit code | `failed` | `unexpected_exit_code` |
| Runtime result reports timeout | `timed_out` | `command_timeout` |
| Runtime result has no exit code and did not timeout | `error` | `missing_executable` |
| Output containment expectation is not met | `failed` | `output_mismatch` |
| Missing command or missing grant | `blocked` | `missing_gate_command` or `process_exec_not_granted` |

## Artifacts and mutation detection

Each command-gate result writes a JSON raw-output artifact through the injected
`ArtifactStore.put()`. The returned artifact reference is included in
`GateExecutionResult.artifact_refs` and `GateExecutionResult.raw_output_ref`.

Workspace mutation detection remains in `VerificationExecutor`: it snapshots
the governed workspace before and after runner execution and rewrites the gate
result to `unexpected_workspace_mutation` when `mutation_allowed=False`.

## Verification coverage

Dedicated `tests.test_verification.CommandGateRunnerTests` cover:

- exit 0 plus output match -> `PASSED`;
- nonzero exit -> `FAILED` with `unexpected_exit_code`;
- timeout -> `TIMED_OUT`;
- missing executable -> `ERROR` with `missing_executable`;
- default-deny without an explicit `process.exec` command resource;
- output mismatch;
- registry resolution by `gate_kind` and `release_ref`;
- command-runner workspace mutation fail-closed behavior.

`tests.test_plan_execution` also passed after the scheduler grant passthrough.
