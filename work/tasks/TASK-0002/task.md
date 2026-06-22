---
type: WorkItem
id: TASK-0002
schema_version: awkp/0.1
title: Integrate pluggable workflow modules into the AHRA template
description: Make ahra-v0.1-starter the bottom-layer Harness template while importing standard Harness and LoopEngineering as modular workflow implementations.
context_id: CTX-ahra-workflow-modules
priority: P1
risk_level: R1
requester: human:maintainer
reviewer: agent:verifier
created_at: 2026-06-22T07:10:00Z
depends_on: []
input_refs:
  - ../../../architecture/decisions/ADR-0004-pluggable-workflow-modules.md
  - ../../../docs/architecture/workflow-modules.md
  - ../../../contracts/schemas/workflow-module.schema.json
  - E:\harness-first-starter
output_contract:
  - kind: workflow_module_contract
  - kind: reference_runner
  - kind: verification_report
---

# Goal

Use `E:\ahra-v0.1-starter` as the authoritative outer Harness template and
bring the concrete `standard-harness` and `loop-engineering` workflows in as
replaceable modules sourced from `E:\harness-first-starter`.

# Scope

- Define the workflow module contract and example module descriptors.
- Keep workflow implementations behind AHRA ports and local adapters.
- Emit CloudEvents-compatible events plus Artifact and Evidence manifest data.
- Validate module descriptors with schema and semantic registry checks.
- Leave completion to AWKP evidence review instead of self-declaring done.

# Non-goals

- Do not move provider SDKs into AHRA domain code.
- Do not make AHRA own every possible workflow.
- Do not mark this task completed before independent verification.

# Acceptance criteria

- [ ] Module descriptors reject unknown AHRA ports.
- [ ] Module descriptors reject invalid AHRA Run status mappings.
- [ ] Reference runner uses Workspace, Runtime, Artifact, Evidence, and Event boundaries instead of direct workflow-owned side effects.
- [ ] Reference runner events validate against `contracts/schemas/event.schema.json`.
- [ ] Reference runner writes Artifact and Evidence records with IDs, URIs, SHA-256 hashes, and manifests.
- [ ] AWKP task state, events, artifact manifest, evidence manifest, and handoff exist for this fusion work.

# Verification method

Run the repository tests and linters from this checkout:

- `$env:PYTHONPATH='src'; python -m unittest discover -s tests -v`
- `$env:PYTHONPATH='src'; python scripts\lint_contracts.py`
- `$env:PYTHONPATH='src'; python scripts\lint_awkp.py`

# Risk and approvals

R1. The change defines reusable workflow boundaries and therefore requires
independent verifier review before this task can become `completed`.
