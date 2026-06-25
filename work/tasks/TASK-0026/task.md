---
type: WorkItem
id: TASK-0026
schema_version: awkp/0.1
title: Define and implement PlanDraft-to-PlanIR compilation
description: Create the trusted executable representation and deterministic validation boundary for model-generated plans.
context_id: CTX-ahra-dynamic-kernel
priority: P0
risk_level: R1
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-25T00:00:00Z
depends_on: [TASK-0025]
input_refs:
  - docs/architecture/plan-ir.md
  - Goal/Claim/Gate contracts
  - src/ahra/ports.py
output_contract:
  - kind: plan_draft_schema
  - kind: plan_ir_schema
  - kind: plan_patch_schema
  - kind: plan_compiler
  - kind: plan_validator
  - kind: validation_report
  - kind: tests
---

# Goal

Ensure the Scheduler can execute only finite, typed, claim-covered, immutable plans.

# Scope

- Define PlanDraft, PlanIR, PlanPatchDraft, PlanNode, edge, input/output, budget, retry, timeout, compensation, Gate responsibility, and capability request contracts.
- Implement canonical compilation and plan digest.
- Validate DAG structure, references, node types, Claim coverage, output consumers, budgets, fan-out, terminal Goal verification, and immutable refs.
- Resolve only registered node/Gate/runtime identifiers.
- Produce a structured PlanValidationReport with all errors, not only the first one.
- Add valid and adversarial fixture plans.

# Non-goals

- Do not call a Planner model.
- Do not execute nodes.
- Do not grant capabilities yet.

# Acceptance criteria

- [ ] The Scheduler-facing API accepts PlanIR only and cannot receive PlanDraft.
- [ ] Cycles, missing refs, duplicate IDs, unbounded fan-out, absent Gate responsibility, uncovered Claims, invalid budgets and mutable latest refs fail closed.
- [ ] Canonical equivalent drafts compile to the same PlanIR digest.
- [ ] A PlanPatch creates a new plan version and cannot mutate the parent.
- [ ] Validation reports are Artifacts suitable for Evidence references.
- [ ] Domain/compiler code imports no concrete model or workflow SDK.

# Verification method

- python scripts/check.py
- schema tests
- DAG/property tests
- adversarial plan tests
- digest determinism tests
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

Risk level: **R1**. Keep the first node type set small; do not add a general code-generated workflow node.
