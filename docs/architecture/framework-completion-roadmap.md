---
type: Concept
id: DOCS-architecture-framework-completion-roadmap
schema_version: awkp/0.1
title: Framework completion roadmap
description: Implementation-facing roadmap for turning the AHRA starter into a reusable AI-operated Agent project framework template.
status: active
owner: team:platform
source_refs: [../../architecture/SPEC.md, ../../README.md]
evidence_refs: []
confidence: reviewed
last_verified_at: 2026-06-22T00:00:00Z
review_after: 2026-09-22T00:00:00Z
tags: [architecture, roadmap, framework]
---

# Purpose

This document maps the remaining framework gaps to explicit implementation
decisions. It is narrower than [AHRA SPEC](../../architecture/SPEC.md): this is
about what this starter should implement next, defer, or keep optional.

The target product shape is an AI-operated project framework template. Humans
may operate it through conversation with an AI, and the AI may use MCP tools to
inspect or mutate framework state. A human-facing dashboard is optional and is
not part of the default starter scope.

# Current Decisions

| # | Capability | Decision | Reason |
|---|---|---|---|
| 1 | EvidenceGate / verifier completion | Implement as P0 | Task completion is still too manual. Completion must be derived from acceptance criteria and evidence, not producer self-claim. |
| 2 | Durable control plane | Defer implementation; keep as architecture requirement | This is not a visual panel. It means durable stores, CAS, events, leases, and reconciliation behind AI/MCP operation. It matters when runs must survive crashes or concurrency. |
| 3 | Runtime sandbox provider | Pending alignment | Worktree isolation protects source files, but it is not process, network, or secret isolation. Default sandbox product/profile must be chosen before implementation. |
| 4 | ApprovalService | Document now; defer implementation until approval cases are selected | Approval is a durable authorization object, not a UI requirement. Current manual resume covers only one narrow plan-approval path. |
| 5 | Project scaffold / initialization | Optional | Copying the whole starter is valid. A helper is only useful to remove sample state, prevent ID collisions, create first tasks, and run a doctor check. |
| 6 | CI gates | Optional | Some projects will not use CI. Keep local checks authoritative and document CI as an optional wrapper. |
| 7 | Observability and Evaluation | Document now; implement after EvidenceGate | Trace, audit, cost, replay, and eval should exist as framework concepts, but the first implementation can stay small and local. |

# Clarifications

## Durable Control Plane Is Not a Dashboard

The control plane is the framework's state authority and command surface:

- Run state, lease, and fencing-token writes.
- Task state transitions through AWKP rules.
- Artifact and Evidence references.
- Approval records.
- Event publication and reconciliation.
- MCP tools that expose safe commands to AI agents.

A dashboard would only be one optional client. If the product is AI-only, the
same control plane can be operated entirely through MCP and project files.

## ApprovalService Is Not the Same as EvidenceGate

EvidenceGate decides whether a task may move to `completed`.

ApprovalService decides whether a specific risky action may happen before or
during a run, for example:

- execute a high-risk tool;
- resume a plan that requires explicit authorization;
- write outside a normal workspace;
- deploy, publish, delete, spend money, or call an external service.

Approval must bind a specific actor, action, resource, parameter digest, scope,
expiry, and decision. It must not become a vague permanent permission such as
"this agent can do anything later."

## Scaffold Is a Safety Helper, Not a Runtime Requirement

Copying the whole project is a valid adoption path. A future scaffold command
would exist only to make copying less error-prone:

- replace project names and identifiers;
- clear or archive sample `work/tasks/*`;
- create a first task and context with unique IDs;
- refresh indexes;
- validate local paths and commands;
- run `python scripts/check.py`.

If manual copying stays reliable, scaffold can remain optional.

# Recommended Next Sequence

1. Implement EvidenceGate as the next code task.
2. Add minimal local observability/eval artifacts after EvidenceGate.
3. Revisit runtime sandbox once the default local sandbox profile is chosen.
4. Revisit ApprovalService when the first non-plan high-risk action needs it.
5. Treat durable control plane, scaffold, and CI as later or optional layers.
