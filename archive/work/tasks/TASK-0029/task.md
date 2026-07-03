---
type: WorkItem
id: TASK-0029
schema_version: awkp/0.1
title: Implement static PlanIR DAG scheduling and authoritative state wiring
description: Execute a hand-authored admitted PlanIR with bounded concurrency, checkpoints, retries, cancellation, and verification.
context_id: CTX-ahra-dynamic-kernel
priority: P0
risk_level: R2
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-25T00:00:00Z
depends_on: [TASK-0028]
input_refs:
  - PlanIR compiler
  - node executor registry
  - verification service
  - RunService/CAS/Lease
  - AWKP adapters
output_contract:
  - kind: plan_execution_service
  - kind: dag_scheduler
  - kind: checkpoint_records
  - kind: state_adapters
  - kind: reconciler_checks
  - kind: static_vertical_slice
---

# Goal

Prove the trusted control and execution planes independently of any Planner model.

# Scope

- Implement PlanExecution and NodeRun state machines with CAS/lease semantics.
- Schedule ready DAG nodes with bounded concurrency and deterministic dependency handling.
- Persist checkpoints, budgets, Artifact/Evidence refs, failures and cancellation propagation.
- Connect RunService, Plan execution state and AWKP Goal/Task projection through explicit adapters; remove or document duplicate authority.
- Invoke VerificationService at declared node/integration/goal boundaries.
- Add reconciler checks for orphan runs, expired leases, missing evidence and inconsistent projections.
- Run a static fixture PlanIR end-to-end.

# Non-goals

- Do not call a dynamic Planner.
- Do not implement distributed queues or remote workers.
- Do not remove legacy runner.

# Acceptance criteria

- [ ] Only admitted immutable PlanIR can start execution.
- [ ] DAG dependencies, concurrency limits, budgets and deadlines are enforced.
- [ ] Crash/restart simulation resumes from checkpoint without repeating completed idempotent nodes.
- [ ] Stale lease/fencing token writes are rejected.
- [ ] Cancellation propagates to active nodes and leaves auditable terminal state.
- [ ] Task/Goal, PlanExecution and NodeRun each retain distinct authority.
- [ ] The static vertical slice produces complete Artifact/Evidence/Trace/Handoff records and passes the Goal completion gate.

# Verification method

- python scripts/check.py
- static PlanIR end-to-end fixture
- checkpoint/recovery tests
- lease/CAS tests
- cancellation tests
- reconciler tests
- git diff --check

# Required evidence and handoff

- Publish an implementation/change report with exact files, contracts, migrations, known limitations, and unresolved items.
- Preserve deterministic command outputs or structured summaries with content digests.
- Map every acceptance criterion to one or more Evidence IDs.
- Record the producer Agent Release, Context Manifest, workspace/branch, base commit, and final commit or rejected patch.
- Create an immutable Handoff with one exact next action when blocked, failed, paused, or returned for changes.
- The producer must not mark this task completed; an independent verifier and EvidenceGate decide completion.

# Rollback and compatibility

- Do not silently overwrite released contracts or historical events.
- Use a new schema version when field meaning changes or compatibility is broken.
- Keep compatibility adapters until the task explicitly authorizes their removal.
- Any rollback must preserve Artifact/Evidence references and explain state projection changes.

# Risk and approvals

Risk level: **R2**. Passing this task completes SG-2. Dynamic planning is forbidden before this gate.
