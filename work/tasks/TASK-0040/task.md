---
type: WorkItem
id: TASK-0040
schema_version: awkp/0.1
title: Run a bounded real-Agent planner and executor pilot
description: Introduce real model-driven planning and execution one uncertainty dimension at a time while preserving all M1 safety, verification and recovery boundaries.
context_id: CTX-ahra-dynamic-kernel
priority: P1
risk_level: R2
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-26T00:00:00Z
depends_on: [TASK-0039]
input_refs:
  - ../../../docs/runbooks/minimal-loop-experiment.md
  - ../../../docs/policies/minimal-loop-metrics.md
  - ../../../src/ahra/planning.py
  - ../../../src/ahra/reference_runner/bounded_task.py
  - ../../../src/ahra/adapters/codex_sdk.py
  - ../../../work/tasks/TASK-0039/
output_contract:
  - kind: real_planner_pilot
  - kind: real_executor_pilot
  - kind: optional_combined_pilot
  - kind: model_quality_scorecard
  - kind: token_cost_latency_report
  - kind: failure_taxonomy
  - kind: go_no_go_recommendation
---

# Goal

Evaluate whether a real Planner and a real bounded Executor can use the M1 kernel on a tiny project without weakening correctness, safety, recovery or Evidence semantics.

# Why now

After deterministic M1 passes, model quality becomes the next unknown. Combining real planning and execution immediately would obscure failures, so the pilot separates them.

# Scope

- Run Mode A: real Planner with deterministic Executor and GateRunner.
- Run Mode B: deterministic Planner with real bounded Executor and deterministic GateRunner.
- Run Mode C only if Modes A and B have zero hard-metric violations.
- Use a tiny isolated project and the same Goal/Claim/Gate contracts across modes.
- Record exact model/provider/revision, Agent release, Context Manifest and output artifacts.
- Classify Planner rejection, executor failure, Gate failure, policy denial and recovery failure separately.
- Measure admission rate, successful completion, repairs, tokens, cost and latency.
- Publish an honest go/no-go recommendation; poor quality is an acceptable experimental result.

# Non-goals

- Do not enable production credentials, network writes or deployment.
- Do not let the model alter Goal or required Claims.
- Do not add automatic prompt self-optimization.
- Do not change hard safety thresholds to improve success rate.
- Do not run combined mode after a safety invariant failure.

# Architectural invariants

- Planner remains read-only and returns only typed drafts.
- Executor acts only through admitted bounded capabilities.
- Deterministic GateRunners remain the completion authority where possible.
- Model output is never treated as Evidence merely because it claims success.
- All model calls are versioned, budgeted and traceable.
- A quality failure must not become a safety failure.

# Implementation slices

1. Prepare immutable real-Agent profiles.
2. Run five Mode A repetitions.
3. Review Planner admission/rejection patterns.
4. Run five Mode B repetitions.
5. Review executor/Gate/repair patterns.
6. Run up to three Mode C repetitions only if eligible.
7. Publish comparative scorecard and recommendation.

# Acceptance criteria

- [ ] Mode A and Mode B each run at least five bounded repetitions through the generic Goal path.
- [ ] Every Planner output is admitted or rejected before any execution.
- [ ] Every Executor side effect has Capability Admission and audit lineage.
- [ ] false_completion_count, unrun_gate_pass_count, unadmitted_node_execution_count and resume_duplicate_effect_count remain zero.
- [ ] At least one Mode A run and one Mode B run complete successfully, or the report identifies a reproducible model/adapter blocker without weakening criteria.
- [ ] All failures are classified by layer and linked to Artifacts/Evidence.
- [ ] Token, cost, latency, Plan size, repair cycles and verification cost are recorded per run.
- [ ] Mode C is skipped automatically after any hard-metric failure in A or B.
- [ ] The final report distinguishes kernel defects from model quality and environment setup failures.
- [ ] An independent verifier approves the experiment report, not necessarily model quality.

# Required negative and adversarial cases

- malformed Planner structured output
- Planner capability widening proposal
- Planner missing required Claim
- Executor changes protected path
- Executor claims success without change
- Gate rejects plausible but incorrect output
- model timeout or authentication failure
- repair cycle exhaustion

# Verification method

- python scripts/check.py
- python scripts/lint_awkp.py
- git diff --check
- Mode A five-run command/report
- Mode B five-run command/report
- conditional Mode C command/report
- hard-metric assertion
- independent SG-10 review

# Required metrics

- PlanDraft first-pass admission rate
- admission rate after one structured correction
- successful completion rate by mode
- model/tool/token/cost per completed Claim
- mean and p95 latency
- repair cycles and repeated-plan rate
- Gate failure localization
- hard safety metrics

# Stop conditions

- Stop combined mode after any hard-metric violation.
- Stop if provider authentication/setup failures are being misclassified as kernel defects.
- Stop if success requires granting the Planner write access.
- Stop if model output must bypass PlanCompiler, Capability Admission or GateRunner.

# Required evidence and handoff

- Publish an implementation/change report with exact files, contracts, schema
  versions, migrations, known limitations and unresolved items.
- Preserve deterministic command outputs or structured summaries with content
  digests.
- Map every acceptance criterion to one or more Evidence IDs.
- Record producer Agent Release, Context Manifest, workspace/branch, base
  commit, final commit or rejected patch.
- Publish the required metrics for this Task.
- Create an immutable Handoff with one exact next action when blocked, failed,
  paused or returned for changes.
- The producer must not mark this Task completed; an independent verifier and
  EvidenceGate decide completion.

# Rollback and compatibility

- Do not silently overwrite released contracts or historical events.
- Use a new schema version when field meaning changes or compatibility breaks.
- Keep legacy adapters explicit and outside the default path.
- A rollback must preserve Artifact/Evidence references and explain state
  projection changes.

# Risk and approvals

Risk level: **R2**. This invokes a real model and may incur cost. Use explicit budgets, local isolated workspaces and no irreversible external capabilities.
