---
type: WorkItem
id: TASK-0049
schema_version: awkp/0.1
title: Current workflow integrity preview and latent defect audit
description: Audit the current AHRA workflow shape before any wider Mode C work, focusing on hidden workflow defects rather than Mode C defaultization.
context_id: CTX-ahra-dynamic-kernel
priority: P0
risk_level: R1
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-28T14:04:34.285055Z
depends_on: [TASK-0048]
input_refs:
  - ../../../work/index.md
  - ../../../docs/architecture/authority-map.md
  - ../../../docs/architecture/framework-entrypoints.md
  - ../../../docs/architecture/component-inventory.json
  - ../../../docs/architecture/dynamic-agent-kernel.md
  - ../../../docs/architecture/verification-system.md
  - ../../../docs/architecture/plan-ir.md
  - ../../../docs/policies/agent-authority-boundaries.md
  - ../../../docs/policies/component-lifecycle.md
  - ../../../src/ahra/goal_operations.py
  - ../../../src/ahra/plan_execution.py
  - ../../../src/ahra/reference_runner/bounded_task.py
  - ../../../src/ahra/reference_runner/standard_harness.py
  - ../../../src/ahra/real_agent_pilot.py
  - ../../../scripts/run_real_agent_pilot.py
  - ../../../work/tasks/TASK-0045/evidence/failure-taxonomy.json
  - ../../../work/tasks/TASK-0047/evidence/root-cause-report.md
  - ../../../work/tasks/TASK-0048/evidence/executor-timeout-root-cause-report.md
  - ../../../work/tasks/TASK-0048/evidence/evidence-gate-report-4.json
output_contract:
  - kind: workflow_integrity_map
  - kind: latent_defect_matrix
  - kind: verification_summary
  - kind: handoff
---

# Goal

Preview the current AHRA workflow as a whole before opening any wider Mode C
work. The task must identify whether the previous Mode C failures point to
hidden workflow defects, and must keep default M1, Mode C pilot, and AWKP
EvidenceGate boundaries separate.

# Scope

- Map the current default M1 Goal operation path.
- Map the explicit Mode C real-Agent pilot path.
- Map the AWKP task, artifact, evidence, and EvidenceGate completion path.
- Classify hidden workflow defects already exposed by TASK-0045 through
  TASK-0048.
- Identify any remaining P0/P1 workflow risks that should block wider Mode C
  work.
- Run a minimal default M1 smoke check and static/local verification sufficient
  for this audit.

# Non-goals

- Do not promote Mode C to the default path.
- Do not run a broad Mode C pilot.
- Do not change runtime code unless the audit finds a concrete P0/P1 workflow
  defect that cannot be safely deferred.
- Do not reinterpret TASK-0048's single successful bounded rerun as broad Mode C
  stability.
- Do not turn this task into release checkpoint packaging.
- Do not self-complete this task; EvidenceGate decides completion.

# Acceptance criteria

- [ ] A workflow map separately describes the default M1 Goal path, the Mode C
  pilot path, and the AWKP EvidenceGate path with code/doc evidence.
- [ ] The audit states whether the current default M1 path appears intact, with
  fresh smoke evidence or a concrete blocker.
- [ ] A latent-defect matrix classifies TASK-0045 through TASK-0048 failure
  signals as workflow, adapter, provider/runtime, model-behavior, or evidence
  boundary issues.
- [ ] The matrix identifies remaining P0/P1 workflow risks and whether they
  block broader Mode C work.
- [ ] Any proposed TASK-0050 follow-up is narrow and preserves Mode C
  non-default status.
- [ ] No Mode C default-path claim is made.
- [ ] Producer moves TASK-0049 only to review; EvidenceGate decides completion.

# Verification method

- .\.venv\Scripts\python.exe -B -m ahra.cli goal validate <temp-request>
- .\.venv\Scripts\python.exe -B -m ahra.cli goal plan <temp-request>
- .\.venv\Scripts\python.exe -B -m ahra.cli goal start <temp-request>
- .\.venv\Scripts\python.exe -B scripts\check.py --lint
- git diff --check

# Required evidence and handoff

- Publish `evidence/workflow-integrity-map.md`.
- Publish `evidence/latent-defect-matrix.json`.
- Publish `evidence/verification-summary.json`.
- Publish `handoffs/HANDOFF-0001.md` with one exact next action.
