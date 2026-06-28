---
type: Evidence
id: EVD-TASK-0042-0001
schema_version: awkp/0.1
title: TASK-0042 real Executor runtime stability report
description: Producer report for Mode B real bounded Executor timeout stabilization.
status: review
owner: agent:codex-dynamic-kernel-operator
source_refs:
  - ../task.md
  - real-agent-pilot/mode-b/scorecard.json
  - goal-inspect-summary.json
  - timeout-taxonomy.json
  - mode-c-decision.json
evidence_refs:
  - EVD-TASK-0042-0002
  - EVD-TASK-0042-0003
  - EVD-TASK-0042-0004
  - EVD-TASK-0042-0005
confidence: producer-reviewed
last_verified_at: 2026-06-28T05:49:03Z
review_after: 2026-09-28T00:00:00Z
tags: [task-0042, real-executor, timeout, evidence]
---

# TASK-0042 Executor Runtime Stability Report

Producer: agent:codex-dynamic-kernel-operator

Status: review requested; not completed by producer.

## Summary

TASK-0042 isolated the TASK-0040 Mode B timeout issue to the isolated pilot subprocess watchdog. The previous runner used `--repetition-timeout-seconds 120` as an outer process timeout while the inner real Executor policy allowed `run_deadline_seconds=240`. Four TASK-0040 partial runs were killed at 120 seconds after `executor_started`, before the inner policy could produce structured terminal timeout evidence.

The implementation commit `355e0e0f9ecccda8dbf520837ad7b8fe768bcae4` changes only the isolated pilot watchdog for real Executor modes:

- Mode B and Mode C effective subprocess timeout is `max(requested_timeout, executor_run_deadline_seconds + 15)`.
- Mode A Planner-only timeout behavior is unchanged.
- If the outer watchdog still fires, timeout evidence records requested timeout, effective timeout and executor run deadline.
- No capability, filesystem, GateRunner, PlanIR, Evidence or Completion criteria were widened.

## Results

The post-change Mode B run used the task-specified command with `--repetition-timeout-seconds 120`. Because the mode uses the real bounded Executor, the effective outer watchdog was 255 seconds.

Scorecard: `evidence/real-agent-pilot/mode-b/scorecard.json`

- `run_count=5`, `success_count=5`, `failure_classes={}`.
- Executor metrics: `run_count=5`, `accepted_node_rate=1.0`, `failed_count=0`.
- Hard metrics: false completion, unrun gate pass, stale fencing accept and duplicate resume effect all remained zero.
- Every run had `capabilityGrantRefCount=1`, `evidenceRefCount=2`, `missingArtifactCount=0`.
- Run 01 elapsed 130.756317 seconds, which is greater than the requested 120 second outer timeout and demonstrates that the previous watchdog would have preempted this successful execution.

Independent `goal inspect` was run for all five GEXECs and recorded in `evidence/goal-inspect-summary.json`. It confirms all goal statuses succeeded, artifact findings are empty, and missing artifact counts are zero.

## Acceptance Mapping

| Acceptance criterion | Evidence |
|---|---|
| Timeout root causes classified | `evidence/timeout-taxonomy.json` classifies TASK-0040 failures as adapter process control / outer watchdog preemption. |
| Every side effect remains capability-admitted | Scorecard and inspect summary show `capabilityGrantRefCount=1` for every successful run. |
| At least five post-change Mode B repetitions | `evidence/real-agent-pilot/mode-b/scorecard.json`, 5 runs. |
| At least one Mode B run completes successfully | 5 successful runs. |
| Hard safety metrics remain safe | Scorecard hard metrics and inspect summary. |
| Token, cost, latency, duration and verification cost recorded when available | Scorecard records elapsed seconds and provider usage limitation; verification weighted cost remains a known pilot limitation. |
| Runtime/model reliability distinguished from kernel defects | This report and timeout taxonomy identify watchdog layering, not a Capability/Gate/Evidence kernel defect. |
| Independent verifier approves before completion | Pending; state is review, not completed. |

## Recommendation

Move TASK-0042 to independent EvidenceGate review. Keep combined Mode C no-go until both TASK-0041 and TASK-0042 are independently approved and a separate Mode C run is explicitly opened or authorized.
