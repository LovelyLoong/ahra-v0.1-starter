---
type: Evidence
id: EVD-TASK-0074-0001
schema_version: awkp/0.1
title: Development worktree isolation report
description: Producer evidence report for development-bounded isolated worktree execution.
task_id: TASK-0074
owner: agent:codex
status: review
created_by: agent:codex
created_at: 2026-07-01T07:35:00Z
---

# Summary

TASK-0074 isolates the development-bounded real Agent executor from the maintainer's main working tree.

The development profile now uses `IsolatedGitWorkspaceProvider` for `profile/development-bounded` only. `GoalOperationService` creates a throwaway git worktree under the run artifact directory, passes that isolated path into the scheduler, and injects the same provider into `BoundedTaskExecutor`. The real Agent and `TaskHarness` therefore see the throwaway worktree, not the governed source workspace.

# Mechanism

- `src/ahra/reference_runner/git_ops.py` adds `IsolatedGitWorkspaceProvider`.
- `src/ahra/goal_operations.py` selects that provider only when `request.profile_ref == profile/development-bounded`.
- Successful `commit_all` materializes changed regular files from the throwaway worktree back to the governed workspace only when they match the profile allowlist and do not match the blacklist.
- `finalize_execution_workspace` removes the worktree and deletes the temporary branch on success and failure.
- M1 deterministic and non-development real executor paths keep their previous workspace provider behavior.

# Proven Blast Radius Containment

`tests/test_development_worktree_isolation.py` covers:

- the Agent receives a workspace path different from the main repository workspace;
- a hostile Agent can run `git reset --hard` and `git clean -fd` inside the isolated worktree without deleting a seeded uncommitted file in the main workspace;
- only allowlisted files are materialized back from an isolated worktree;
- denied and out-of-allowlist files are not copied back;
- temporary worktrees are removed after both success and failed executor paths.

# Verification

- `uv run python -B -m unittest tests.test_development_worktree_isolation -v` passed.
- `uv run python -B -m unittest tests.test_node_executor tests.test_goal_operations -v` passed.
- `uv run python -B scripts/check.py` passed: 291 tests passed, 1 Windows symlink skip.
- `git diff --check` passed.

Producer did not mark TASK-0074 completed. EvidenceGate remains the completion authority.
