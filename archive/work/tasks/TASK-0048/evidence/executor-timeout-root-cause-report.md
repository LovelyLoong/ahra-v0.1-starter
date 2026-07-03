---
type: EvidenceReport
id: ART-TASK-0048-0001
schema_version: awkp/0.1
title: TASK-0048 Executor timeout root-cause report
description: Classifies the live Mode C bounded-write Executor timeout, records the minimal bounded-write repair, and preserves the Mode C non-default boundary.
status: review
owner: agent:codex-dynamic-kernel-operator
task_id: TASK-0048
created_at: 2026-06-28T13:34:57.686892Z
created_by: agent:codex-dynamic-kernel-operator
updated_at: 2026-06-28T13:51:02.6503656Z
updated_by: agent:codex-independent-verifier
update_reason: Added required AWKP Markdown frontmatter during independent review; technical body unchanged.
---

# TASK-0048 Executor Timeout Root Cause

## Scope

This report covers only the live Mode C bounded-write Executor completion
timeout that remained after TASK-0047. It does not authorize Mode C default-path
promotion.

## Evidence Chain

- TASK-0047 post-fix Mode C run exited before the isolated watchdog, but the
  bounded Executor node still failed with `timeout: 1`; no `work-report.json`,
  deterministic evidence, or `outputs/summary.txt` was produced.
- TASK-0048 initial live rerun
  `evidence/real-agent-pilot/mode-c-bounded-write` failed with
  `TimeoutError('executor exceeded idle timeout (45s)')`. Heartbeats showed no
  changed files before the idle timeout.
- Direct Codex SDK Executor probe
  `evidence/direct-codex-executor-probe/probe-result.json` proved the SDK could
  write the target artifact, but took 67.406989s and attempted shell
  verification before returning.
- After adding explicit artifact-only instructions, direct probe
  `evidence/direct-codex-executor-probe-2/probe-result.json` completed in
  35.293269s, wrote `outputs/summary.txt`, and returned a valid `WorkReport`
  without shell verification.
- Live rerun
  `evidence/real-agent-pilot/mode-c-bounded-write-2` reached Executor
  acceptance, but failed plan budget reconciliation because skipped semantic
  review was counted as a model call.
- Live rerun
  `evidence/real-agent-pilot/mode-c-bounded-write-3` failed because the real
  Planner emitted a 30s bounded node timeout. That was below the observed
  direct Executor completion time.
- Final live rerun
  `evidence/real-agent-pilot/mode-c-bounded-write-4` succeeded with
  `success_count=1`, both nodes succeeded, `outputs/summary.txt` was written,
  and hard metrics passed.

## Root Cause Classification

The remaining failure was not a single runtime crash. It was a three-part live
contract problem:

1. The generated Executor task did not preserve exact bounded-write output
   obligations from PlanIR into `TaskSpec`.
2. The Codex Executor prompt allowed artifact-only tasks to spend time on shell
   verification before returning, pushing first completion beyond the 45s idle
   window.
3. Real Planner output could reintroduce too-small Executor node budgets after
   the request template had already been expanded for real Executor execution.

Two accounting issues were also found during reruns:

- Internal artifact checks must not consume external `process.exec` capability.
- A skipped semantic review must not count as a model call.

## Minimal Repair

- `src/ahra/reference_runner/bounded_task.py`
  - Preserves PlanIR `filesystem.write` resources and `expectedOutputs` in the
    generated `TaskSpec`.
  - Adds an internal required-artifact check for literal write resources.
  - Excludes AHRA internal checks from external tool-call accounting.
  - Counts semantic review model calls only when semantic review actually ran.
- `src/ahra/reference_runner/checks.py`
  - Adds `ahra.internal.artifact_exists.v1`, a harness-internal read-only
    artifact check that does not invoke `process.exec`.
- `src/ahra/adapters/codex_sdk.py`
  - Instructs Executor agents to create required files before final JSON and
    skip shell/process verification for artifact-only/internal-check tasks.
- `src/ahra/real_agent_pilot.py`
  - Normalizes real Planner bounded-task budgets for real Executor profiles
    after Planner output, before admission and request writeback.

## Decision

TASK-0048 repaired the bounded-write completion path for one bounded live Mode C
repetition. This is not sufficient evidence to defaultize Mode C. Mode C remains
non-default and should still require separate EvidenceGate review before any
broader pilot or default-path promotion.
