---
type: Evidence
id: EVD-TASK-0085-0001
schema_version: awkp/0.1
task_id: TASK-0085
kind: loop_defect_record
title: TASK-0085 bootstrap defect record
description: Manual-path bootstrap defect record per Increment F rule - Workflow B cannot edit its own kernel boundary
owner: manual-implementation:maintainer
status: final
created_by: manual-implementation:maintainer
created_at: 2026-07-01T10:00:00Z
---

# TASK-0085 Bootstrap Defect Evidence

## Task ID
TASK-0085

## Evidence Type
Loop defect record per Increment F rule

## Summary
TASK-0085 was executed on the manual path rather than through Workflow B, as Workflow B is structurally forbidden from editing its own kernel boundary (capability admission and write scope determination). This is the single bootstrap exception recorded for the self-hosting loop.

## Defect Classification
- **Type**: Structural limitation (not a bug)
- **Severity**: Expected bootstrap exception
- **Resolution**: One-time manual implementation required to enable future self-hosting

## Implementation Details

### Changes Made

1. **Extended hardened kernel blacklist** (`src/ahra/goal_operations.py:92-111`)
   - Added `scripts/**`, `pyproject.toml`, `uv.lock`, `Makefile`, `.github/**` to the blacklist
   - These infrastructure files are now protected alongside kernel modules

2. **Request-scoped write admission** (`src/ahra/goal_operations.py:1709-1743`)
   - Modified `_capability_admission_service` to derive effective `filesystem.write` allowlist from planDraft capability requests for `development-bounded` profile
   - Blacklist remains enforced as `denied_write_paths` in the runtime profile

3. **Request-scoped workspace provider** (`src/ahra/goal_operations.py:968-991`)
   - Modified `_real_executor_workspace_provider` to pass request-derived allowlist to `IsolatedGitWorkspaceProvider` instead of fixed profile allowlist

4. **Deletion and rename propagation** (`src/ahra/reference_runner/git_ops.py:154-177, 336-373`)
   - Added `deleted_files()` helper function using `git ls-tree` / `git ls-files` comparison
   - Updated `IsolatedGitWorkspaceProvider.commit_all()` to propagate deletions from worktree to source repository
   - Both modifications and deletions now respect the request-scoped allowlist

### Test Coverage

New test file: `tests/test_task_0085_request_scoped_write.py`

- **RequestScopedWriteAdmissionTests**: Verifies effective allowlist derived from planDraft
- **KernelBlacklistTests**: Verifies kernel modules and infrastructure files are rejected at runtime via `denied_resources`
- **IsolatedWorkspaceDeletePropagationTests**: Verifies deletion and rename propagation respects allowlist

All tests pass (5/5).

### Validation

All example goal files validate successfully:
- `examples/goals/task-0086-workflow-a-start-workspace.yaml` ✓
- `examples/goals/task-0087-codex-alignment-outputs.yaml` ✓
- `examples/goals/task-0088-workflow-a-turn-timeout.yaml` ✓
- `examples/goals/task-0089-entropy-archive.yaml` ✓

Full test suite: 323 tests passed, 1 skipped.

## Justification for Manual Path

Workflow B cannot edit the capability admission boundary because:
1. The capability admission service itself (`src/ahra/capabilities.py`) is in the kernel blacklist
2. The goal operations module (`src/ahra/goal_operations.py`) that determines write scope is also blacklisted
3. This creates a structural chicken-and-egg: Workflow B cannot modify the code that determines its own write permissions

This is the intended design - the capability kernel must be modified through a governed manual path to prevent self-modifying permission escalation.

## Post-Bootstrap State

After TASK-0085:
- Future tasks in the self-hosting loop (TASK-0086 through TASK-0089) CAN be executed by Workflow B alone
- Each task declares its specific `filesystem.write` resources in its GoalExecutionRequest planDraft
- The capability admission service derives the effective allowlist from those declarations
- The hardened kernel blacklist prevents any task from modifying the kernel boundary itself

## Actor
manual-implementation:maintainer

## Timestamp
2026-07-01T10:00:00Z

## References
- `work/tasks/TASK-0085/task.md`
- `docs/roadmaps/development-program-overview.md` (Increment F rule)
- Acceptance criteria: All satisfied ✓
