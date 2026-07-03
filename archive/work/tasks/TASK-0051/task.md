---
type: WorkItem
id: TASK-0051
schema_version: awkp/0.1
title: Resolve current Mode C combined pilot stability
description: Diagnose, repair, and verify the current real Planner plus real Executor Mode C path after TASK-0050.
context_id: CTX-ahra-dynamic-kernel
priority: P0
risk_level: R2
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-28T15:16:05.166386Z
depends_on: [TASK-0050]
input_refs:
  - ../../../work/index.md
  - ../../../work/tasks/TASK-0048/evidence/mode-c-bounded-write-rerun-report.json
  - ../../../work/tasks/TASK-0049/evidence/latent-defect-matrix.json
  - ../../../work/tasks/TASK-0050/evidence/workflow-invariant-resolution.md
  - ../../../docs/architecture/authority-map.md
  - ../../../docs/architecture/framework-entrypoints.md
  - ../../../docs/architecture/component-inventory.json
  - ../../../docs/policies/minimal-loop-metrics.md
  - ../../../scripts/run_real_agent_pilot.py
  - ../../../src/ahra/real_agent_pilot.py
  - ../../../src/ahra/reference_runner/bounded_task.py
  - ../../../src/ahra/reference_runner/task_harness.py
  - ../../../src/ahra/adapters/codex_sdk.py
  - ../../../tests/test_real_agent_pilot.py
  - ../../../tests/test_node_executor.py
  - ../../../tests/test_codex_driver.py
output_contract:
  - kind: mode_c_current_blocker_or_stability_report
  - kind: verification_summary
  - kind: handoff
---

# Goal

Resolve the current Mode C combined path enough to know, from fresh evidence,
whether real Planner plus real Executor now completes the bounded M1 Goal
operation reliably under the existing safety envelope.

# Scope

- Run a fresh post-TASK-0050 Mode C pilot with explicit combined/model-cost
  authorization and isolated repetitions.
- If the pilot fails, classify the exact current failure layer and apply the
  smallest code or prompt-contract repair that does not weaken capability,
  gate, budget, timeout, scheduler, or EvidenceGate boundaries.
- If the pilot succeeds, publish the exact run evidence and state the remaining
  approval boundary.
- Preserve the default deterministic M1 path.

# Non-goals

- Do not promote Mode C to the default path inside this task.
- Do not weaken verification, capability admission, PlanIR validation, budget
  enforcement, or timeout enforcement to make Mode C pass.
- Do not claim production-grade orchestration.
- Do not self-complete this task; EvidenceGate decides completion.

# Acceptance criteria

- [ ] A fresh post-TASK-0050 Mode C run is executed with at least three isolated
  repetitions, or is blocked with an exact provider/setup/cost reason.
- [ ] Every failed repetition, if any, is classified with concrete artifacts,
  run result, scorecard, and code-path references.
- [ ] Any implemented repair is the smallest change needed for the classified
  failure and has deterministic regression coverage.
- [ ] If all repetitions pass, the report states exactly what this proves and
  what it does not prove.
- [ ] Targeted tests, lint, and diff checks pass, or failures are recorded as
  blockers with exact command output.
- [ ] Producer moves TASK-0051 only to review; EvidenceGate decides completion.

# Verification method

- .\.venv\Scripts\python.exe -B -m unittest tests.test_real_agent_pilot tests.test_node_executor tests.test_codex_driver tests.test_reference_runner
- .\.venv\Scripts\python.exe -B scripts\check.py --lint
- git diff --check
- Fresh Mode C pilot:
  .\.venv\Scripts\python.exe -B scripts\run_real_agent_pilot.py --mode mode_c_combined --output-dir work\tasks\TASK-0051\evidence\real-agent-pilot\mode-c-fresh --experiment-id TASK-0051-MODE-C --repetitions 3 --allow-model-cost --allow-combined --isolated-repetitions --repetition-timeout-seconds 180 --executor-idle-timeout-seconds 45 --executor-heartbeat-interval-seconds 10 --executor-attempt-wall-timeout-seconds 60 --executor-run-deadline-seconds 90

# Required evidence and handoff

- Publish `evidence/mode-c-current-blocker-or-stability-report.md`.
- Publish `evidence/verification-summary.json`.
- Publish `handoffs/HANDOFF-0001.md` with one exact next action.
