---
type: WorkItem
id: TASK-0021
schema_version: awkp/0.1
title: Reconcile repository truth and freeze obsolete backlog
description: Establish a factual baseline of code, tasks, entrypoints, tests, and component wiring before changing architecture.
context_id: CTX-ahra-dynamic-kernel
priority: P0
risk_level: R1
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-25T00:00:00Z
depends_on: []
input_refs:
  - AHRA-DYNAMIC-KERNEL-MASTER-PLAN.md
  - work/index.md
  - README.md
  - AGENTS.md
  - src/ahra/
  - docs/
  - architecture/
  - contracts/
  - skills/
output_contract:
  - kind: repository_baseline
  - kind: component_inventory
  - kind: task_drift_report
  - kind: backlog_reconciliation
  - kind: verification_report
---

# Goal

Create one auditable view of what is actually implemented, what is only documented, what is active work, and what is stale or duplicated.

# Scope

- Run and record the current supported baseline checks without changing code first.
- Inventory default CLI commands, package scripts, Skills, adapters, contracts, services, docs, examples, tasks, and test consumers.
- Classify every component as core, adapter, experimental, legacy, removal_candidate, or archived.
- Trace the real call path from each default entrypoint to stores, policy, runtime, artifacts, evidence, and completion.
- Reconcile code/task drift, including any task whose planned capability already partially exists in code.
- Review TASK-0011 through TASK-0020 and append an explicit retain, rewrite, defer, cancel, or reconcile decision through AWKP events.
- Confirm TASK-0021 through TASK-0032 IDs are free before creating authoritative task directories.

# Non-goals

- Do not implement the new architecture.
- Do not delete code or rewrite event history.
- Do not mark a task completed merely because similar code exists.

# Acceptance criteria

- [ ] A machine-readable component inventory covers every default-visible package, command, Skill, adapter, contract family, active architecture document, and active task.
- [ ] Each inventory entry names owner, lifecycle class, entrypoints, consumers, tests, served Core Objects, and replacement/removal information.
- [ ] Baseline command results and environment limitations are preserved as Evidence.
- [ ] A drift report distinguishes implemented, partially implemented, documented-only, duplicate, and dead paths.
- [ ] TASK-0011 through TASK-0020 have append-only, human-direction-consistent reconciliation outcomes; no history is rewritten.
- [ ] No file is deleted and no new runtime behavior is introduced.
- [ ] Proposed task IDs are confirmed or remapped atomically.

# Verification method

- python scripts/check.py
- python scripts/lint_awkp.py
- git diff --check
- CLI help/entrypoint inventory
- Import and consumer scan

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

Risk level: **R1**. This task is the authority reset. Any unexpected failing baseline becomes a recorded blocker, not an excuse to silently change acceptance criteria.
