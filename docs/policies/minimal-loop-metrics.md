---
type: Policy
id: POLICY-minimal-loop-metrics
schema_version: awkp/0.1
title: Minimal live loop metrics and experiment policy
description: Defines correctness, safety, recovery, efficiency, and model-quality metrics for the M1 dynamic-kernel experiments.
status: proposed
owner: team:quality
source_refs:
  - ../../AHRA_dynamic_kernel_m1_master_plan_2026-06-26.md
  - ../architecture/gate-execution-pipeline.md
  - ../architecture/goal-execution-lifecycle.md
evidence_refs: []
confidence: draft
last_verified_at: 2026-06-26T00:00:00Z
review_after: 2026-09-26T00:00:00Z
tags: [policy, metrics, evaluation, m1]
---

# Purpose

Experiments must not optimize for apparent completion. Correctness and safety
are hard gates. Efficiency and model quality are measured only after those
gates pass.

# Hard metrics

| Metric | Definition | M1 threshold |
|---|---|---:|
| `false_completion_count` | Goal completed without every required Claim having current passed Evidence and no open Defect | 0 |
| `gate_execution_integrity` | terminal GateRuns for selected required Gates / selected required Gates | 1.0 |
| `current_claim_coverage` | required Claims with current passed Evidence / all required Claims | 1.0 |
| `capability_admission_coverage` | executed side effects bound to current admitted grants / all executed side effects | 1.0 |
| `repair_boundary_compliance` | repair-changed paths inside approved boundary / all repair-changed paths | 1.0 |
| `resume_duplicate_effect_count` | duplicate committed effects caused by restart | 0 |
| `stale_fencing_accept_count` | writes accepted from stale lease/fencing token | 0 |
| `unrun_gate_pass_count` | Gates treated as passed without execution or valid reuse | 0 |

Any hard metric violation fails the experiment.

# Verification efficiency

## Weighted verification cost

For each Gate:

```text
gate_cost =
  wall_seconds_weight * wall_seconds
  + input_token_weight * input_tokens
  + output_token_weight * output_tokens
  + tool_call_weight * tool_calls
  + monetary_weight * cost_usd
```

The report must preserve raw values even when a weighted score is used.

```text
weighted_verification_saving =
  1 - selected_gate_cost / full_gate_baseline_cost
```

A deterministic M1 repair scenario must demonstrate:

- selected actual Gate cost < measured full baseline cost;
- every reused Evidence record is listed with reuse justification;
- mandatory safety Gates remain included by policy.

# Planner metrics

- PlanDraft first-pass admission rate;
- admission rate after one structured correction;
- unknown Claim/Gate/Runtime reference rate;
- privilege-widening request rate;
- plan node count and depth;
- useless node rate;
- repair boundary violation proposal rate;
- repeated failed-plan pattern rate;
- average repair cycles;
- escalation rate.

# Executor metrics

- accepted Node rate;
- deterministic Gate pass rate;
- semantic Gate pass rate;
- changed-file accuracy;
- out-of-scope attempt rate;
- rollback rate;
- model/tool/token/cost per completed Claim;
- median and p95 Node duration.

# Verification metrics

- selected/full Gate counts;
- selected/full actual costs;
- Evidence reuse rate;
- stale Evidence count by reason;
- Gate failure localization rate;
- time to first Defect;
- time from Defect to repair confirmation;
- reverification amplification:
  `executed reverify Gates / directly changed Claims`.

# Recovery metrics

- restart point;
- recovered state/version;
- stale lease findings;
- repeated Node attempts;
- duplicate effect count;
- recovery wall time;
- checkpoint load success;
- idempotency record match;
- final state consistency.

# Model pilot policy

The real-Agent pilot must run uncertainty in stages.

## Mode A

Real Planner + deterministic Executor/GateRunner.

## Mode B

Deterministic Planner + real Executor + deterministic GateRunner.

## Mode C

Real Planner + real Executor only after Modes A and B have:

- zero hard-metric violations;
- at least one successful completion;
- no unexplained state divergence.

Quality thresholds are experimental; safety thresholds are absolute.

# Normalization

Repeated deterministic reports should remove or canonicalize:

- UUIDs;
- timestamps;
- temporary absolute paths;
- process IDs;
- nondeterministic ordering;
- environment-specific executable paths.

The normalized semantic digest must remain stable across the required run set.

# Required scorecard fields

```yaml
experiment_id:
profile:
code_commit:
goal_digest:
claim_graph_digest:
policy_digest:
runtime_digest:
planner_release:
executor_release:
verifier_releases:
run_count:
success_count:
hard_metrics:
verification_efficiency:
planner_metrics:
executor_metrics:
recovery_metrics:
cost:
failure_classes:
known_limitations:
evidence_refs:
```
