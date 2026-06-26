---
type: Handoff
id: HANDOFF-TASK-0035-0001
schema_version: awkp/0.1
title: TASK-0035 evidence current-set handoff
description: Producer handoff for independent EvidenceGate review of TASK-0035 Evidence current-set and multi-Claim Defect semantics.
status: review
owner: agent:codex-dynamic-kernel-operator
task_id: TASK-0035
created_by: agent:codex-dynamic-kernel-operator
created_at: 2026-06-26T06:36:54.539961Z
---

# TASK-0035 Handoff

Producer: `agent:codex-dynamic-kernel-operator`

State requested: `review`

## Summary

TASK-0035 makes Completion and selective verification consume the
EvidenceRegistry current set rather than caller-curated final records. Evidence
supersession is append-only and fails closed on unknown refs, cycles,
self-supersession, duplicate refs and competing current leaves. Defects now
record direct and affected Claims.

## Evidence

- `work/tasks/TASK-0035/evidence/implementation-report.json`
- `work/tasks/TASK-0035/evidence/verification-report.json`
- `work/tasks/TASK-0035/evidence/dynamic-fixture-report.json`

## Verification

- `uv run python -B scripts\check.py`
- `uv run python -B scripts\lint_awkp.py`
- `git diff --check`
- `uv run python -B -m ahra.cli fixture dynamic-repair --fixture tests\fixtures\dynamic-goal-project --report work\tasks\TASK-0035\evidence\dynamic-fixture-report.json`

## Reviewer Notes

- The producer has not marked the task completed. Completion requires
  independent EvidenceGate review.
- The dynamic fixture now passes full append-only Evidence history into
  Completion and relies on supersession to exclude historical failures.
- `claimRef` remains in DefectRecord output as compatibility metadata; the new
  default contract fields are `directClaimRefs` and `affectedClaimRefs`.
- SQLite persistence and unified Scheduler-driven repair remain out of scope
  for this task.

## Exact Next Action

Run independent EvidenceGate review for `TASK-0035` current Evidence and
multi-Claim Defect criteria.
