---
type: WorkItem
id: TASK-0048
schema_version: awkp/0.1
title: Repair live Executor bounded-write completion timeout
description: Diagnose and minimally repair the remaining live Mode C bounded-write Executor timeout without defaultizing Mode C.
context_id: CTX-ahra-dynamic-kernel
priority: P0
risk_level: R2
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-28T13:04:50.987271Z
depends_on: [TASK-0047]
input_refs:
  - ../../../work/tasks/TASK-0047/evidence/mode-c-rerun-report.json
  - ../../../work/tasks/TASK-0047/evidence/root-cause-report.md
  - ../../../work/tasks/TASK-0047/evidence/evidence-gate-report-4.json
  - ../../../work/tasks/TASK-0047/evidence/real-agent-pilot/mode-c-daemon-executor/scorecard.json
  - ../../../work/tasks/TASK-0047/evidence/real-agent-pilot/mode-c-daemon-executor/run-01/run-result.json
  - ../../../src/ahra/adapters/codex_sdk.py
  - ../../../src/ahra/reference_runner/bounded_task.py
  - ../../../src/ahra/reference_runner/standard_harness.py
  - ../../../src/ahra/plan_execution.py
  - ../../../scripts/run_real_agent_pilot.py
output_contract:
  - kind: executor_timeout_root_cause_report
  - kind: minimal_runtime_patch
  - kind: verification_summary
  - kind: mode_c_bounded_write_rerun_report
  - kind: handoff
---

# Goal

Classify and repair the remaining live Mode C bounded-write completion timeout
observed after TASK-0047. The target is the real Executor bounded-write node
only: make it complete the required bounded artifact or produce a more precise
fail-closed error inside the bounded execution window.

# Scope

- Inspect the post-TASK-0047 live Mode C evidence for the exact Executor prompt,
  workspace state, emitted SDK events, and missing artifact/evidence boundary.
- Attribute whether the remaining failure is caused by Executor prompt
  contract, output parsing, artifact path expectations, capability scope,
  bounded-task result mapping, scheduler timeout policy, or provider runtime.
- Apply the smallest code or prompt-contract change needed for the bounded
  write node to complete under the existing safety envelope.
- Preserve planner admission, capability admission, budget checks, gate checks,
  EvidenceGate authority, and Mode C non-default status.
- Run deterministic regression tests and one bounded live Mode C repetition if
  provider execution is available.

# Non-goals

- Do not promote Mode C to the default path.
- Do not run a broad three-repetition pilot unless a later task authorizes it.
- Do not weaken node timeout, gate, capability, budget, or EvidenceGate checks.
- Do not reinterpret TASK-0047 as live Mode C success.
- Do not self-complete this task; EvidenceGate decides completion.

# Acceptance criteria

- [ ] The remaining live bounded-write timeout is classified with concrete
  code/evidence references.
- [ ] A deterministic regression test covers the classified failure mode or the
  corrected bounded Executor contract.
- [ ] The minimal patch makes the bounded-write Executor produce the required
  artifact/evidence in a bounded run, or proves with precise evidence that the
  provider/runtime is the blocker.
- [ ] Existing deterministic tests for bounded task execution, plan execution,
  Codex adapter behavior, and real-agent pilot handling still pass.
- [ ] One bounded live Mode C rerun is executed and reported, or blocked with a
  concrete provider/setup/cost reason.
- [ ] No Mode C default-path claim is made.
- [ ] Producer moves TASK-0048 only to review; EvidenceGate decides completion.

# Verification method

- .\.venv\Scripts\python.exe -m unittest tests.test_node_executor tests.test_plan_execution tests.test_codex_driver tests.test_real_agent_pilot
- .\.venv\Scripts\python.exe -B scripts\check.py --lint
- git diff --check
- Optional bounded live rerun:
  .\.venv\Scripts\python.exe -B scripts\run_real_agent_pilot.py --mode mode_c_combined --output-dir work\tasks\TASK-0048\evidence\real-agent-pilot\mode-c-bounded-write --experiment-id TASK-0048-MODE-C --repetitions 1 --allow-model-cost --allow-combined --isolated-repetitions --repetition-timeout-seconds 180 --executor-idle-timeout-seconds 45 --executor-heartbeat-interval-seconds 10 --executor-attempt-wall-timeout-seconds 60 --executor-run-deadline-seconds 90

# Required evidence and handoff

- Publish `evidence/executor-timeout-root-cause-report.md`.
- Publish `evidence/verification-summary.json`.
- Publish `evidence/mode-c-bounded-write-rerun-report.json` or a blocked-rerun
  report with exact reason.
- Publish `handoffs/HANDOFF-0001.md` with one exact next action.
