---
type: WorkItem
id: TASK-0037
schema_version: awkp/0.1
title: Persist the local control plane in SQLite and prove process restart recovery
description: Replace in-memory dynamic execution authority with a transactional SQLite profile and demonstrate recovery across a real process exit without duplicate side effects.
context_id: CTX-ahra-dynamic-kernel
priority: P0
risk_level: R2
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-26T00:00:00Z
depends_on: [TASK-0036]
input_refs:
  - ../../../docs/architecture/goal-execution-lifecycle.md
  - ../../../src/ahra/plan_execution.py
  - ../../../src/ahra/evidence_v2.py
  - ../../../src/ahra/capabilities.py
  - ../../../src/ahra/ports.py
  - ../../../docs/architecture/observability-and-evaluation.md
output_contract:
  - kind: sqlite_control_store
  - kind: schema_migrations
  - kind: transactional_cas
  - kind: durable_checkpoints
  - kind: idempotency_records
  - kind: recovery_reconciler
  - kind: subprocess_crash_resume_test
  - kind: recovery_report
---

# Goal

Make the M1 local profile durable: terminate the process after a committed Node effect, restart with the same SQLite database, and finish the Goal without repeating completed work.

# Why now

Re-instantiating a Scheduler over an in-memory Store proves object separation but not crash recovery. A generic resume command must rely on durable state and idempotency.

# Scope

- Implement a SQLite-backed local store for GoalExecution, PlanExecution, NodeRun and Checkpoint.
- Persist GateRun/Evidence references, capability decisions/grants, events and idempotency records required for resume.
- Use transactions and expected-version CAS semantics.
- Add schema versioning and forward-only local migrations.
- Add recovery reconciliation for expired leases, interrupted Nodes and orphaned in-flight records.
- Add side-effect idempotency records for the deterministic experiment.
- Run a subprocess crash/restart test with a fresh Scheduler process.
- Keep large Artifact content in files; store refs/digests in SQLite.

# Non-goals

- Do not implement distributed consensus.
- Do not claim multi-host exactly-once semantics.
- Do not migrate production data.
- Do not persist raw private prompts or chain of thought.
- Do not add real model calls.

# Architectural invariants

- SQLite is the authority for local runtime state; report files are projections.
- Every state mutation is transactional and version-checked.
- A checkpoint references immutable plan and schema versions.
- Completed idempotent effects are not re-executed after restart.
- Stale leases/fencing tokens cannot write authoritative state.
- Recovery emits events and never silently edits history.

# Implementation slices

1. Define SQLite schema and migration command/API.
2. Implement stores and CAS transactions.
3. Persist idempotency and recovery-critical refs.
4. Implement reconciler/requeue rules.
5. Add subprocess stop-after-checkpoint hook.
6. Run a new process and assert exactly-once behavior.

# Acceptance criteria

- [ ] A fresh process can inspect and resume a non-terminal GoalExecution from SQLite.
- [ ] A Node completed before the crash is not executed again.
- [ ] A committed side effect is not duplicated.
- [ ] An expired lease is reconciled and a stale fencing token is rejected.
- [ ] An interrupted safe Node is retried only according to its declared retry/idempotency policy.
- [ ] GoalExecution, PlanExecution, NodeRun and Checkpoint versions remain consistent after recovery.
- [ ] GateRun/Evidence/capability lineage remains available after restart.
- [ ] Schema migration from an empty v0.1 database is deterministic and tested.
- [ ] The in-memory store remains test-only or explicit experimental, not default M1 authority.
- [ ] Full checks and subprocess recovery tests pass.

# Required negative and adversarial cases

- process killed after effect but before Node terminal update
- process killed after Node terminal update but before next dispatch
- expired Node lease
- stale fencing write
- duplicate resume command
- database schema version mismatch
- partial transaction rollback
- missing Artifact file referenced by database

# Verification method

- python scripts/check.py
- python scripts/lint_awkp.py
- git diff --check
- SQLite migration tests
- transaction/CAS conflict tests
- subprocess crash and resume integration test
- duplicate-effect assertion
- reconciler findings report

# Required metrics

- crash recovery success rate
- resume duplicate effect count
- stale fencing accept count
- recovery wall time
- reconciler finding count by code
- checkpoint load success

# Stop conditions

- Stop if exactly-once requires only in-memory flags.
- Stop if a crash can lose the AdmissionDecision or GateRun lineage needed for completion.
- Stop if recovery must rerun every Node from the beginning.

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

Risk level: **R2**. This introduces a persistent authority and migration semantics. Back up test databases and require independent review of transactions, CAS and recovery.
