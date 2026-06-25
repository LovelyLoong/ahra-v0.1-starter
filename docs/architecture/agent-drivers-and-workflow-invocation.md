---
type: Architecture
id: ARCH-agent-drivers-workflow-invocation
schema_version: awkp/0.1
title: Agent drivers and workflow invocation
description: Records the legacy workflow invocation model without binding the template to one agent product or SDK.
status: active
owner: team:platform
source_refs:
  - ../../architecture/decisions/ADR-0005-agent-neutral-workflow-invocation.md
  - ../../architecture/decisions/ADR-0006-reference-runtime-adapters-mcp-and-resume.md
  - ../../docs/architecture/workflow-modules.md
evidence_refs: []
confidence: reviewed
last_verified_at: 2026-06-22T00:00:00Z
review_after: 2026-09-22T00:00:00Z
tags: [architecture, workflow, drivers]
---

# Summary

AHRA separates workflow control from agent execution.

This document now describes the legacy workflow compatibility path. The current
default dynamic-kernel operation path is defined by `framework-entrypoints.md`
and `component-inventory.json`.

Workflow modules decide the deterministic process: attempts, policy gates,
checks, reviewer gates, rollback, dynamic planning, and approval pauses.
Agent drivers perform bounded role work inside that process. A driver may be
Codex, Claude Code, an open-source agent framework, OpenAI Agents SDK, a local
command adapter, a direct LLM API, or a human review service.

No workflow module may know which product implements the driver.

# Objects

`WorkflowRunRequest` is the stable launch object. It answers:

- Which workflow module should run.
- Which task, goal, or module input should be used.
- Which workspace should be used.
- Which agent driver should perform role work.
- Which artifact/evidence store receives outputs.
- Whether planner output needs human approval.
- Which scheduling decision and execution policy the calling Agent chose.

`AgentDriver` is the stable execution port. It answers:

- Given a role and structured input, produce a structured result.
- Preserve role boundaries.
- Keep provider SDKs, credentials, tracing, and prompt packaging outside AHRA
  core.

`AgentDriverRegistry` resolves a `driverRef` to a driver adapter. It must fail
closed when a driver is missing or duplicated.

# Driver Roles

The initial role vocabulary is:

| Role | Purpose | Expected output |
|---|---|---|
| `executor` | Mutate the isolated workspace for one bounded task | `WorkReport` |
| `task_reviewer` | Independently judge one task attempt | `ReviewResult` |
| `goal_reviewer` | Independently judge cumulative goal satisfaction | `GoalReviewResult` |
| `planner` | Propose bounded next tasks or escalate | `NextStepDecision` |

Role names are part of the contract. Adding a role changes the observable
workflow contract and requires documentation, schema, and tests.

# Launch Contract

An agent-friendly request looks like this:

```yaml
apiVersion: ahra.dev/v1alpha1
kind: WorkflowRunRequest
metadata:
  name: example-standard-task
spec:
  moduleId: standard-harness
  input:
    taskRef: work/tasks/TASK-1234/task.yaml
  workspaceRef: .
  driverRef: codex-python-sdk
  storeRef: local-file
  artifactDir: .runtime/ahra-runs/TASK-1234
  approvalMode: manual
```

The request is intentionally independent from any one caller. In the current
repository it is used only by explicit legacy workflow compatibility calls.

MCP is not part of the current default starter route.

# Approval Modes

`approvalMode` controls the planner boundary for workflow modules that can
produce follow-up tasks:

| Mode | Behavior |
|---|---|
| `manual` | The workflow may ask the planner for follow-up tasks, saves the proposal, and pauses with `awaiting_plan_approval`. |
| `auto` | The workflow may ask the planner for follow-up tasks and execute accepted proposals within the module's deterministic limits. |
| `disabled` | The workflow does not request planner proposals. If existing tasks and gates cannot satisfy the goal, the run blocks. |

Workflow modules without a planner phase still validate and record
`approvalMode`, but the field has no extra behavior for that module.

# Legacy Operation

When a user explicitly asks an agent to start a legacy workflow, the agent
should:

1. Read the local skill for workflow running.
2. Locate or create a `WorkflowRunRequest`.
3. Validate the request against the contract schema.
4. Resolve the workflow module and `driverRef`.
5. Call the legacy workflow compatibility command.
6. Report the resulting run id, status, artifact dir, and evidence refs.
7. Leave AWKP Task completion to the evidence gate and independent verifier.

The launch agent is not the workflow implementation. It is only a caller of the
runner API unless it is explicitly registered as a driver adapter.

# Scheduling Boundary

The Agent that starts a workflow is the scheduling Agent for that run. It may
choose bounded execution parameters through `schedulerDecision`, including
attempt count, heartbeat cadence, idle timeout, per-attempt wall timeout, and
the overall run deadline. That decision is recorded as a run artifact so later
inspection can distinguish policy from implementation behavior.

`schedulerDecision.executionPolicy.maxAttempts` is the generic attempt limit.
When omitted it defaults to `2`. The same limit bounds executor attempts and
reviewer output-contract retries; invalid values fail request validation before
any Agent role is started.

The scheduling Agent does not own task state transitions or acceptance. The
reference runner still owns the workflow state machine, lease-aware execution,
artifacts, evidence, rollback, and terminal result records. AWKP completion
still belongs to EvidenceGate and an independent verifier.

# Adapter Rules

- Driver adapters must not be imported by AHRA domain code.
- Driver adapters must return structured outputs, not prose-only success
  claims.
- Driver adapters must declare capabilities rather than relying on fallback
  guessing.
- A Codex adapter, Claude Code adapter, OpenAI Agents adapter, and local LLM
  adapter are peer implementations.
- Provider credentials remain outside prompts, Memory, Artifact, Evidence,
  Trace, and Snapshot.

# Reference Adapter Policy

The starter may provide optional adapters under `src/ahra/adapters/`.
Adapters are not part of the workflow module contract.

The Codex Python SDK adapter is the starter's first concrete non-fixture local
driver adapter. It is registered as `codex-python-sdk`, consumes the user's
local Codex SDK setup, and must fail closed when the optional package,
workspace binding, or account setup is missing.

The starter does not provide a separate command-line fallback driver. If the
user's Codex SDK setup requires authentication, the workflow should report the
SDK error and let the user complete that setup outside AHRA.

Claude Code, OpenAI Agents SDK, local command agents, direct LLM APIs, and
open-source agent frameworks can be added the same way. Adding one must not
change `WorkflowRunRequest`, workflow module descriptors, or AHRA domain
objects.

# Resume Requests

Manual approval is a second operation, not a new launch. When a workflow pauses
with `awaiting_plan_approval`, the caller must submit `WorkflowResumeRequest`
with a decision bound to the exact plan artifact SHA-256.

This keeps approval scoped to the plan that was actually reviewed. It also
lets an agent say "approve this plan" through a file, direct Python API, or
CLI command without guessing workflow internals.

# Deprecated MCP Operation Surface

The local MCP server is no longer the default starter entrypoint. It may remain
temporarily as a legacy adapter surface, but new work should not add MCP-only
operations.

If kept, MCP must only wrap the same operations as the Python API:

- list workflow modules
- validate request documents
- start workflow runs
- inspect local run artifacts
- resume approved manual plans

MCP tools must not bypass schema validation, module registry resolution,
driver registry resolution, or artifact/evidence writing. The preferred future
operation surface is CLI plus Skill.

# Legacy Starter Scope

The legacy workflow compatibility surface provides:

- The request schema.
- A driver registry.
- A reference runner API.
- A fake driver for tests.
- Agent-facing local Skills and documentation that identify this as a legacy
  path.
- A hidden CLI compatibility wrapper around the stable local APIs.
- An optional Codex Python SDK driver adapter.
- A manual resume request path for approved planner proposals.

This compatibility surface should not provide:

- A mandatory `ProjectAdapter`.
- A mandatory model provider integration.
- A required CLI.
- A required MCP server.
- A special Codex-only path.
