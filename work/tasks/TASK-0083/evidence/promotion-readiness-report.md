---
type: Evidence
id: EVD-TASK-0083-PROMOTION-READINESS
schema_version: awkp/0.1
title: Workflow A promotion readiness report
description: Maps component:alignment-session-manager readiness to component lifecycle requirements after the dogfood semantic-review repairs.
owner: agent:codex-supervisor
status: active
created_by: agent:codex-supervisor
created_at: 2026-07-01T18:01:46.3094319Z
---

# Summary

`component:alignment-session-manager` is not ready for default-visible promotion.

The completed prerequisite tasks and the post-dogfood repair are meaningful:

- TASK-0079 established independent semantic/code-review evidence for development-bounded code changes.
- TASK-0080 moved Workflow A dogfood artifacts and store paths into task-scoped run storage.
- TASK-0081 exposed the explicit experimental `workflow-a` lifecycle and preserved both human gates.
- TASK-0082 kept the component experimental and documented promotion criteria.
- Commit `a1fa038` made development-bounded code-change nodes fail closed when no semantic review gate is declared, added a real semantic-review gate to the dogfood request, and increased the development node budget so executor plus reviewer can complete.

Those facts close the previously observed dogfood supervision gaps. They do not yet prove the default-visible consumer requirement.

# Component Lifecycle Mapping

| Requirement | Current evidence | Readiness |
|---|---|---|
| One authoritative description | `docs/architecture/intent-alignment-workflow.md`, `docs/architecture/framework-entrypoints.md` | Ready |
| Executable entrypoint | `ahra workflow-a start/advance/snapshot/approve-requirement/draft/admit/authorize` | Ready as explicit experimental surface |
| Non-fixture consumer or explicit fixture-only label | Tests and dogfood request exist, but no EvidenceGate-approved non-fixture Workflow A lifecycle output has been consumed by Workflow B | Blocked |
| Contract and failure tests | `tests/test_alignment_session.py`, `tests/test_cli.py`, request/admission/approval tests | Ready |
| Owner and review date | `component:alignment-session-manager` inventory entry | Ready |
| Security and side-effect classification | Inventory entry documents AgentDriver use, explicit file writes, untrusted RequestDraft, and ApprovalService Gate 2 | Ready |
| Artifact/Evidence behavior | TASK-0077..0082 and post-dogfood repair evidence document artifacts, review behavior, and task-scoped run paths | Ready for experimental use |

# Readiness Decision

The correct decision is to keep:

- `lifecycle_class: experimental`
- `default_visible: false`
- `workflow-a` as an explicit experimental CLI surface

Promotion is blocked until a later task proves a non-fixture Workflow A to Workflow B consumer path:

1. Run Workflow A with a non-fixture AgentDriver or an explicitly approved non-fixture local driver boundary.
2. Produce an authorized `GoalExecutionRequest` through `workflow-a authorize`.
3. Prove Workflow B consumes that request through `goal validate`, `goal plan`, and `goal start`.
4. Record the result as EvidenceGate-reviewed task evidence before changing `default_visible` to true.

# Documentation Changes

- `docs/architecture/component-inventory.json` now records `promotion_status`, concrete `promotion_blockers`, and non-circular promotion criteria.
- `docs/architecture/framework-entrypoints.md` now states that default-visible promotion requires non-fixture Workflow A to Workflow B consumer proof.

# Residual Risk

This report intentionally does not promote Workflow A. It narrows the next promotion task to one missing proof: non-fixture Workflow A output consumed by Workflow B.
