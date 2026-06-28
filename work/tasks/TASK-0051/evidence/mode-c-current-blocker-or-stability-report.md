---
type: Evidence
id: EVD-TASK-0051-0001
schema_version: awkp/0.1
title: TASK-0051 Mode C current stability report
description: Fresh post-TASK-0050 evidence for the real Planner plus real Executor Mode C path.
status: review
owner: agent:codex-dynamic-kernel-operator
created_at: 2026-06-28T15:21:57.720061Z
created_by: agent:codex-dynamic-kernel-operator
task_id: TASK-0051
kind: mode_c_current_blocker_or_stability_report
---

# Summary

TASK-0051 did not reproduce the previous Mode C failures. A fresh
post-TASK-0050 Mode C pilot ran three isolated repetitions with real Planner
and real bounded Executor enabled. All three repetitions succeeded.

This means the current M1 bounded Mode C path is no longer blocked by the
previous planner-output-invalid, executor timeout, process-boundary shutdown,
bounded-write contract, or pilot-invariant issues.

This does not promote Mode C to the default route and does not prove production
or arbitrary-project stability.

# Fresh Mode C Pilot

Command:

```powershell
.\.venv\Scripts\python.exe -B scripts\run_real_agent_pilot.py --mode mode_c_combined --output-dir work\tasks\TASK-0051\evidence\real-agent-pilot\mode-c-fresh --experiment-id TASK-0051-MODE-C --repetitions 3 --allow-model-cost --allow-combined --isolated-repetitions --repetition-timeout-seconds 180 --executor-idle-timeout-seconds 45 --executor-heartbeat-interval-seconds 10 --executor-attempt-wall-timeout-seconds 60 --executor-run-deadline-seconds 90
```

Scorecard:

- Path: `work/tasks/TASK-0051/evidence/real-agent-pilot/mode-c-fresh/scorecard.json`
- `run_count`: 3
- `success_count`: 3
- `failure_classes`: `{}`
- `workflow_failure_dimensions.counts.none`: 3
- Planner first-pass admission rate: 1.0
- Executor accepted node rate: 1.0
- Capability admission coverage: 1.0
- Current claim coverage: 1.0
- Gate execution integrity: 1.0
- False completion count: 0
- Unrun gate pass count: 0
- Stale fencing accept count: 0
- Resume duplicate effect count: 0

Run refs:

- run-01: `GEXEC-458409999dbc6a3c`, `PEXEC-2af42000f57102c6`
- run-02: `GEXEC-ea42583341bc04a6`, `PEXEC-9ff2adfc758276a5`
- run-03: `GEXEC-98e18eebee0bdad8`, `PEXEC-cf9eacdc2ca36337`

# Independent Inspect

Each GoalExecution was inspected independently with its run-local SQLite store
and artifact directory:

- run-01: goal `succeeded`, plan `succeeded`, two node runs `succeeded`,
  `missingArtifactCount=0`, `artifactFindings=[]`.
- run-02: goal `succeeded`, plan `succeeded`, two node runs `succeeded`,
  `missingArtifactCount=0`, `artifactFindings=[]`.
- run-03: goal `succeeded`, plan `succeeded`, two node runs `succeeded`,
  `missingArtifactCount=0`, `artifactFindings=[]`.

# Current Blocker Assessment

No current blocker was found in the fresh three-repetition Mode C evidence.

Prior failures are now covered as follows:

- TASK-0040 planner-output-invalid: not reproduced; all three real Planner
  outputs were admitted.
- TASK-0045 executor/runtime timeout: not reproduced; all three bounded
  Executor runs completed.
- TASK-0047 process-boundary hang: not reproduced; isolated repetitions exited
  normally.
- TASK-0048 bounded-write contract failure: not reproduced; all three runs
  produced required artifacts and evidence.
- TASK-0050 pilot-invariant gaps: scorecard now records failure dimensions and
  real Executor budget invariant evidence.

# Boundary

This report supports the claim that the current local M1 bounded Mode C pilot
path is passing under the tested settings.

It does not support these claims:

- Mode C is the default path.
- Mode C is production-grade.
- Mode C is stable for arbitrary projects or arbitrary goals.
- Provider token or cost usage is known; the driver did not report usage.

The next decision is an independent EvidenceGate review of TASK-0051.
