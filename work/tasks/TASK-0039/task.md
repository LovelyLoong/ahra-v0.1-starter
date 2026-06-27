---
type: WorkItem
id: TASK-0039
schema_version: awkp/0.1
title: Run and baseline the deterministic M1 minimal live loop
description: Demonstrate the generic durable loop twenty consecutive times with actual Gates, admitted capabilities, Scheduler-driven repair, selective reverification and process restart.
context_id: CTX-ahra-dynamic-kernel
priority: P0
risk_level: R2
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-26T00:00:00Z
depends_on: [TASK-0038]
input_refs:
  - ../../../docs/runbooks/minimal-loop-experiment.md
  - ../../../docs/policies/minimal-loop-metrics.md
  - ../../../docs/architecture/gate-execution-pipeline.md
  - ../../../docs/architecture/goal-execution-lifecycle.md
  - ../../../tests/fixtures/m1-minimal-project
output_contract:
  - kind: m1_fixture_project
  - kind: experiment_profiles
  - kind: twenty_run_scorecard
  - kind: full_vs_selective_verification_baseline
  - kind: crash_resume_report
  - kind: security_report
  - kind: release_baseline
  - kind: independent_verification_report
---

# Goal

Prove the minimal live dynamic workflow works through the generic Goal operation path with deterministic adapters and publish a reproducible M1 baseline before introducing model nondeterminism.

# Why now

Individual components and unit tests are not enough. The project needs one bounded, repeatable, externally inspectable experiment that exercises every runtime boundary and quantifies verification savings.

# Scope

- Create or finalize a minimal external fixture project and generic GoalExecutionRequest.
- Run happy-path, defect-repair, security-denial and process-restart profiles.
- Use actual GateRunner executions and current-set Evidence.
- Use Capability Admission for every side effect.
- Run repair PlanExecution v2 through Scheduler.
- Measure selected actual Gate cost against a measured full Gate baseline.
- Normalize nondeterministic report fields and compute semantic digests.
- Run twenty consecutive deterministic repetitions.
- Publish one M1 experiment scorecard and release baseline.

# Non-goals

- Do not use a real LLM.
- Do not target the AHRA repository for self-modification.
- Do not use production credentials or external irreversible effects.
- Do not weaken Claims between repetitions.
- Do not accept report-only recovery that does not cross a process boundary.

# Architectural invariants

- The experiment uses only the generic Goal CLI/service path.
- All selected required Gates actually execute or are justified current reuse.
- Every side effect has admitted capability lineage.
- Repair uses PlanExecution v2 and Scheduler.
- Completion uses resolved current Evidence and no open Defect.
- The test target remains isolated and AHRA does not modify itself.
- Hard metrics are absolute; efficiency cannot compensate for a safety failure.

# Implementation slices

1. Build the M1 project/profile.
2. Measure full verification baseline.
3. Run one happy-path and inspect lineage.
4. Run defect-repair and selective verification.
5. Run security denial.
6. Run process crash/resume.
7. Automate twenty repetitions and normalization.
8. Publish scorecard, baseline and handoff.

# Acceptance criteria

- [ ] Twenty consecutive runs complete with false_completion_count = 0.
- [ ] gate_execution_integrity = 1.0 in every run.
- [ ] current_claim_coverage = 1.0 at every accepted completion.
- [ ] capability_admission_coverage = 1.0 for every executed side effect.
- [ ] repair_boundary_compliance = 1.0.
- [ ] resume_duplicate_effect_count = 0 and stale_fencing_accept_count = 0.
- [ ] Selected actual verification cost is strictly lower than the measured full baseline in the defect-repair profile.
- [ ] Every reused Evidence record has a current-set inspection and explicit reuse rationale.
- [ ] Normalized semantic results are stable across all twenty deterministic runs.
- [ ] The source fixture and AHRA repository remain unmodified outside declared Artifact/runtime locations.
- [ ] An independent verifier reviews raw Artifacts, GateRuns and scorecard rather than only the producer summary.
- [ ] Passing EvidenceGate authorizes the project to claim M1 deterministic minimal live loop.

# Required negative and adversarial cases

- one GateRunner forced failure
- one widened capability request
- one path escape
- one stale Evidence trigger
- one open Defect completion attempt
- one crash after committed effect
- one stale fencing write
- one duplicate resume command

# Verification method

- python scripts/check.py
- python scripts/lint_awkp.py
- git diff --check
- generic Goal CLI profiles P0-P3
- twenty-run deterministic experiment command
- normalized digest comparison
- full-vs-selected actual Gate cost comparison
- independent SG-9 review

# Required metrics

- all hard metrics in POLICY-minimal-loop-metrics
- weighted verification saving
- Evidence reuse rate
- Gate wall time and cost
- repair cycles
- recovery wall time
- normalized semantic digest distribution

# Stop conditions

- Stop on the first hard-metric violation and create a Defect.
- Stop if any run completes from caller-curated Evidence rather than registry current set.
- Stop if selected verification is not actually cheaper than the measured baseline.
- Stop if normalized deterministic results diverge without a classified reason.

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

Risk level: **R2**. This is the M1 release gate. Passing requires independent review of twenty-run evidence, not a single successful demonstration.
