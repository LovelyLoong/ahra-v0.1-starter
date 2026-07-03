---
type: Handoff
id: HANDOFF-TASK-0031-0001
schema_version: awkp/0.1
title: TASK-0031 dynamic repair fixture ready for review
description: Producer handoff after implementing the isolated dynamic GoalContract to Defect to bounded repair and selective reverification fixture.
status: active
owner: agent:codex-dynamic-kernel-operator
source_refs: [../task.md, ../state.json, ../artifact-manifest.json, ../evidence-manifest.json, ../evidence/dynamic-fixture-command-report.json]
evidence_refs: [EVD-TASK-0031-0001, EVD-TASK-0031-0002, EVD-TASK-0031-0003]
confidence: reviewed
last_verified_at: 2026-06-25T15:40:45Z
review_after: 2026-09-25T00:00:00Z
tags: [handoff, task-0031, dynamic-kernel, repair, evidence-gate]
---

# TASK-0031 Handoff

Producer-side implementation and verification are complete. The task is being returned to review, not completed by the producer.

Evidence to inspect:

- `work/tasks/TASK-0031/evidence/dynamic-fixture-command-report.json`
- `work/tasks/TASK-0031/evidence/verification-report.json`
- `work/tasks/TASK-0031/evidence/implementation-report.json`

Verification already run:

- `.venv\Scripts\python.exe -B -m unittest tests.test_dynamic_fixture -v`
- `.venv\Scripts\python.exe -B -m unittest tests.test_dynamic_fixture tests.test_planning tests.test_plan_execution tests.test_verification -v`
- `.venv\Scripts\python.exe -B -m ahra.cli fixture dynamic-repair --fixture tests\fixtures\dynamic-goal-project --report work\tasks\TASK-0031\evidence\dynamic-fixture-command-report.json`
- `.venv\Scripts\python.exe -B scripts\check.py`
- `.venv\Scripts\python.exe -B scripts\check.py --lint`
- `git diff --check`

Exact next action: independent verifier should evaluate TASK-0031 evidence and run EvidenceGate with expected state_version 5.
