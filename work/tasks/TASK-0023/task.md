---
type: WorkItem
id: TASK-0023
schema_version: awkp/0.1
title: Define GoalContract, ClaimGraph, and GatePlan contracts
description: Create machine-valid acceptance-first contracts before implementing any dynamic planner.
context_id: CTX-ahra-dynamic-kernel
priority: P0
risk_level: R1
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-25T00:00:00Z
depends_on: [TASK-0022]
input_refs:
  - docs/architecture/verification-system.md
  - SPEC.md
  - contracts/schemas/
output_contract:
  - kind: goal_contract_schema
  - kind: claim_graph_schema
  - kind: gate_definition_schema
  - kind: gate_plan_schema
  - kind: validators
  - kind: contract_tests
---

# Goal

Represent human success criteria as stable Claims with explicit verification responsibility.

# Scope

- Define JSON Schemas and provider-neutral domain objects for GoalContract, ClaimGraph, Claim, GateDefinition, and GatePlan.
- Support functional, structural, quality, security, operational, and governance Claim types.
- Require stable IDs, criterion provenance, dependencies, risk, evidence kinds, and gate refs.
- Implement deterministic validation for coverage, unique IDs, acyclic dependencies, registered gates, and mandatory security/governance claims.
- Provide valid and invalid examples plus compatibility/versioning rules.

# Non-goals

- Do not call an LLM to generate claims yet.
- Do not implement PlanIR or scheduling.
- Do not execute verification commands.

# Acceptance criteria

- [ ] Every Goal criterion must map to at least one Claim and uncovered criteria fail validation.
- [ ] Every required Claim must map to a Gate or explicit approval requirement.
- [ ] Claim dependencies are checked for cycles and missing references.
- [ ] Security and governance Claim requirements cannot be downgraded by extension fields.
- [ ] Schemas reject unknown major versions and malformed IDs while allowing compatible extension fields.
- [ ] Contract tests include valid, uncovered, cyclic, duplicate, and forbidden-downgrade cases.
- [ ] No model/provider SDK is imported by the domain or validation layer.

# Verification method

- python scripts/check.py
- schema example validation
- contract unit tests
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

Risk level: **R1**. This task creates acceptance structure only. Claim generation strategy is deferred to TASK-0030.
