---
type: WorkItem
id: TASK-0005
schema_version: awkp/0.1
title: Enforce reference runner workspace isolation and add cross-platform checks
description: Fix the review finding that the local reference runner could mutate the source workspace directly, and add a Windows-friendly check entrypoint.
context_id: CTX-ahra-runner-isolation
priority: P0
risk_level: R1
requester: human:maintainer
reviewer: agent:verifier
created_at: 2026-06-22T14:23:00Z
depends_on: [TASK-0004]
input_refs:
  - ../../../docs/architecture/reference-runtime-adapters-and-mcp.md
  - ../../../docs/architecture/workflow-modules.md
  - ../../../WORKFLOW.md
  - ../../../AGENTS.md
output_contract:
  - kind: architecture_update
  - kind: reference_runner_fix
  - kind: check_entrypoint
  - kind: verification_report
---

# Goal

Close the severe implementation gap where the reference runner could execute
workflow mutations against the source workspace named by `workspaceRef`.

# Scope

- Document that `workspaceRef` is the source workspace and that the local
  runner must execute in a run-owned isolated Git worktree.
- Make default `run_workflow()` materialize and record an isolated worktree
  before invoking `standard-harness` or `loop-engineering`.
- Make manual resume continue the stored effective workspace instead of
  silently switching workspaces.
- Expose the isolated workspace in MCP run inspection.
- Add a cross-platform `python scripts/check.py` verification entrypoint and
  keep `make check` as a wrapper where `make` exists.

# Non-goals

- Do not mark TASK-0002, TASK-0003, or TASK-0004 completed as part of this
  task.
- Do not mark TASK-0005 completed before independent verifier approval.
- Do not implement production cleanup/garbage collection for retained
  worktrees.
- Do not change the `WorkflowRunRequest` or `WorkflowResumeRequest` schema.

# Constraints

Preserve the existing provider-neutral contracts. Do not add provider SDKs to
domain code. Keep destructive Git rollback behavior confined to the effective
isolated workspace in the default local runner path.

# Acceptance criteria

- [x] Docs define local runner workspace isolation and resume workspace
      recovery.
- [x] Default `run_workflow()` creates a run-owned Git worktree and records it
      as an artifact.
- [x] Runner API tests prove source workspace contents stay unchanged while the
      isolated workspace receives the workflow mutations.
- [x] Manual `loop-engineering` resume continues the same isolated workspace.
- [x] MCP run inspection returns `workspace.json`.
- [x] `python scripts/check.py` runs the contract lint and unit tests on this
      Windows/PowerShell environment.
- [x] AWKP task state, events, artifact manifest, evidence manifest, and
      handoff exist.

# Verification method

- `python scripts\check.py`
- `python scripts\lint_awkp.py`
- `git diff --check`

# Risk and approvals

R1. This changes local reference runner execution behavior and must be reviewed
by an independent verifier before completion.
