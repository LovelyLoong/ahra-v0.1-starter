---
type: WorkItem
id: TASK-0044
schema_version: awkp/0.1
title: Fix Mode C isolated timeout partial-run recovery
description: Recover durable child-run state after isolated Mode C timeouts and finalize GoalExecution consistently when the active PlanExecution is terminal.
context_id: CTX-ahra-dynamic-kernel
priority: P1
risk_level: R2
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-28T07:35:49.642192Z
depends_on: [TASK-0043]
input_refs:
  - ../../../work/tasks/TASK-0043/evidence/evidence-gate-report-4.json
  - ../../../work/tasks/TASK-0043/evidence/failure-taxonomy.json
  - ../../../work/tasks/TASK-0043/evidence/mode-c-decision.json
  - ../../../scripts/run_real_agent_pilot.py
  - ../../../src/ahra/real_agent_pilot.py
  - ../../../src/ahra/goal_operations.py
  - ../../../src/ahra/plan_execution.py
  - ../../../tests/test_real_agent_pilot.py
  - ../../../tests/test_goal_operations.py
output_contract:
  - kind: code_change
  - kind: timeout_recovery_report
  - kind: regression_test_summary
---

# Goal

Fix the specific audit inconsistency approved in TASK-0043: isolated Mode C child-process timeouts must recover partial durable run state instead of publishing a synthetic skipped run when the child already wrote Planner, PlanExecution, NodeRun, capability or artifact evidence.

# Scope

- When an isolated repetition times out, inspect the run directory for `goal-run-request.yaml`, `.ahra/goal-control.sqlite3` and `.ahra/artifacts`.
- If the active PlanExecution is terminal but the parent GoalExecution is still non-terminal, finalize the active GoalExecution through the normal Goal operation service semantics.
- Publish a recovered run-result that reflects actual Planner admission artifacts, GoalExecution/PlanExecution status, metrics, refs and failure_class.
- Preserve synthetic `runner_timeout` only when no durable child-run state can be recovered.
- Add regression tests for timeout recovery and GoalExecution finalization after a terminal active PlanExecution.

# Non-goals

- Do not promote Mode C to the default path.
- Do not change capability grants, filesystem scope, approval policy, GateRunner semantics or Completion criteria.
- Do not relax provider token/cost reporting; unavailable provider usage remains null.
- Do not solve model quality or Executor budget quality in this task.
- Do not rerun a full paid Mode C pilot as acceptance for this fix unless a later task authorizes it.

# Acceptance criteria

- [ ] TASK-0043 remains completed as a no-go evidence package and Mode C remains non-default.
- [ ] Timeout recovery prefers durable child-run evidence over synthetic skipped results when a timed-out isolated child wrote a request and SQLite store.
- [ ] A GoalExecution left running with an active terminal failed PlanExecution is finalized to failed through the normal service path.
- [ ] Recovered timeout run-result includes actual `goalExecutionId`, `planExecutionId`, `goalStatus`, `planStatus`, metrics and failure_class.
- [ ] Planner status is reconstructed from preserved Planner/admission artifacts when wrapper stdout/stderr is unavailable.
- [ ] If no durable state exists, the existing `runner_timeout` blocked behavior is preserved.
- [ ] Provider token/cost unavailable fields remain null, not fabricated.
- [ ] Regression tests cover recovered timeout state and no-state timeout fallback.
- [ ] Local verification runs the focused real-agent/goal-operation tests plus lint and diff checks.
- [ ] Producer moves task only to review; EvidenceGate decides completion.

# Verification method

- .\.venv\Scripts\python.exe -m unittest tests.test_real_agent_pilot tests.test_goal_operations -v
- .\.venv\Scripts\python.exe -B scripts\check.py --lint
- .\.venv\Scripts\python.exe -B scripts\lint_awkp.py
- git diff --check

# Required evidence and handoff

- Publish a focused timeout recovery report with before/after behavior and test results.
- Record exact code paths changed and commands run.
- Preserve TASK-0043 no-go interpretation: this is a recovery/audit fix, not Mode C approval.
