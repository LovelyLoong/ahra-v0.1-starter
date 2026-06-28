---
type: WorkItem
id: TASK-0042
schema_version: awkp/0.1
title: Stabilize real Executor bounded runtime timeouts
description: Investigate and improve Mode B real bounded Executor runtime stability without mixing it with real Planner uncertainty.
context_id: CTX-ahra-dynamic-kernel
priority: P1
risk_level: R2
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-28T05:11:09.310201Z
depends_on: [TASK-0040]
input_refs:
  - ../../../docs/runbooks/minimal-loop-experiment.md
  - ../../../docs/policies/minimal-loop-metrics.md
  - ../../../src/ahra/real_agent_pilot.py
  - ../../../src/ahra/reference_runner/bounded_task.py
  - ../../../src/ahra/adapters/codex_sdk.py
  - ../../../work/tasks/TASK-0040/
output_contract:
  - kind: executor_runtime_stability_report
  - kind: mode_b_scorecard
  - kind: timeout_taxonomy
  - kind: go_no_go_recommendation
---

# Goal

Reduce or explain Mode B real bounded Executor timeouts while preserving M1 safety, capability admission, deterministic GateRunner and Evidence semantics.

# Scope

- Analyze TASK-0040 Mode B timeout runs and the one successful run.
- Keep deterministic Planner and deterministic GateRunner fixed.
- Improve runtime timeout classification, executor request bounding or adapter handling only where it does not weaken safety criteria.
- Re-run at least five Mode B repetitions after TASK-0041 is handled, unless an environment/setup blocker is explicitly recorded.
- Keep Mode C no-go until Mode A and Mode B both satisfy the policy preconditions.

# Non-goals

- Do not change real Planner behavior in this task.
- Do not run combined Mode C.
- Do not grant broader filesystem, process, network or secret capabilities to make Executor success easier.
- Do not treat timeout absence as correctness; deterministic Gate evidence remains mandatory.

# Acceptance criteria

- [ ] Mode B timeout root causes are classified as model latency, adapter process control, prompt/tool contract, environment setup, or kernel defect.
- [ ] Every Executor side effect remains capability-admitted before execution.
- [ ] At least five post-change Mode B repetitions are executed, or a setup blocker is classified without weakening criteria.
- [ ] At least one Mode B run completes successfully, or the report identifies a reproducible executor/runtime blocker.
- [ ] Hard safety metrics remain zero for false completion, unrun gate pass, unadmitted node execution, stale fencing accept and duplicate resume effect.
- [ ] Token, cost, latency, executor duration and verification cost are recorded per run when available.
- [ ] Final report distinguishes runtime/model reliability from kernel defects.
- [ ] Independent verifier approves the TASK-0042 report before completion.

# Verification method

- .\\.venv\\Scripts\\python.exe -m unittest tests.test_real_agent_pilot tests.test_goal_operations -v
- .\\.venv\\Scripts\\python.exe -B scripts\\run_real_agent_pilot.py --mode mode_b_real_executor --output-dir work\\tasks\\TASK-0042\\evidence\\real-agent-pilot\\mode-b --experiment-id TASK-0042-MODE-B --repetitions 5 --allow-model-cost --isolated-repetitions --repetition-timeout-seconds 120
- .\\.venv\\Scripts\\python.exe -B scripts\\check.py --lint
- .\\.venv\\Scripts\\python.exe -B scripts\\lint_awkp.py
- git diff --check

# Required evidence and handoff

- Publish timeout taxonomy, Mode B scorecard, successful-run lineage or blocker report, and verification summary.
- Map each acceptance criterion to Evidence IDs.
- Create a handoff with one exact next action.
- Producer must not mark TASK-0042 complete; EvidenceGate decides completion.
