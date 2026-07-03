---
type: Handoff
id: HANDOFF-TASK-0034-0001
schema_version: awkp/0.1
title: TASK-0034 capability admission handoff
description: Producer handoff for independent EvidenceGate review of TASK-0034 mandatory Capability Admission.
status: review
owner: agent:codex-dynamic-kernel-operator
task_id: TASK-0034
created_by: agent:codex-dynamic-kernel-operator
created_at: 2026-06-26T04:16:03.320534Z
---

# TASK-0034 Handoff

Producer: `agent:codex-dynamic-kernel-operator`

State requested: `review`

## Summary

TASK-0034 makes Capability Admission mandatory before executable NodeRuns enter
`running`. Default Scheduler execution now uses real AdmissionDecision and
CapabilityGrant records from `CapabilityAdmissionService`; denied or missing
admission fails before executor invocation.

## Evidence

- `work/tasks/TASK-0034/evidence/implementation-report.json`
- `work/tasks/TASK-0034/evidence/verification-report.json`
- `work/tasks/TASK-0034/evidence/dynamic-fixture-report.json`

## Verification

- `uv run python -B scripts\check.py`
- `uv run python -B scripts\lint_awkp.py`
- `git diff --check`
- `uv run python -B -m ahra.cli fixture dynamic-repair --fixture tests\fixtures\dynamic-goal-project --report work\tasks\TASK-0034\evidence\dynamic-fixture-report.json`

## Reviewer Notes

- The producer has not marked the task completed. Completion requires
  independent EvidenceGate review.
- `reference_runner/bounded_task.py` still contains a synthetic runtime grant
  helper, explicitly documented as standard-harness compatibility only.
- PlanIR still serializes the historical `capabilityGrants` field name for
  compatibility, but the default Scheduler treats it as capability intent, not
  runtime authorization.
- Repair execution remains direct in the fixture after repair planning; TASK-0036
  owns Scheduler-driven repair lifecycle.

## Exact Next Action

Run independent EvidenceGate review for `TASK-0034` mandatory Capability
Admission criteria.
