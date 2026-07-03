---
type: WorkItem
id: TASK-0050
schema_version: awkp/0.1
title: Close real bounded Executor workflow invariants
description: Resolve the remaining P1 workflow risks from TASK-0049 before any broader Mode C work.
context_id: CTX-ahra-dynamic-kernel
priority: P0
risk_level: R1
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-28T14:32:06.820347Z
depends_on: [TASK-0049]
input_refs:
  - ../../../work/index.md
  - ../../../docs/architecture/authority-map.md
  - ../../../docs/architecture/framework-entrypoints.md
  - ../../../docs/architecture/component-inventory.json
  - ../../../docs/architecture/dynamic-agent-kernel.md
  - ../../../docs/architecture/verification-system.md
  - ../../../docs/architecture/plan-ir.md
  - ../../../docs/policies/component-lifecycle.md
  - ../../../docs/policies/agent-authority-boundaries.md
  - ../../../src/ahra/real_agent_pilot.py
  - ../../../src/ahra/reference_runner/bounded_task.py
  - ../../../src/ahra/reference_runner/standard_harness.py
  - ../../../src/ahra/plan_execution.py
  - ../../../tests/test_real_agent_pilot.py
  - ../../../tests/test_node_executor.py
  - ../../../tests/test_reference_runner.py
  - ../TASK-0048/evidence/executor-timeout-root-cause-report.md
  - ../TASK-0049/evidence/latent-defect-matrix.json
  - ../TASK-0049/evidence/evidence-gate-report-4.json
output_contract:
  - kind: workflow_invariant_resolution
  - kind: verification_summary
  - kind: handoff
---

# Goal

Close the remaining P1 workflow-invariant risks identified by TASK-0049 so the
project can stop re-litigating the same workflow boundary issues before deciding
whether to run any separate broader Mode C pilot.

# Scope

- Align the real bounded Executor dependency chain with component lifecycle
  documentation so default-visible real-Executor work does not silently depend
  on an undocumented legacy component boundary.
- Add Mode C pilot scorecard failure dimensions that separate contract, gate,
  budget, scheduler, provider/runtime, and model-behavior failures.
- Make the real Executor budget normalization invariant explicit and covered by
  local verification.
- Add deterministic invariant coverage for non-literal output resources and
  multi-output expectedOutputs so the bounded Executor contract boundary is not
  inferred from the single literal bounded-write case.
- Publish evidence that maps the four TASK-0049 P1 risks to the actual changes
  and remaining limits.

# Non-goals

- Do not promote Mode C to the default path.
- Do not run a broad live Mode C pilot.
- Do not reinterpret TASK-0048's single successful bounded rerun as broad Mode C
  stability.
- Do not package a release checkpoint.
- Do not migrate or rewrite the whole legacy standard-harness module unless the
  minimal dependency-alignment fix proves insufficient.
- Do not self-complete this task; EvidenceGate decides completion.

# Acceptance criteria

- [ ] The BoundedTaskExecutor to TaskHarness dependency is no longer ambiguous
  in code imports and component lifecycle documentation.
- [ ] Mode C pilot scorecards include workflow failure dimensions sufficient to
  distinguish contract, gate, budget, scheduler, provider/runtime, and
  model-behavior failures.
- [ ] The real Executor budget normalization invariant is documented or exposed
  in evidence and has targeted test coverage.
- [ ] Non-literal output resources and multi-output expectedOutputs have
  deterministic invariant coverage without weakening literal artifact checks.
- [ ] A workflow-invariant resolution report maps each TASK-0049 P1 risk to the
  implemented mitigation and states any remaining no-go boundary.
- [ ] Targeted tests, lint, and diff checks pass, or any failure is recorded as a
  blocker with exact command output.
- [ ] Producer moves TASK-0050 only to review; EvidenceGate decides completion.

# Verification method

- .\.venv\Scripts\python.exe -B -m unittest tests.test_real_agent_pilot tests.test_node_executor tests.test_reference_runner
- .\.venv\Scripts\python.exe -B scripts\check.py --lint
- .\.venv\Scripts\python.exe -B scripts\check.py --test
- git diff --check

# Required evidence and handoff

- Publish `evidence/workflow-invariant-resolution.md`.
- Publish `evidence/verification-summary.json`.
- Publish `handoffs/HANDOFF-0001.md` with one exact next action.
