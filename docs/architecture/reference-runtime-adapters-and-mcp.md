---
type: Architecture
id: ARCH-reference-runtime-adapters-mcp
schema_version: awkp/0.1
title: Reference runtime adapters and removed MCP trace
description: Defines the Codex Python SDK driver adapter, local runtime profile, workflow resume contract, and the historical MCP surface that has now been removed.
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

The local AHRA MCP server has been removed. Historical MCP references are trace
only and do not describe a live operation surface.

# Codex SDK Driver

The first concrete non-fixture local driver is `CodexSDKDriver`.

It is an adapter, not a workflow module and not AHRA core. It must:

- Implement `src/ahra/ports.py::AgentDriver`.
- Accept role-specific `AgentRunRequest` values.
- Ask Codex for structured JSON matching the expected reference-runner output
  type.
- Bind the Codex session to the run-owned execution workspace.
- Parse JSON into `WorkReport`, `ReviewResult`, `GoalReviewResult`, or
  `NextStepDecision`.
- Fail closed when the SDK package, workspace binding, local account setup, or
  response shape is invalid.

The adapter must not:

- Import into AHRA domain objects.
- Write credentials into prompts, artifacts, evidence, memory, or snapshots.
- Add Codex-specific fields to workflow module descriptors.
- Become the only valid driver path.

User-owned Codex account and login setup stay outside the template. The
adapter only consumes the SDK available in the user's environment. If the SDK
is not installed or the user's account is not authenticated, the workflow must
surface that failure and stop; it must not silently fall back to a different
driver.

The starter does not provide a separate command-line fallback driver.
`codex-python-sdk` is the only built-in non-fixture Codex driver reference.

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

The caller may include `schedulerDecision` in the run request. The reference
runner stores that decision as `scheduler-decision.json` and applies its
execution policy to bounded Agent phases. Long-running Agent work is allowed,
but the runner emits heartbeat events and converts idle, attempt-wall-timeout,
or run-deadline exhaustion into terminal failed results with failure evidence.
For formal AWKP task runs, exhausted terminal failures are also published back
to the task-local artifact/evidence manifests with a handoff and a `review`
state, leaving completion or retry judgment to the user or an independent
verifier.

For the local profile, check execution may adapt bare `python ...` verification
commands to the project environment with `uv run python -B ...` when the
workspace has a `pyproject.toml` and `uv` is available. This preserves the
task's verification intent while avoiding host-level Python launcher drift.

Creating the isolated worktree does not require the source checkout to be
clean. The isolated workspace is created from the selected base commit, so
uncommitted source checkout changes are not part of the execution input.
Fast-forwarding accepted results back into the source checkout still requires
the source checkout to be clean; otherwise integration must fail closed instead
of overwriting local work.

Manual resume continues the same isolated worktree that the paused run used.
The caller still provides the original `workspaceRef`; the runner verifies it
against the stored start request and reads the effective workspace from the
stored run result. A resume request must not silently switch to a different
workspace.

Standalone fixture or exploratory runs may leave accepted commits on the
run-owned branch until a human or authorized workflow acts on them.

Formal AWKP task runs are different. When `workspaceRef` contains
`work/tasks/<TASK-ID>` for the requested task, the reference runner must treat
the run as authoritative local workflow execution: it preflights task state,
dependency completion, and active lease absence; executes inside a run-owned
worktree; publishes workflow evidence and a handoff back to the task; moves the
task to `review`; and fast-forwards the source workspace to the accepted run
branch. It still must not mark the AWKP task `completed`; completion remains an
EvidenceGate verifier decision.

The runner should not remove the isolated worktree automatically while the run
is awaiting review, approval, or resume.

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

# Removed MCP Entry Point

The starter MCP server implementation has been deleted. It is no longer a
legacy optional adapter surface in this repository. Historical ADRs and task
evidence may mention the old stdio wrapper, but those references are trace-only.

The current operation route is Mode C plus Goal CLI plus Skill.

# Legacy Agent Operation

For the current default path, use `framework-entrypoints.md` and
`skills/ahra-dynamic-kernel/SKILL.md`.

For an explicit legacy workflow compatibility request, an agent should use this
order:

1. Load the local AHRA workflow-runner skill.
2. Validate the request schema.
3. Load workflow modules.
4. Resolve driver adapters.
5. Start or resume through the hidden legacy workflow compatibility CLI group.
6. When a task is in review, inspect AWKP task state and invoke EvidenceGate
   with a verifier report.
7. Report factual run status and artifact/evidence locations.

The launch agent remains an operator. It is not automatically the driver
unless a driver adapter explicitly represents it.
