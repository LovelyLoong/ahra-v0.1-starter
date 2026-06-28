---
type: EvidenceReport
id: ART-TASK-0047-0001
schema_version: awkp/0.1
title: TASK-0047 Mode C timeout root-cause report
description: Classifies the Mode C timeout root cause, records the minimal runtime-stability patch, and preserves the Mode C no-go boundary.
status: review
owner: agent:codex-dynamic-kernel-operator
task_id: TASK-0047
created_at: 2026-06-28T12:42:39.282929Z
created_by: agent:codex-dynamic-kernel-operator
---

# TASK-0047 Root Cause Report

Created at: 2026-06-28T12:42:39.282929Z
Producer: agent:codex-dynamic-kernel-operator

## Conclusion

The TASK-0045 Mode C timeout had two distinct layers.

1. Fixed in TASK-0047: after the bounded Executor had already reached terminal
   failure internally, the isolated child process could stay alive until the
   outer repetition watchdog killed it. The root cause was AgentDriver phase
   cancellation running on the scheduler event loop and waiting on provider SDK
   cleanup paths that can block inside `asyncio.to_thread` default-executor
   work.
2. Not fixed, and still a no-go: the real Mode C bounded Executor still times
   out instead of completing the bounded write task. Mode C remains
   experimental and must not be promoted to the default path.

## Evidence From TASK-0045

- `work/tasks/TASK-0045/evidence/real-agent-pilot/mode-c/scorecard.json`
  recorded `run_count: 3`, `success_count: 0`, and
  `failure_classes.timeout: 3`.
- Each TASK-0045 Mode C run hit the isolated process watchdog at about 360
  seconds with `recoveredPartialRun: true`.
- The recovered internal execution state showed the bounded task node
  `timed_out` and the dependent verification node still `pending`.
- Planner admission was not the failing layer: the scorecard preserved accepted
  planner output and a passed plan-validation report before execution failed.

## Root Cause Classification

Planner output: not the root cause for the process hang. Planner drafts were
accepted before the executor timeout.

Scheduler timeout handling: part of the root cause. The timeout path requested
cancellation but could still wait for the AgentDriver phase to finish cleanup.

Bounded Executor runtime behavior: still a real Mode C quality failure. The
Executor does not complete the bounded write task in the live run.

Codex SDK cancellation/process behavior: root cause of the process-boundary
hang. The local `openai_codex` async client routes sync calls through
`asyncio.to_thread`; when that work is stuck or slow to unwind, the loop default
executor can leave non-daemon worker threads alive after AHRA has already
written terminal failure state.

Isolated repetition watchdog: not the primary root cause. It was the final
external containment layer that killed the process after the internal scheduler
failed to self-close the child process.

## Minimal Patch

Changed `src/ahra/reference_runner/standard_harness.py` only for AgentDriver
phase isolation:

- Added `_AgentPhaseRunner` to run each AgentDriver phase in a daemon thread
  with a dedicated event loop.
- Added a one-second cooperative cancellation grace window via
  `AGENT_PHASE_CANCEL_GRACE_SECONDS`.
- Added `agent_phase_cancel_grace_exceeded` evidence when a provider phase does
  not finish cancellation inside the grace window.
- Added `_DaemonThreadPoolExecutor` as the AgentDriver phase event loop default
  executor so abandoned `asyncio.to_thread` work cannot keep the isolated child
  process alive.
- Added normal-completion cleanup for async generators and default-executor
  threads.

The patch does not change planner admission, gate execution, capability checks,
budget checks, EvidenceGate authority, or Mode C default status.

## Regression Tests

Added fake-driver coverage in `tests/test_reference_runner.py`:

- `CancellationResistantExecutorDriver` proves timeout return does not wait for
  unresponsive cancellation cleanup.
- `ToThreadExecutorDriver` proves normal AgentDriver phases close their default
  executor threads.
- `ToThreadBlockingExecutorDriver` proves timeout return does not leave
  non-daemon AgentDriver or `asyncio.to_thread` workers behind.

## Live Rerun Evidence

Post-fix bounded Mode C rerun:

- Scorecard:
  `work/tasks/TASK-0047/evidence/real-agent-pilot/mode-c-daemon-executor/scorecard.json`
- Run result:
  `work/tasks/TASK-0047/evidence/real-agent-pilot/mode-c-daemon-executor/run-01/run-result.json`
- Result: the command exited before the isolated watchdog and did not require
  partial-run recovery.
- Remaining failure: `success_count: 0`, `failure_classes.timeout: 1`,
  `nodeStatusCounts: {"pending": 1, "timed_out": 1}`.

## Decision Boundary

TASK-0047 resolves the Mode C timeout root cause at the process-boundary and
runtime-stability layer. It does not make Mode C successful. Mode C remains
no-go for default path until a separate task fixes the live Executor completion
failure and EvidenceGate approves that claim.
