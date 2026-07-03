---
type: WorkItem
id: TASK-0024
schema_version: awkp/0.1
title: Implement Evidence v2 validity and deterministic invalidation
description: Bind evidence to exact claims, subjects, dependencies, gates, policies, runtimes, and verifier releases.
context_id: CTX-ahra-dynamic-kernel
priority: P0
risk_level: R1
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-25T00:00:00Z
depends_on: [TASK-0023]
input_refs:
  - docs/architecture/verification-system.md
  - src/ahra/evidence_gate.py
  - artifact/evidence manifests
  - TASK-0023 contracts
output_contract:
  - kind: evidence_v2_schema
  - kind: evidence_registry
  - kind: fingerprint_builder
  - kind: invalidation_engine
  - kind: migration_adapter
  - kind: tests
---

# Goal

Make Evidence safely reusable when nothing relevant changed and reliably stale when an input changed.

# Scope

- Define Evidence v2 and GateRun records with content digests and validity state.
- Implement canonical fingerprint generation.
- Implement invalidation for changed subjects, dependencies, claims, gates, policies, runtimes, tests, verifier releases, TTL, revocation, and contradiction.
- Preserve old Evidence records and create status/supersession events rather than overwriting.
- Provide a compatibility adapter for existing AWKP evidence manifests.
- Expose inspect APIs showing why evidence is current or stale.

# Non-goals

- Do not implement Gate selection or Defect repair.
- Do not delete Evidence v1 records.
- Do not infer dependencies from unrestricted model text.

# Acceptance criteria

- [ ] Identical canonical inputs produce the same fingerprint regardless of map ordering.
- [ ] Changing any bound digest makes dependent Evidence stale.
- [ ] Unrelated Artifact changes do not invalidate Evidence when the graph proves no dependency.
- [ ] Unknown or incomplete dependency information causes conservative invalidation.
- [ ] TTL, revocation and contradiction are represented distinctly and audibly.
- [ ] Existing Evidence can be read through a clearly labeled legacy adapter but is not silently treated as fully fingerprinted.
- [ ] Tests cover direct, transitive, unrelated, policy, gate, TTL and contradiction cases.

# Verification method

- python scripts/check.py
- evidence fingerprint property tests
- invalidation graph tests
- legacy manifest compatibility tests
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

Risk level: **R1**. Evidence status is metadata/projection; immutable evidence payloads remain content-addressed.
