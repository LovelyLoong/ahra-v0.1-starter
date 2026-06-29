---
type: WorkItem
id: TASK-0060
schema_version: awkp/0.1
title: Bridge a GoalExecution to an AWKP task
description: Connect the two parallel worlds so a completed GoalExecution advances a corresponding AWKP task, with kernel GateRun evidence feeding the AWKP EvidenceGate decision.
context_id: CTX-workflow-autonomy
priority: P1
risk_level: R2
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-29T11:00:00Z
depends_on: [TASK-0059]
input_refs:
  - ../../../src/ahra/goal_operations.py
  - ../../../src/ahra/evidence_gate.py
  - ../../../src/ahra/verification.py
  - ../../../docs/architecture/authority-map.md
output_contract:
  - kind: goal_awkp_bridge_report
  - kind: verification_summary
  - kind: handoff
---

# Goal

Unify the two parallel universes. Today `goal_operations.py` has zero reference
to `work/tasks`, `task.md`, or EvidenceGate; a completed GoalExecution advances
no AWKP task. TASK-0055 already made the AWKP gate review kernel evidence
lineage - this task completes the bridge so a GoalExecution and an AWKP task are
two views of one unit of work, and the kernel's GateRun evidence feeds the AWKP
EvidenceGate decision.

# Scope

- Define and implement a bridge that associates a GoalExecution with an AWKP
  task (id mapping recorded durably and in task events), so a completed
  GoalExecution drives the AWKP task toward review/completion through the
  governed writer (TASK-0057) and orchestrator (TASK-0059).
- Feed the kernel's real GateRun EvidenceV2 (from TASK-0053..0056) into the AWKP
  EvidenceGate evidence-lineage review (TASK-0055), so the AWKP completion
  decision rests on kernel-produced evidence.
- Record the bridge concept in the authority map (one active owner), per the
  doc-governance rule.

# Non-goals

- Do not build the Agent-assisted GoalExecutionRequest authoring here (that is
  Phase 1).
- Do not let the kernel self-complete an AWKP task; EvidenceGate plus a distinct
  verifier still decides.
- Do not break the existing standalone Goal path or the standalone AWKP path.
- Do not self-complete this task; EvidenceGate decides completion.

# Acceptance criteria

- [ ] A GoalExecution can be durably associated with an AWKP task id, and the
  association is recorded in the task's append-only events, covered by a test.
- [ ] A completed GoalExecution advances its associated AWKP task toward
  review/completion via the governed CAS writer and orchestrator, not by
  hand-edit, covered by a test.
- [ ] The kernel's real GateRun EvidenceV2 is consumed by the AWKP
  EvidenceGate evidence-lineage review (TASK-0055), so AWKP completion rests on
  kernel-produced evidence, covered by a test.
- [ ] The producer != verifier boundary still holds across the bridge; the
  kernel cannot self-complete the AWKP task.
- [ ] The bridge concept has exactly one active owner entry in
  `docs/architecture/authority-map.md`, and the AWKP linter passes.
- [ ] The standalone Goal path and standalone AWKP path both still work
  (regression).
- [ ] Targeted tests, lint, and diff checks pass, or any failure is recorded as
  a blocker with exact command output.
- [ ] Producer moves TASK-0060 only to review; EvidenceGate decides completion.

# Verification method

- .\.venv\Scripts\python.exe -B -m unittest tests.test_goal_operations tests.test_evidence_gate -v
- .\.venv\Scripts\python.exe -B scripts\check.py
- git diff --check

# Required evidence and handoff

- Publish `evidence/goal-awkp-bridge-report.md` describing the association
  model, how kernel evidence feeds the AWKP gate, and the preserved boundaries.
- Publish `evidence/verification-summary.json`.
- Publish `handoffs/HANDOFF-0001.md` with one exact next action for TASK-0061.
