---
type: Concept
id: DOCS-architecture-framework-completion-roadmap
schema_version: awkp/0.1
title: Framework completion roadmap
description: Implementation-facing roadmap for turning the starter into an Agent workflow foundation.
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
about what this Agent workflow foundation should implement next, defer, or keep
optional.

The target product shape is an Agent project foundation: a work-governance
framework, executable standard workflows, project adaptation rules, and custom
workflow extension contracts. Humans may operate it through conversation with
an AI, but the default operation surface is CLI plus local Skill plus
repository documentation. The CLI wraps existing Python APIs. MCP is not part
of the current default starter route. A
human-facing dashboard is optional and is not part of the default starter
scope.

# Current Decisions

| # | Capability | Decision | Reason |
|---|---|---|---|
| 1 | Product position | Agent workflow foundation | The project is a complete Agent work system, not merely an outer harness template. |
| 2 | EvidenceGate / verifier completion | Implemented local path; keep as the completion gate | Task completion is derived from acceptance criteria and evidence, not producer self-claim. |
| 3 | Operation entrypoint | Default to CLI plus Skill plus docs; keep MCP as a legacy optional route | The foundation should be operable from local instructions and commands before depending on an agent-client integration protocol. |
| 4 | Runtime sandbox provider | Default local boundary is run-owned Git worktree isolation; defer stronger sandbox providers | Worktree isolation is enough for the starter. It does not claim process, network, or secret isolation. |
| 5 | Custom workflows | Allow extension through workflow module contracts before building higher-level composition tools | Users may build project-specific workflows, but stable contracts must come before a broad builder. |
| 6 | Durable control plane | Defer implementation; keep as architecture requirement | This is not a visual panel. It means durable stores, CAS, events, leases, and reconciliation behind local command/API operation. It matters when runs must survive crashes or concurrency. |
| 7 | ApprovalService | Document now; defer implementation until approval cases are selected | Approval is a durable authorization object, not a UI requirement. Current manual resume covers only one narrow plan-approval path. |
| 8 | Project scaffold / initialization | Optional | Copying the whole starter is valid. A helper is only useful to remove sample state, prevent ID collisions, create first tasks, and run a doctor check. |
| 9 | CI gates | Optional | Some projects will not use CI. Keep local checks authoritative and document CI as an optional wrapper. |
| 10 | Observability and Evaluation | Implemented minimal local records | Trace, audit, cost, replay, and eval should exist as framework concepts, but the first implementation can stay small and local. |

# Direction

The foundation has five layers:

- work-governance framework;
- standard workflows;
- project adaptation;
- custom workflow extension;
- operation entrypoint.

The preferred path is to run work through standard workflows. External agents
and human-operated tools may still be used, but governance is mandatory:
state, scope, evidence, artifacts, handoff, and completion must follow the
framework rules.

# Clarifications

## Durable Control Plane Is Not a Dashboard

The control plane is the framework's state authority and command surface:

- Run state, lease, and fencing-token writes.
- Task state transitions through AWKP rules.
- Artifact and Evidence references.
- Approval records.
- Event publication and reconciliation.
- CLI commands or direct local API calls that expose safe operations to AI
  agents.

A dashboard would only be one optional client. If the product is AI-only, the
same control plane can be operated through local Skills, repository
documentation, CLI commands, and project files.

## MCP Is Not the Default Entry Point

MCP is deprecated as a default starter route.

Existing MCP code can remain temporarily as a legacy adapter surface, but new
framework work should not add MCP-only features. The stable operation surface
is CLI plus Skill, where the CLI calls the same Python APIs that tests already
exercise.

## Worktree Isolation Is the Local Default

For the local starter profile, run-owned Git worktree isolation is the selected
default. It separates the source worktree from workflow mutation and keeps
accepted changes on run-owned branches until a human or authorized workflow
acts.

This is not process, network, host, or secret isolation. OCI containers,
devcontainers, VMs, remote sandboxes, and secret brokers remain future adapter
work and should not be implied by local runtime examples.

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

1. Keep TASK-0009 in verifier review and use it to close the local isolation
   and entrypoint alignment.
2. Align the top-level README and architecture docs around the Agent workflow
   foundation position.
3. Use the CLI plus Skill operation surface for follow-up executable tasks.
4. Keep examples split into test fixtures and runnable examples so
   `fake-reference` cannot be mistaken for a default driver.
5. Revisit ApprovalService when the first non-plan high-risk action needs it.
6. Treat durable control plane, scaffold, CI, and higher-level workflow
   composition helpers as later or optional layers.
