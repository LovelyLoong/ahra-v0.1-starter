---
type: WorkItem
id: TASK-0032
schema_version: awkp/0.1
title: Remove or quarantine legacy and unwired paths and close the migration
description: Make the new dynamic kernel the only default path while preserving explicit compatibility and audit history.
context_id: CTX-ahra-dynamic-kernel
priority: P1
risk_level: R2
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-25T00:00:00Z
depends_on: [TASK-0031]
input_refs:
  - component-inventory.yaml
  - repository consolidation policy
  - SG-3 evidence
  - legacy workflow/MCP/docs/examples
output_contract:
  - kind: clean_default_entrypoints
  - kind: legacy_or_removal_changes
  - kind: final_component_inventory
  - kind: migration_guide
  - kind: archived_tasks_docs
  - kind: release_verification
---

# Goal

Ensure users and Agents cannot accidentally enter obsolete, disconnected, or misleading paths.

# Scope

- Re-evaluate every component inventory entry using SG-3 evidence.
- Remove MCP from default scripts/docs/Skill; delete it or package it as explicit optional legacy only when a real consumer is recorded.
- Freeze, isolate, or remove loop-engineering and old WorkflowModule execution paths after compatibility needs are assessed.
- Move Memory/demo-only capabilities to experimental/examples unless wired to the new core.
- Remove duplicate state stores or retain only through a documented adapter/reconciler.
- Archive superseded documents and completed task directories from default Agent context while preserving history.
- Update README, AGENTS, CLI, Skill, package metadata and indexes to point only to the new default path.
- Add lifecycle lint preventing regression.

# Non-goals

- Do not erase Git history, events, ADRs or released schemas.
- Do not remove a compatibility path before its replacement and migration tests pass.
- Do not introduce new features.

# Acceptance criteria

- [ ] Every default-visible component is classified core or selected adapter and satisfies lifecycle requirements.
- [ ] No default CLI/script/doc depends on MCP, loop-engineering, demo-only stores, or fake drivers.
- [ ] Legacy capabilities have explicit location, owner, compatibility scope and removal trigger, or are deleted with migration notes.
- [ ] One authoritative runtime path connects Goal, Claims, PlanIR, Scheduler, Capability, Artifact, Evidence and Completion.
- [ ] Active docs contain no contradictory default-route statements.
- [ ] Archive content is excluded from normal Context Builder read order but remains traceable.
- [ ] Full local checks, static fixture, dynamic fixture, security tests and migration tests pass.
- [ ] Final component inventory contains no unowned or untested Core entry.

# Verification method

- python scripts/check.py
- python scripts/lint_awkp.py
- git diff --check
- default entrypoint smoke
- static and dynamic fixtures
- security suite
- legacy import/reference scan
- packaging install smoke

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

Risk level: **R2**. Passing this task completes SG-4 and the first dynamic-kernel migration.
