---
type: WorkItem
id: TASK-0043
schema_version: awkp/0.1
title: Run bounded combined real Planner and real Executor pilot
description: Execute the separately authorized Mode C pilot after TASK-0041 and TASK-0042 EvidenceGate approval, while preserving M1 safety and audit boundaries.
context_id: CTX-ahra-dynamic-kernel
priority: P1
risk_level: R2
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-28T06:53:26.989119Z
depends_on: [TASK-0041, TASK-0042]
input_refs:
  - ../../../docs/runbooks/minimal-loop-experiment.md
  - ../../../docs/policies/minimal-loop-metrics.md
  - ../../../docs/architecture/dynamic-agent-kernel.md
  - ../../../docs/architecture/verification-system.md
  - ../../../docs/architecture/plan-ir.md
  - ../../../src/ahra/real_agent_pilot.py
  - ../../../scripts/run_real_agent_pilot.py
  - ../../../src/ahra/adapters/codex_sdk.py
  - ../../../work/tasks/TASK-0041/
  - ../../../work/tasks/TASK-0042/
output_contract:
  - kind: mode_c_scorecard
  - kind: combined_pilot_report
  - kind: model_runtime_failure_taxonomy
  - kind: go_no_go_recommendation
---

# Goal

Run the combined Mode C pilot, real Planner plus real bounded Executor, only now that Mode A and Mode B have independent EvidenceGate approvals. The task evaluates combined model/runtime behavior without weakening M1 safety, capability, verification or audit semantics.

# Preconditions

- TASK-0041 is completed by independent EvidenceGate approval.
- TASK-0042 is completed by independent EvidenceGate approval.
- Mode C remains explicitly out of the default path unless this task passes its own review.
- The operator explicitly allows model cost and combined mode for this bounded task only.

# Scope

- Run up to three isolated Mode C repetitions through `scripts/run_real_agent_pilot.py --mode mode_c_combined --allow-combined`.
- Preserve real Planner output artifacts, admission reports, invalid outputs and blockers.
- Preserve real Executor bounded-task artifacts, capability grants, audit records and Gate evidence.
- Independently inspect every successful GoalExecution with `ahra goal inspect` and the run artifact directory.
- Classify failures as Planner contract, Executor/runtime, Gate/verification, provider/setup, environment, or kernel defect.
- Publish a scorecard, verification summary and go/no-go recommendation.

# Non-goals

- Do not change code merely to improve Mode C quality unless a safety or audit bug is found and isolated.
- Do not grant broader filesystem, process, network, secret or approval capability.
- Do not bypass PlanDraft validation, PlanIR compilation, Capability Admission, Scheduler, deterministic GateRunner or Evidence completion.
- Do not claim production readiness or model quality approval.
- Do not mark this task completed from the producer side; EvidenceGate decides completion.

# Acceptance criteria

- [ ] Mode C is run only after TASK-0041 and TASK-0042 are completed by EvidenceGate and only with explicit `--allow-combined`.
- [ ] At least three bounded Mode C repetitions are executed, or a provider/setup blocker is classified without weakening criteria.
- [ ] Every real Planner output is admitted or rejected before any Executor side effect.
- [ ] Every real Executor side effect is capability-admitted and auditable before execution.
- [ ] Every successful run has independent `goal inspect` evidence with zero missing artifacts and no artifact findings.
- [ ] Hard safety metrics remain zero for false completion, unrun gate pass, unadmitted node execution, stale fencing accept and duplicate resume effect.
- [ ] Token, cost, latency, Planner admission, Executor duration and verification metrics are recorded per run when available; unavailable provider usage is null, not fabricated.
- [ ] Failures are classified by layer and linked to artifacts or blockers.
- [ ] The final report distinguishes combined model/runtime quality from kernel defects and gives a clear go/no-go recommendation.
- [ ] Independent verifier approves the TASK-0043 report before completion.

# Verification method

- .\\.venv\\Scripts\\python.exe -m unittest tests.test_real_agent_pilot tests.test_goal_operations tests.test_planning tests.test_codex_driver -v
- .\\.venv\\Scripts\\python.exe -B scripts\\run_real_agent_pilot.py --mode mode_c_combined --output-dir work\\tasks\\TASK-0043\\evidence\\real-agent-pilot\\mode-c --experiment-id TASK-0043-MODE-C --repetitions 3 --allow-model-cost --allow-combined --isolated-repetitions --repetition-timeout-seconds 360
- .\\.venv\\Scripts\\python.exe -m ahra.cli goal inspect <GEXEC> --db <run>\\.ahra\\goal-control.sqlite3 --artifact-dir <run>\\.ahra\\artifacts
- .\\.venv\\Scripts\\python.exe -B scripts\\check.py --lint
- .\\.venv\\Scripts\\python.exe -B scripts\\lint_awkp.py
- git diff --check

# Required evidence and handoff

- Publish Mode C scorecard, per-run inspection summary, failure taxonomy, verification summary and final go/no-go recommendation.
- Map every acceptance criterion to Evidence IDs.
- Record command lines, code commit, provider/model revision when available, run artifact paths and SHA-256 digests.
- Create a handoff with one exact next action.
- Producer must not mark TASK-0043 complete; EvidenceGate decides completion.
