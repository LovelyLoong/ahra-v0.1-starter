---
type: Evidence
id: EVD-TASK-0041-0001
schema_version: awkp/0.1
title: TASK-0041 Planner contract hardening implementation report
description: Producer report for real Planner PlanDraft contract adherence hardening and post-change Mode A evidence.
status: review
owner: agent:codex-dynamic-kernel-operator
source_refs:
  - ../task.md
  - real-agent-pilot/mode-a/scorecard.json
  - goal-inspect-summary.json
  - invalid-output-artifact-index.json
  - mode-c-decision.json
evidence_refs:
  - EVD-TASK-0041-0002
  - EVD-TASK-0041-0003
  - EVD-TASK-0041-0004
  - EVD-TASK-0041-0005
  - EVD-TASK-0041-0006
  - EVD-TASK-0041-0007
confidence: producer-reviewed
last_verified_at: 2026-06-28T05:33:17.055491Z
review_after: 2026-09-28T00:00:00Z
tags: [task-0041, real-planner, plan-draft, evidence]
---

# TASK-0041 Implementation Report

Created at: 2026-06-28T05:30:14Z

Producer: agent:codex-dynamic-kernel-operator

Status: review requested; not completed by producer.

## Summary

TASK-0041 isolated the real Planner Mode A contract-adherence issue from TASK-0040 without changing PlanIR, Capability Admission, GateRunner, Evidence, Completion, or Mode B behavior.

Two implementation commits are in scope:

- `0cae25794e7f4b1378dae9e5379fe58d6ac3f31e`: tightened the PlanDraft output contract, rejected TASK-0040 alias shapes such as `goalRef`, `type`, `claims`, `gates`, and preserved invalid raw/driver output artifacts on adapter failures.
- `cbd738c1e65cff181a1e6c3a702d84d7dc53ddbc`: exposed `allowedCapabilities` to the Planner input artifact and clarified that PlanDraft `capabilityRequests` are downstream Executor intent, not Planner runtime grants.

## Evidence

The intermediate run at `evidence/real-agent-pilot/mode-a-before-capability-context-20260628T132437/scorecard.json` is preserved as a narrowing step. It had 5/5 first-pass Planner admission and 0/5 success, with `missing_capability_intent: 5`. That showed the alias/shape blocker was fixed and the remaining failure was capability intent.

The post-change run at `evidence/real-agent-pilot/mode-a/scorecard.json` ran 5 isolated Mode A repetitions on commit `cbd738c1e65cff181a1e6c3a702d84d7dc53ddbc`:

- `run_count=5`, `success_count=5`, `failure_classes={}`.
- Planner metrics: `first_pass_admission_rate=1.0`, `rejected_count=0`, `blocked_count=0`.
- Executor metrics: `accepted_node_rate=1.0`, `failed_count=0`.
- Hard metrics: false completion, unrun gate pass, stale fencing accept and duplicate resume effect all remained zero.
- Each run had `capabilityGrantRefCount=1`, `evidenceRefCount=2`, `missingArtifactCount=0`.

Independent `goal inspect` was run for all five post-change GEXECs and recorded in `evidence/goal-inspect-summary.json`. It confirms all goal statuses succeeded, all artifact findings are empty, and all missing artifact counts are zero.

No post-change invalid Planner outputs were produced. `evidence/invalid-output-artifact-index.json` records that the preservation path remains covered by tests and points to the TASK-0040 invalid-output artifacts used as the regression input.

## Acceptance Mapping

| Acceptance criterion | Evidence |
|---|---|
| Required PlanDraft fields explicitly named | Commits `0cae2579` and `cbd738c1`; tests in `tests/test_planning.py` and `tests/test_codex_driver.py`. |
| Planner output admitted or rejected before execution | `planner-admission-report.json` exists for every post-change run; scorecard planner status is `accepted` before execution. |
| Normalization deterministic/minimal and boundaries not weakened | No semantic coercion was added; strict output contract rejects alias shape; allowed capabilities are only exposed as input context. |
| Invalid raw and parsed driver output remain preserved | Adapter failure path writes `planner-invalid-output-artifact.json` and `planner-invalid-output.json`; covered by tests and indexed in `invalid-output-artifact-index.json`. |
| At least five post-change Mode A repetitions | `evidence/real-agent-pilot/mode-a/scorecard.json`, 5 runs. |
| At least one admitted PlanDraft or narrower blocker | 5 admitted PlanDrafts and 5 successful executions. |
| Hard safety metrics remain safe | Scorecard hard metrics and inspect summary. |
| Token, cost, latency, plan size and admission metrics recorded when available | Scorecard records elapsed seconds, admission metrics, model provider/revision, and cost limitation as unavailable rather than fabricated. |
| Final report distinguishes model contract adherence from kernel defects | This report records Planner contract/context fixes and does not claim Mode B or Mode C readiness. |
| Independent verifier approves before completion | Pending; state is review, not completed. |

## Recommendation

Move TASK-0041 to independent EvidenceGate review. Keep Mode C no-go from this task because TASK-0042 still owns the separate Mode B real Executor timeout stability issue.
