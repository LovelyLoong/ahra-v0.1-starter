---
type: Handoff
id: HANDOFF-TASK-0003-0001
schema_version: awkp/0.1
title: Agent-neutral workflow invocation ready for verification
description: Handoff for independent review of the workflow invocation and driver registry changes.
status: active
owner: agent:verifier
source_refs: [../task.md, ../state.json, ../artifact-manifest.json]
evidence_refs: [EVD-TASK-0003-0001]
confidence: tested
last_verified_at: 2026-06-22T08:52:42Z
review_after: 2026-09-22T00:00:00Z
tags: [handoff, workflow, drivers]
---

# Goal and state

TASK-0003 is in `review`. The implementation agent has not marked the task
completed.

# Completed

- Added ADR-0005 for agent-neutral workflow invocation.
- Added architecture documentation for driver roles, registry, and launch
  requests.
- Added `WorkflowRunRequest` schema and example requests.
- Added local workflow runner skill instructions.
- Converted the reference runner driver boundary to role-based requests.
- Added a fail-closed `AgentDriverRegistry`.
- Added runner API tests that start `standard-harness` through request +
  registry.

# Verification

The verification report is `../evidence/agent-neutral-workflow-invocation-report.json`.
Rerun the task verification commands before moving this item out of `review`.

# Exact next action

Independent verifier reruns checks, reviews the contract boundary, then updates
state to `completed` or `changes_requested`.

# Blockers and required input

None known.

# Failed approaches

None recorded.

# Risks and assumptions

No production vendor driver is included. Codex, Claude Code, OpenAI Agents SDK,
and open-source agent frameworks are expected to be peer adapters.

# Touched assets

Architecture docs, contracts, examples, local skill instructions, reference
runner driver/invocation code, tests, and AWKP task package.

# Lease

Released; no holder.
