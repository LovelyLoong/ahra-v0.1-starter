---
type: WorkItem
id: TASK-0035
schema_version: awkp/0.1
title: Resolve the current Evidence set and support multi-Claim Defects
description: Make supersession, invalidation and completion correct for append-only Evidence histories and represent direct versus affected Claims in Defects.
context_id: CTX-ahra-dynamic-kernel
priority: P0
risk_level: R2
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-26T00:00:00Z
depends_on: [TASK-0034]
input_refs:
  - ../../../docs/architecture/verification-system.md
  - ../../../docs/architecture/gate-execution-pipeline.md
  - ../../../src/ahra/evidence_v2.py
  - ../../../src/ahra/verification.py
  - ../../../contracts/schemas/evidence-v2.schema.json
  - ../../../contracts/schemas/defect-record.schema.json
output_contract:
  - kind: evidence_current_set_resolver
  - kind: supersession_semantics
  - kind: evidence_status_events
  - kind: multi_claim_defect_contract
  - kind: completion_migration
  - kind: selective_verification_migration
  - kind: verification_report
---

# Goal

Ensure Completion and selective reverification operate on a deterministic current Evidence set while preserving all historical failed, stale and superseded records for audit.

# Why now

Repair loops accumulate Evidence. Without explicit current-set semantics, an old failed record can either block forever or be incorrectly reused. Defects also need more than one Claim when a failure crosses integration boundaries.

# Scope

- Define supersession graph validation and current leaf resolution.
- Implement EvidenceRegistry current-set and current-passed-by-Claim queries.
- Ensure superseded history is excluded from satisfaction but remains inspectable.
- Make a stale superseding record leave the Claim uncovered rather than silently falling back to obsolete history.
- Persist or publish Evidence status/supersession events.
- Version DefectRecord to support direct_claim_refs and affected_claim_refs.
- Use affected Claims for selective Gate calculation.
- Migrate Completion and fixture tests to query the registry rather than hand-selecting final records.

# Non-goals

- Do not add SQLite persistence.
- Do not implement repair orchestration.
- Do not delete legacy Evidence.
- Do not make old AWKP Evidence fully equivalent to Evidence v2.

# Architectural invariants

- Evidence history is append-only.
- Supersession never deletes or mutates the superseded record.
- Only resolved current leaves may satisfy Claims.
- A stale/revoked/contradicted current leaf does not reactivate an older superseded record.
- Unknown or cyclic supersession fails closed.
- Completion ignores irrelevant historical failures only after current-set resolution.
- Defect affected Claims are computed or validated, not invented without trace.

# Implementation slices

1. Version schemas and add compatibility adapters.
2. Implement supersession graph validation.
3. Implement current-set snapshot/query APIs.
4. Update invalidation and Completion.
5. Update Defect construction and selective selection.
6. Migrate fixture and append-only history tests.

# Acceptance criteria

- [ ] A passed Evidence record that supersedes a prior failed record can satisfy a Claim without deleting the failed history.
- [ ] A stale/revoked/contradicted superseding record leaves the Claim uncovered and blocks Completion.
- [ ] Supersession cycles, self-supersession and unknown refs fail closed.
- [ ] Completion consumes the EvidenceRegistry current set instead of a caller-curated tuple.
- [ ] Selective verification lists current reused Evidence and historical excluded Evidence separately.
- [ ] DefectRecord supports one or more direct Claims and one or more affected Claims.
- [ ] Affected Claims include deterministic reverse dependency closure or an independently validated equivalent.
- [ ] Legacy Evidence remains legacy_partial and cannot silently satisfy M1 Claims.
- [ ] Full checks and migration tests pass.

# Required negative and adversarial cases

- failed EVD-1 superseded by passed EVD-2
- passed EVD-2 becomes stale
- two competing current leaves
- supersession cycle
- unknown supersedes ref
- revoked current leaf
- Defect affecting multiple dependent Claims
- caller omits historical records to force completion

# Verification method

- python scripts/check.py
- python scripts/lint_awkp.py
- git diff --check
- EvidenceRegistry history/current-set unit tests
- Completion append-only history tests
- selective reverification affected-Claim tests
- SG-6 trust-and-current-Evidence review

# Required metrics

- current Claim coverage
- historical Evidence count
- current Evidence leaf count
- supersession resolution failures
- stale Evidence count by reason
- false completion count

# Stop conditions

- Stop if Completion still requires a caller to remove old Evidence manually.
- Stop if a stale replacement can reactivate superseded Evidence.
- Stop if the schema change cannot preserve historical audit records.

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

Risk level: **R2**. This changes completion semantics for append-only histories. Independent review must inspect migrations and adversarial Evidence graphs.
