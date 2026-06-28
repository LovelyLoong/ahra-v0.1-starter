---
type: WorkItem
id: TASK-0045
schema_version: awkp/0.1
title: Run post-fix bounded Mode C closeout test
description: Re-run the combined real Planner and real Executor pilot after TASK-0044 timeout recovery, preserving no-go/default-path boundaries.
context_id: CTX-ahra-dynamic-kernel
priority: P1
risk_level: R2
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-28T08:04:07.611735Z
depends_on: [TASK-0043, TASK-0044]
input_refs:
  - ../../../work/tasks/TASK-0043/evidence/evidence-gate-report-4.json
  - ../../../work/tasks/TASK-0043/evidence/failure-taxonomy.json
  - ../../../work/tasks/TASK-0043/evidence/mode-c-decision.json
  - ../../../work/tasks/TASK-0044/evidence/evidence-gate-report-4.json
  - ../../../scripts/run_real_agent_pilot.py
  - ../../../src/ahra/real_agent_pilot.py
  - ../../../src/ahra/goal_operations.py
  - ../../../src/ahra/adapters/codex_sdk.py
output_contract:
  - kind: post_fix_mode_c_scorecard
  - kind: goal_inspect_summary
  - kind: model_runtime_failure_taxonomy
  - kind: closeout_go_no_go_decision
  - kind: verification_summary
---

# Goal

Run a bounded post-fix Mode C closeout test after TASK-0044. The task measures whether timeout recovery and audit reporting are now self-consistent during a real combined Planner plus bounded Executor run. It does not promote Mode C to the default path.

# Preconditions

- TASK-0043 is completed as a Mode C no-go evidence package.
- TASK-0044 is completed by independent EvidenceGate approval.
- Mode C is still non-default and requires explicit `--allow-combined`.
- The operator explicitly allows model cost and combined mode for this bounded closeout task only.

# Scope

- Run three isolated Mode C repetitions through `scripts/run_real_agent_pilot.py --mode mode_c_combined --allow-combined`.
- Preserve Planner outputs, Planner admission reports, invalid outputs, blockers, Executor artifacts, capability grants, audit records and Gate evidence.
- Independently inspect every run with durable GoalExecution state using `ahra goal inspect` and the run artifact directory.
- Check whether TASK-0044 timeout recovery eliminates synthetic skipped results for stateful child-process timeouts.
- Classify remaining failures as Planner contract, Executor/runtime, Gate/verification, provider/setup, environment, budget, or kernel defect.
- Publish a scorecard, inspection summary, failure taxonomy, verification summary and closeout go/no-go recommendation.

# Non-goals

- Do not promote Mode C to the default path.
- Do not change code for model quality, budget quality or prompt behavior in this task.
- Do not grant broader filesystem, process, network, secret or approval capability.
- Do not bypass PlanDraft validation, PlanIR compilation, Capability Admission, Scheduler, deterministic GateRunner or Evidence completion.
- Do not claim production readiness or model quality approval.
- Do not mark this task completed from the producer side; EvidenceGate decides completion.

# Acceptance criteria

- [ ] TASK-0043 and TASK-0044 are completed by EvidenceGate and Mode C remains non-default.
- [ ] Mode C is run only with explicit `--allow-combined` and `--allow-model-cost`.
- [ ] Three bounded isolated Mode C repetitions are executed, or a provider/setup blocker is classified without weakening criteria.
- [ ] Every run with durable GoalExecution state has independent `goal inspect --artifact-dir` evidence with zero missing artifacts and no artifact findings, or any exception is explicitly classified.
- [ ] Stateful isolated timeouts are recovered through TASK-0044 behavior: no synthetic skipped `runner_timeout` result is published when request and SQLite state exist.
- [ ] No recovered timeout leaves GoalExecution running while its active PlanExecution is terminal.
- [ ] Every real Planner output is admitted or rejected before any Executor side effect.
- [ ] Every observed Executor side effect is capability-admitted and auditable before execution.
- [ ] Hard safety counters remain zero for false completion, unrun gate pass, unadmitted node execution, stale fencing accept and duplicate resume effect.
- [ ] Provider token/cost usage is recorded per run when available; unavailable usage remains null, not fabricated.
- [ ] The final decision distinguishes timeout/audit correctness from combined model/runtime quality and gives a clear go/no-go recommendation.
- [ ] Producer moves task only to review; EvidenceGate decides completion.

# Verification method

- .\.venv\Scripts\python.exe -B scripts\run_real_agent_pilot.py --mode mode_c_combined --output-dir work\tasks\TASK-0045\evidence\real-agent-pilot\mode-c --experiment-id TASK-0045-MODE-C --repetitions 3 --allow-model-cost --allow-combined --isolated-repetitions --repetition-timeout-seconds 360
- .\.venv\Scripts\python.exe -m ahra.cli goal inspect <GEXEC> --db <run>\.ahra\goal-control.sqlite3 --artifact-dir <run>\.ahra\artifacts
- .\.venv\Scripts\python.exe -m unittest tests.test_real_agent_pilot tests.test_goal_operations tests.test_planning tests.test_codex_driver -v
- .\.venv\Scripts\python.exe -B scripts\check.py --lint
- .\.venv\Scripts\python.exe -B scripts\lint_awkp.py
- git diff --check

# Required evidence and handoff

- Publish post-fix Mode C scorecard, independent goal inspect summary, failure taxonomy, verification summary and closeout go/no-go decision.
- Map every acceptance criterion to Evidence IDs.
- Record exact command lines, code commit, provider/model revision when available, run artifact paths and SHA-256 digests.
- Create a handoff with one exact next action.
- Preserve TASK-0043/TASK-0044 interpretation: this task may prove the timeout recovery fix in live Mode C conditions, but Mode C remains non-default unless a separate EvidenceGate decision approves promotion.
