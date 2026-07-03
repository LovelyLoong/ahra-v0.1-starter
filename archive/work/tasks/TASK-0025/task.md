---
type: WorkItem
id: TASK-0025
schema_version: awkp/0.1
title: Build layered verification, Defect records, and selective reverification
description: Implement L0/L1/L2 gate selection and defect-driven local repair semantics without a dynamic planner.
context_id: CTX-ahra-dynamic-kernel
priority: P0
risk_level: R1
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-25T00:00:00Z
depends_on: [TASK-0024]
input_refs:
  - docs/architecture/verification-system.md
  - TASK-0023 contracts
  - TASK-0024 evidence registry
  - src/ahra/evidence_gate.py
output_contract:
  - kind: verification_selection_schema
  - kind: defect_record_schema
  - kind: verification_service
  - kind: selection_engine
  - kind: completion_gate_v2
  - kind: tests
---

# Goal

Allow final acceptance to cover all Claims while physically rerunning only stale, failed, or mandatory Gates.

# Scope

- Define VerificationTrigger, VerificationSelection, VerificationResult, and DefectRecord contracts.
- Implement deterministic reverse-dependency impact analysis and Gate selection.
- Implement L0, L1 and L2 Gate classes and mandatory safety baseline rules.
- Upgrade completion logic to require current Evidence for every required Claim.
- Generate DefectRecord on failed Gate/Claim with reproduction and repair boundary.
- Add a fixture proving a local change selects fewer Gates than a full run while final logical coverage remains complete.

# Non-goals

- Do not generate repair plans.
- Do not execute arbitrary Agent nodes.
- Do not remove the existing task EvidenceGate compatibility path.

# Acceptance criteria

- [ ] Selection is deterministic for the same graph, changes and policy.
- [ ] Failed Gates, affected Claims, downstream integration boundaries, and mandatory safety Gates are selected.
- [ ] Unchanged current Evidence is reused only when fingerprints match.
- [ ] Completion fails for missing, stale, expired, revoked or contradicted Evidence.
- [ ] A failed Gate creates a structured Defect with exact Claim, Gate, expected/actual, refs and repair boundary.
- [ ] The selective fixture executes fewer Gates than the declared full set and records the rationale.
- [ ] The existing Task completion path remains fail-closed during migration.

# Verification method

- python scripts/check.py
- full-vs-selective fixture
- defect lifecycle tests
- completion coverage tests
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

Risk level: **R1**. Passing this task completes SG-1. Do not proceed if selective reuse cannot be proven safe.
