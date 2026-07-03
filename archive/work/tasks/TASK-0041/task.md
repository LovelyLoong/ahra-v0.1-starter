---
type: WorkItem
id: TASK-0041
schema_version: awkp/0.1
title: Harden real Planner PlanDraft contract adherence
description: Improve the real Planner Mode A path so model output adheres to the PlanDraft contract or fails closed with audit-grade invalid-output evidence.
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
  - ../../../docs/architecture/plan-ir.md
  - ../../../docs/policies/agent-authority-boundaries.md
  - ../../../src/ahra/planning.py
  - ../../../src/ahra/real_agent_pilot.py
  - ../../../src/ahra/adapters/codex_sdk.py
  - ../../../work/tasks/TASK-0040/
output_contract:
  - kind: planner_contract_hardening
  - kind: mode_a_scorecard
  - kind: invalid_output_evidence
  - kind: go_no_go_recommendation
---

# Goal

Make the real Planner Mode A path produce host-admissible PlanDraft output more reliably without weakening PlanDraft, PlanIR, Capability Admission, GateRunner, Evidence or Completion boundaries.

# Scope

- Analyze TASK-0040 Mode A invalid Planner outputs and their preserved raw/driver artifacts.
- Tighten the real Planner request/output contract for the minimum PlanDraft fields required by the current compiler.
- Keep Planner read-only and unable to grant capabilities, execute tools, modify Goals/Claims/Gates, or declare completion.
- Preserve every invalid Planner raw output and parsed driver output as artifacts.
- Re-run at least five Mode A repetitions after the change.
- Publish a scorecard and recommendation that keeps Mode C no-go unless Mode A and Mode B preconditions are actually satisfied.

# Non-goals

- Do not change Mode B executor timeout handling in this task.
- Do not run combined Mode C.
- Do not lower PlanDraft or PlanIR validation requirements.
- Do not silently coerce semantic meaning, Claims, Gates, Runtime refs, capability scope or Goal identity.
- Do not hide malformed model output by replacing it with deterministic fixture output.

# Acceptance criteria

- [ ] Real Planner prompt/output contract explicitly names the required PlanDraft fields used by the compiler.
- [ ] Planner output is still admitted or rejected before any execution.
- [ ] Any adapter normalization is deterministic, minimal, documented and covered by tests; it must not weaken Goal, Claim, Gate, Runtime or capability boundaries.
- [ ] Invalid raw Planner output and parsed driver output remain preserved as artifacts with digests.
- [ ] At least five post-change Mode A repetitions are executed, or a setup blocker is classified without weakening criteria.
- [ ] At least one Mode A run produces an admitted PlanDraft, or the report identifies a narrower reproducible model/adapter blocker than TASK-0040.
- [ ] Hard safety metrics remain zero for false completion, unrun gate pass, unadmitted node execution, stale fencing accept and duplicate resume effect.
- [ ] Token, cost, latency, plan size and rejection/admission metrics are recorded per run when available; unavailable provider usage is recorded as null, not fabricated.
- [ ] Final report distinguishes model contract adherence from kernel defects.
- [ ] Independent verifier approves the TASK-0041 report before completion.

# Verification method

- .\\.venv\\Scripts\\python.exe -m unittest tests.test_planning tests.test_real_agent_pilot -v
- .\\.venv\\Scripts\\python.exe -B scripts\\run_real_agent_pilot.py --mode mode_a_real_planner --output-dir work\\tasks\\TASK-0041\\evidence\\real-agent-pilot\\mode-a --experiment-id TASK-0041-MODE-A --repetitions 5 --allow-model-cost --isolated-repetitions --repetition-timeout-seconds 120
- .\\.venv\\Scripts\\python.exe -B scripts\\check.py --lint
- .\\.venv\\Scripts\\python.exe -B scripts\\lint_awkp.py
- git diff --check

# Required evidence and handoff

- Publish implementation notes, Mode A scorecard, invalid-output artifact index and verification summary.
- Map each acceptance criterion to Evidence IDs.
- Record code commit, model/provider/revision where available, Context Manifest refs, and run artifact paths.
- Create a handoff with one exact next action.
- Producer must not mark TASK-0041 complete; EvidenceGate decides completion.
