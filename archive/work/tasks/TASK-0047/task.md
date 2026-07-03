---
type: WorkItem
id: TASK-0047
schema_version: awkp/0.1
title: Classify and repair Mode C executor timeout root cause
description: Diagnose the Mode C bounded Executor timeout root cause and apply a minimal runtime-stability fix without defaultizing Mode C.
context_id: CTX-ahra-dynamic-kernel
priority: P0
risk_level: R2
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-28T12:16:26.961005Z
depends_on: [TASK-0045, TASK-0046]
input_refs:
  - ../../../work/tasks/TASK-0045/evidence/failure-taxonomy.json
  - ../../../work/tasks/TASK-0045/evidence/goal-inspect-summary.json
  - ../../../work/tasks/TASK-0045/evidence/mode-c-decision.json
  - ../../../work/tasks/TASK-0045/evidence/real-agent-pilot/mode-c/scorecard.json
  - ../../../work/tasks/TASK-0045/evidence/real-agent-pilot/mode-c/run-01/run-result.json
  - ../../../src/ahra/plan_execution.py
  - ../../../src/ahra/reference_runner/bounded_task.py
  - ../../../src/ahra/reference_runner/standard_harness.py
  - ../../../src/ahra/adapters/codex_sdk.py
  - ../../../scripts/run_real_agent_pilot.py
output_contract:
  - kind: root_cause_report
  - kind: minimal_runtime_patch
  - kind: verification_summary
  - kind: mode_c_rerun_report
  - kind: handoff
---

# Goal

Classify the root cause of the Mode C timeout observed in TASK-0045 and apply
the smallest runtime-stability fix that makes the timeout boundary self-close
inside the child run instead of depending on the isolated repetition watchdog.

# Scope

- Reproduce the timeout class with a deterministic or fake-driver test.
- Attribute whether the failure is planner output, scheduler timeout handling,
  bounded Executor runtime behavior, Codex SDK cancellation behavior, or the
  isolated repetition watchdog.
- Apply only the minimal code change needed for the root cause.
- Preserve existing safety boundaries, capability admission, EvidenceGate
  authority, and non-default Mode C status.
- Run bounded local verification and, if live provider execution is available
  and explicitly bounded, one post-fix Mode C repetition.

# Non-goals

- Do not promote Mode C to the default path.
- Do not run a broad three-repetition Mode C pilot unless a later task
  explicitly authorizes it.
- Do not weaken node, gate, capability, budget, or EvidenceGate checks.
- Do not reinterpret TASK-0045 no-go as a success.
- Do not self-complete this task; EvidenceGate decides completion.

# Acceptance criteria

- [ ] The TASK-0045 timeout is classified with a concrete root cause and
  supporting code/evidence references.
- [ ] A deterministic regression test fails before the fix or otherwise proves
  the failure mode using a fake/non-cancellable AgentDriver.
- [ ] The minimal runtime patch ensures node/attempt timeout paths return
  terminal failure evidence without waiting indefinitely for a stuck real
  AgentDriver cancellation cleanup.
- [ ] Existing deterministic tests for plan execution, node execution, Codex
  adapter behavior, and real-agent pilot timeout recovery still pass.
- [ ] A bounded Mode C rerun is either executed once and reported, or blocked
  with a concrete provider/setup/cost reason; no default-path claim is made.
- [ ] Producer moves TASK-0047 only to review; EvidenceGate decides completion.

# Verification method

- .\.venv\Scripts\python.exe -m unittest tests.test_node_executor tests.test_plan_execution tests.test_codex_driver tests.test_real_agent_pilot
- .\.venv\Scripts\python.exe -B scripts\check.py --lint
- git diff --check
- Optional, bounded live rerun when available:
  .\.venv\Scripts\python.exe -B scripts\run_real_agent_pilot.py --mode mode_c_combined --output-dir work\tasks\TASK-0047\evidence\real-agent-pilot\mode-c --experiment-id TASK-0047-MODE-C --repetitions 1 --allow-model-cost --allow-combined --isolated-repetitions --repetition-timeout-seconds 240 --executor-attempt-wall-timeout-seconds 60 --executor-run-deadline-seconds 90

# Required evidence and handoff

- Publish `evidence/root-cause-report.md`.
- Publish `evidence/verification-summary.json`.
- Publish `evidence/mode-c-rerun-report.json` or a blocked-rerun report with
  exact reason.
- Publish `handoffs/HANDOFF-0001.md` with one exact next action.
