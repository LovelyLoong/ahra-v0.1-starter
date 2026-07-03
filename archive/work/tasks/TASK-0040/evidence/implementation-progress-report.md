---
type: Evidence
id: EVD-TASK-0040-0001
schema_version: awkp/0.1
title: TASK-0040 implementation progress report
description: Producer progress report for the first bounded real-Agent pilot implementation increment.
status: active
owner: agent:codex-dynamic-kernel-operator
source_refs:
  - ../task.md
  - ../../../src/ahra/goal_operations.py
  - ../../../src/ahra/real_agent_pilot.py
  - ../../../scripts/run_real_agent_pilot.py
  - ../../../tests/test_real_agent_pilot.py
evidence_refs:
  - EVD-TASK-0040-0002
confidence: partial
last_verified_at: 2026-06-28T02:24:20Z
review_after: 2026-09-28T00:00:00Z
tags: [task-0040, real-agent-pilot, progress]
---

# TASK-0040 Progress Report

Created at: 2026-06-28T02:24:20Z
Actor: agent:codex-dynamic-kernel-operator

## Implemented Increment

- Added M1 real-Agent pilot profiles to `GoalOperationProfileRegistry`:
  - real Planner + deterministic Executor/GateRunner
  - deterministic Planner + real bounded Executor/GateRunner
  - combined real Planner + real bounded Executor/GateRunner
- Added fail-closed real bounded Executor injection to `GoalOperationService`.
  - `goal validate` and `goal plan` still work without a real executor driver.
  - `goal start` and `goal resume` fail before SQLite side effects when the real executor profile has no injected `AgentDriver`.
- Added `ahra.real_agent_pilot.RealAgentPilotRunner`.
  - Mode A runs `AgentDriverExecutionPlannerAdapter`, then `PlannerOutputValidator`, then starts the normal GoalOperation path only after admission.
  - Mode B uses the normal GoalOperation scheduler and `CapabilityAdmissionService` before invoking `BoundedTaskExecutor`.
  - Mode C is present but disabled unless explicitly allowed after Mode A/B review.
  - Scorecards include the required fields from `docs/policies/minimal-loop-metrics.md`.
- Added `scripts/run_real_agent_pilot.py`.
  - Default mode does not register a real model driver and records a reproducible adapter blocker.
  - `--allow-model-cost` is required before registering `CodexSDKDriver`.
- Added focused unit tests for admitted Planner output, rejected Planner output, missing real executor driver, and successful real executor scheduling with capability admission.

## Verification

Passed:

- `.venv\Scripts\python.exe -m unittest tests.test_real_agent_pilot -v`
- `.venv\Scripts\python.exe -m unittest tests.test_goal_operations tests.test_planning tests.test_node_executor -v`
- `.venv\Scripts\python.exe -B scripts\run_real_agent_pilot.py --mode mode_a_real_planner --output-dir <temp> --experiment-id SCRIPT-NOCOST --repetitions 1`
- `.venv\Scripts\python.exe -B scripts\check.py --lint`
- `git diff --check`
- `.venv\Scripts\python.exe -B scripts\lint_awkp.py`
- `.venv\Scripts\python.exe -B scripts\check.py --test`

Full unit test result: 189 tests passed, 2 skipped.

## Known Limitations

- The required five-run real model Mode A and Mode B pilot has not been executed in this increment.
- The script intentionally requires explicit `--allow-model-cost` before registering `CodexSDKDriver`.
- Current local environment check reports `openai_codex=missing`; the Codex SDK adapter must be installed before an authorized real model pilot can run through this script.
- Independent AWKP EvidenceGate review has not been run for TASK-0040.

## Next Action

Run or explicitly authorize the five-repetition Mode A and Mode B real-Agent pilots, then publish their scorecards and failure taxonomy for independent verification.
