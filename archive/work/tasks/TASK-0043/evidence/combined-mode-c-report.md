---
type: Evidence
id: EVD-TASK-0043-0001
schema_version: awkp/0.1
task_id: TASK-0043
title: TASK-0043 Combined Mode C Pilot Report
description: Producer report for the bounded combined Mode C real Planner plus real Executor pilot.
status: review
owner: agent:codex-dynamic-kernel-operator
created_at: 2026-06-28T07:16:25.537032Z
created_by: agent:codex-dynamic-kernel-operator
tags: [evidence, dynamic-kernel, mode-c, no-go]
---

# TASK-0043 Combined Mode C Pilot Report

Created at: 2026-06-28T07:16:25.537032Z
Created by: agent:codex-dynamic-kernel-operator
Experiment: TASK-0043-MODE-C
Code commit: `c5e5f1d4ad8a05700d3dae94d1a77a9521d2066d`

## Result

Mode C remains **no-go**.

The bounded combined real Planner plus real Executor pilot executed three isolated repetitions with explicit `--allow-combined`. The scorecard recorded `run_count=3`, `success_count=0`, and failure classes `runner_timeout=2` plus `budget_exceeded=1`.

This report does not approve model quality or runtime stability. It records that the combined pilot failed without observing false completion, unrun gate pass, stale fencing accept, duplicate resume effect, or unadmitted observed side effects.

## Per-run Findings

- `TASK-0043-MODE-C-R01`: wrapper reported `runner_timeout` after 360 seconds. Independent `goal inspect` found durable GoalExecution state with a failed PlanExecution classified as timeout while GoalExecution remained running. Planner/admission artifacts exist, so the wrapper's `planner=skipped` summary is incomplete for partial child-run recovery. Missing artifact count was zero.
- `TASK-0043-MODE-C-R02`: Planner output was accepted, Executor wrote `outputs/summary.txt` under admitted `filesystem.write`, deterministic bounded-task evidence was produced, and then PlanExecution failed because `modelCalls 2 > maxModelCalls 1`. Missing artifact count was zero.
- `TASK-0043-MODE-C-R03`: same class as run 01: isolated wrapper timeout with inner PlanExecution timeout and incomplete finalization. Missing artifact count was zero.

## Safety Interpretation

The no-go decision is caused by combined model/runtime instability and timeout/finalization behavior, not by permission broadening or by accepting a false completed goal. The following hard safety counters stayed at zero in the scorecard: false completion, unrun gate pass, stale fencing accept, and duplicate resume effect. Capability admission coverage was `1.0` for observed side effects.

The scorecard also records `gate_execution_integrity=0.0` and `current_claim_coverage=0.0` because no run completed the full goal. Those values are blockers for promotion and are why the decision remains no-go.

## Provider Usage

Provider token and cost usage was unavailable from the AgentDriver. The scorecard and verification summary record unavailable provider usage as `null`, not `0.0`. The budget failure in run 02 records scheduler usage counters; it is not treated as provider billing evidence.

## Recommendation

Do not promote Mode C to the default path. The next exact action is to open a follow-up fix for isolated child-run timeout recovery and final GoalExecution finalization after inner PlanExecution timeout, then rerun the combined pilot under a new task.
