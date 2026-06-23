---
type: Architecture
id: ARCH-reference-runtime-adapters-mcp
schema_version: awkp/0.1
title: Reference runtime adapters and deprecated MCP entrypoint
description: Defines the Codex CLI driver adapter, optional Codex SDK driver adapter, local runtime profile, workflow resume contract, and legacy MCP operation surface.
status: active
owner: team:platform
source_refs:
  - ../../architecture/decisions/ADR-0006-reference-runtime-adapters-mcp-and-resume.md
  - ../../architecture/decisions/ADR-0005-agent-neutral-workflow-invocation.md
evidence_refs: []
confidence: reviewed
last_verified_at: 2026-06-22T00:00:00Z
review_after: 2026-09-22T00:00:00Z
tags: [architecture, adapter, mcp, resume]
---

# Summary

The reference runtime layer makes AHRA usable locally without changing AHRA
core semantics.

It contains three replaceable pieces:

- Driver adapters that implement `AgentDriver`.
- Runtime and workspace adapters for local, cloud, or sandbox execution.
- Agent-facing entrypoints, currently CLI plus documented Skills and local
  commands.

Only the local profile is implemented in the starter. Cloud and sandbox
profiles are contracts for later adapters.

MCP is no longer a default starter route.

# Codex CLI Driver

The default runnable local driver on the maintainer workstation is
`CodexCLIDriver`.

It is an adapter, not a workflow module and not AHRA core. It must:

- Implement `src/ahra/ports.py::AgentDriver`.
- Call the installed `codex exec` command through `driverRef: codex-cli`.
- Use workspace-write sandboxing for executor role work and read-only
  sandboxing for reviewer and planner role work.
- Parse the final Codex CLI response into `WorkReport`, `ReviewResult`,
  `GoalReviewResult`, or `NextStepDecision`.
- Fail closed when the Codex CLI binary is missing, returns non-zero, times
  out, omits the final response file, or returns invalid JSON.

The adapter must not:

- Become the only valid driver path.
- Bypass `AgentDriverRegistry`.
- Write credentials into prompts, artifacts, evidence, memory, or snapshots.

# Codex SDK Driver

The first optional concrete driver is `CodexSDKDriver`.

It is an adapter, not a workflow module and not AHRA core. It must:

- Implement `src/ahra/ports.py::AgentDriver`.
- Accept role-specific `AgentRunRequest` values.
- Ask Codex for structured JSON matching the expected reference-runner output
  type.
- Parse JSON into `WorkReport`, `ReviewResult`, `GoalReviewResult`, or
  `NextStepDecision`.
- Fail closed when the SDK is missing, the response is not JSON, or the JSON
  does not satisfy the expected output shape.

The adapter must not:

- Import into AHRA domain objects.
- Write credentials into prompts, artifacts, evidence, memory, or snapshots.
- Add Codex-specific fields to workflow module descriptors.
- Become the only valid driver path.

User-owned Codex account and login setup stay outside the template. The
adapter only consumes the SDK available in the user's environment.

The reference `CodexSDKClient` follows the current local SDK surface used by
the starter: sandbox and model are passed to Codex, while the process should be
started from the intended local workspace. `workspace_ref` is still included in
the driver request and prompt, but this v0.1 adapter does not claim remote or
cloud workspace attachment. A stronger workspace-aware Codex adapter can be
added later without changing `AgentDriver`.

# Runtime Profiles

The starter recognizes these runtime profile names:

| Profile | Status | Meaning |
|---|---|---|
| `local` | implemented | Worktree, commands, artifacts, and checks run on the current machine. |
| `cloud` | reserved | A future adapter provisions a remote workspace and object storage. |
| `sandbox` | reserved | A future adapter provisions an isolated runtime such as a container, VM, or remote sandbox. |

The local reference runner may use `LocalGitWorkspaceProvider`,
`LocalRuntimeProvider`, and `FileRunStore`. These are reference adapters behind
ports. They are not a claim that every project must use local Git or local
files.

The selected local isolation boundary is run-owned Git worktree isolation. It
does not claim process, network, host, or secret isolation.

# Local Workspace Isolation

For the local profile, `WorkflowRunRequest.workspaceRef` names the source Git
worktree or repository root. It is not the mutable execution directory.

The reference runner must materialize a run-owned Git worktree before invoking
`standard-harness` or `loop-engineering`. Executor, reviewer checks, commits,
rollback, and cleanup commands must target that isolated worktree, not the
source worktree named by `workspaceRef`.

The isolated worktree is part of the run evidence surface. The runner records
the source workspace, base commit, branch, and effective isolated workspace in
the run artifacts. It must fail closed if it cannot create or recover that
workspace.

Manual resume continues the same isolated worktree that the paused run used.
The caller still provides the original `workspaceRef`; the runner verifies it
against the stored start request and reads the effective workspace from the
stored run result. A resume request must not silently switch to a different
workspace.

Accepted commits remain on the run-owned branch until a human or authorized
deployment workflow merges, publishes, or deletes them. The runner should not
remove the isolated worktree automatically while the run is awaiting review,
approval, or resume.

# Resume Contract

`WorkflowRunRequest` starts a run. `WorkflowResumeRequest` continues a run.

A resume request is required when `approvalMode: manual` pauses a
`loop-engineering` run with `awaiting_plan_approval`. It names:

- The paused `runId`.
- The same `moduleId`.
- The same local artifact directory.
- The `driverRef` used to continue execution.
- The approval actor and decision.
- The SHA-256 digest of the exact plan artifact being approved.

The runner must verify the plan artifact digest before executing approved
tasks. Rejection records an approval artifact and leaves the run blocked.

# Deprecated MCP Entry Point

The starter MCP server is a legacy optional adapter surface. It is not required
to operate the framework and should not receive new default-route features.

If retained temporarily, it must stay a thin stdio JSON-RPC wrapper for:

- Listing workflow modules.
- Validating a `WorkflowRunRequest` document.
- Starting a workflow through the same runner API as direct Python callers.
- Inspecting a local run artifact directory.
- Resuming an approved manual plan through `WorkflowResumeRequest`.
- Inspecting AWKP task state, manifests, events, and acceptance criteria.
- Evaluating AWKP task completion through EvidenceGate.

MCP tools must validate inputs, resolve the workflow module registry first,
resolve `driverRef` through `AgentDriverRegistry` for workflow runs, and then
call the same underlying Python APIs as direct callers. MCP does not own
workflow logic and must not bypass EvidenceGate expected-version or verifier
separation checks.

The preferred route is CLI plus Skill.

# Agent Operation

An agent should prefer this order:

1. Load the local AHRA workflow-runner skill.
2. Validate the request schema.
3. Load workflow modules.
4. Resolve driver adapters.
5. Start or resume through `uv run ahra workflow start` or
   `uv run ahra workflow resume`.
6. When a task is in review, inspect AWKP task state and invoke EvidenceGate
   with a verifier report.
7. Report factual run status and artifact/evidence locations.

The launch agent remains an operator. It is not automatically the driver
unless a driver adapter explicitly represents it.
