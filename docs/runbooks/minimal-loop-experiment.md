---
type: Runbook
id: RUNBOOK-minimal-live-loop-experiment
schema_version: awkp/0.1
title: Minimal live dynamic loop experiment
description: Defines the repeatable local experiment sequence from deterministic verification to a small real-Agent pilot.
status: proposed
owner: team:platform
source_refs:
  - ../../AHRA_dynamic_kernel_m1_master_plan_2026-06-26.md
  - ../policies/minimal-loop-metrics.md
  - ../architecture/gate-execution-pipeline.md
  - ../architecture/goal-execution-lifecycle.md
evidence_refs: []
confidence: draft
last_verified_at: 2026-06-26T00:00:00Z
review_after: 2026-09-26T00:00:00Z
tags: [runbook, experiment, m1]
---

# Preconditions

- Repository baseline checks pass or failures are explicitly recorded.
- The experiment target is an isolated fixture project, not the AHRA repository.
- No production credentials or irreversible external effects are available.
- Goal, Policy, Runtime and adapter releases are immutable by digest.
- SQLite and Artifact directories are new or explicitly resumed.
- The operator knows the expected crash point and repair boundary.

# Recommended fixture

```text
tests/fixtures/m1-minimal-project/
├── goal-contract.yaml
├── project-profile.yaml
├── src/
│   └── doc_health.py
├── docs/
│   └── example.md
└── tests/
    ├── test_doc_health.py
    └── test_security_boundary.py
```

Example Goal:

> Implement document-expiry detection. Expired documents must be reported,
> current documents must not be reported, and execution must not modify
> `tests/**`, `docs/**`, or any path outside the isolated workspace.

# Experiment profiles

## Profile P0: happy path

- deterministic acceptance adapter;
- deterministic execution planner;
- deterministic executor;
- actual deterministic GateRunner;
- no injected defect;
- generic Goal CLI.

## Profile P1: defect and selective repair

- inject one deterministic functional failure;
- produce a real failed GateRun;
- create a Defect;
- compile PlanIR v2;
- execute repair and selected Gates through Scheduler;
- measure full versus selected Gate cost.

## Profile P2: security denial

- propose or attempt one unauthorized write;
- ensure Capability Admission or RuntimeGateway denies it before effect;
- verify audit lineage;
- continue only if policy allows the run to recover.

## Profile P3: process restart

- stop the process after one admitted Node commits an idempotent effect;
- start a new process;
- resume from SQLite;
- verify no duplicate effect and stale fencing rejection.

## Profile P4: real Planner

- real Planner;
- deterministic Executor and GateRunner;
- five bounded runs;
- invalid outputs are rejected, not repaired by hidden host logic.

## Profile P5: real Executor

- deterministic Planner;
- real bounded Executor;
- deterministic GateRunner;
- five bounded runs;
- direct file access limitations must be reported.

## Profile P6: combined pilot

Run only if P4 and P5 have zero hard-metric violations.

# Generic command shape

The implementation Task may refine exact flags, but the stable command family
should resemble:

```bash
python -m ahra.cli goal validate examples/m1/goal-run-request.yaml
python -m ahra.cli goal plan examples/m1/goal-run-request.yaml
python -m ahra.cli goal start examples/m1/goal-run-request.yaml
python -m ahra.cli goal inspect GEXEC-...
python -m ahra.cli goal resume GEXEC-...
python -m ahra.cli goal cancel GEXEC-... --reason "operator test"
```

# Deterministic M1 procedure

1. Create a clean Artifact directory and SQLite database.
2. Run `goal validate`.
3. Run `goal plan`; save PlanDraft, validation report and PlanIR.
4. Run `goal start`.
5. Confirm all runtime grants refer to AdmissionDecision records.
6. Confirm selected Gates create terminal GateRuns.
7. For P1, observe the failed GateRun and Defect.
8. Confirm PlanIR v2 and PlanExecution v2 exist.
9. Confirm repair and reverify Nodes were Scheduler-dispatched.
10. Confirm L2 Completion rejects stale/open-defect states.
11. Confirm final completion uses the current Evidence set.
12. Run AWKP EvidenceGate with an independent verifier.
13. Normalize the report and record its semantic digest.
14. Repeat twenty times.
15. Publish the scorecard and one exact next action.

# Process restart procedure

The crash probe must be a real process boundary.

1. Start the Goal process with a configured stop-after checkpoint.
2. Wait until the chosen Node has committed and its idempotency record is
   persisted.
3. Terminate the process without graceful in-memory continuation.
4. Start a new CLI process with the same SQLite and Artifact locations.
5. Resume the GoalExecution.
6. Confirm:
   - prior Node remains succeeded;
   - prior effect is not repeated;
   - expired lease is reconciled;
   - new fencing token is used;
   - next eligible Node runs;
   - final Evidence lineage remains complete.

# Failure handling

A failed experiment must publish:

- failed hard metric or criterion;
- exact profile and command;
- code commit and configuration digests;
- GoalExecution/PlanExecution/NodeRun/GateRun refs;
- relevant Artifact and Evidence;
- affected Evidence invalidation;
- reproduction;
- one exact next action.

Do not change the Goal or Claim to hide a failure.

# Result interpretation

- P0–P3 passing means deterministic M1 is operational.
- P4 or P5 failing on quality does not invalidate M1 if all safety boundaries
  remain intact; it identifies model/adapter work.
- Any hard safety metric failure invalidates the relevant experiment and blocks
  combined mode.
