---
type: Handoff
id: HANDOFF-TASK-0039-0001
schema_version: awkp/0.1
task_id: TASK-0039
title: TASK-0039 review handoff
description: Producer handoff for independent SG-9 EvidenceGate review.
owner: agent:codex-dynamic-kernel-operator
from: agent:codex-dynamic-kernel-operator
to: agent:independent-verifier
created_at: 2026-06-26T11:03:00Z
status: review
---

# TASK-0039 Review Handoff

Producer implementation is ready for independent review.

## Exact Next Action

Run independent EvidenceGate review for TASK-0039 using:

- `work/tasks/TASK-0039/task.md`
- `work/tasks/TASK-0039/state.json`
- `work/tasks/TASK-0039/artifact-manifest.json`
- `work/tasks/TASK-0039/evidence-manifest.json`
- `work/tasks/TASK-0039/evidence/implementation-report.md`
- `work/tasks/TASK-0039/evidence/fixture-manifest.json`
- `work/tasks/TASK-0039/evidence/metrics.json`
- `work/tasks/TASK-0039/evidence/m1-experiment/m1-scorecard.json`
- `work/tasks/TASK-0039/evidence/m1-experiment/profiles/P1-defect-repair/p1-summary.json`
- `work/tasks/TASK-0039/evidence/m1-experiment/profiles/P1-defect-repair/p1-gate-runs.json`
- `work/tasks/TASK-0039/evidence/m1-experiment/profiles/P1-defect-repair/p1-evidence-records.json`
- `work/tasks/TASK-0039/evidence/m1-experiment/profiles/P2-security-denial/p2-summary.json`

## Producer Verification

- `uv run python -B scripts/lint_awkp.py`
- `uv run python -B -m unittest tests.test_m1_experiment -v`
- `uv run python -B scripts/run_m1_minimal_experiment.py --request tests\fixtures\m1-minimal-project\goal-run-request.yaml --output work\tasks\TASK-0039\evidence\m1-experiment --runs 20`
- `uv run python -B -m ahra.cli goal validate tests\fixtures\m1-minimal-project\goal-run-request.yaml`
- `git diff --check`

## Review Focus

- Confirm the twenty P0/P3 run summaries all used `ahra goal` validate/plan/start/resume/inspect.
- Confirm P1 contains a failed GateRun, a Defect, PlanIR v2, Scheduler-run repair, reused security Evidence, and selected cost lower than full baseline.
- Confirm P2 path escape and widened capability probes fail closed before unauthorized effects.
- Confirm normalized semantic digest is stable across all twenty deterministic runs.
- Confirm this producer did not mark TASK-0039 completed.
