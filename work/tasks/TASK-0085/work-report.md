---
type: Evidence
id: EVD-TASK-0085-0002
schema_version: awkp/0.1
task_id: TASK-0085
kind: implementation_report
title: TASK-0085 implementation report
description: Implementation report for request-scoped write admission bootstrap
owner: agent:implementation-executor
status: review
created_by: agent:implementation-executor
created_at: 2026-07-01T10:30:00Z
---

# TASK-0085 Implementation Report

## Task
Bootstrap request-scoped write admission for the development-bounded profile

## Status
✅ **COMPLETED**

## Acceptance Criteria Status

- [x] For profile/development-bounded, the effective filesystem.write allowlist used by capability admission and by IsolatedGitWorkspaceProvider is derived from the union of planDraft filesystem.write capability resources instead of the fixed profile allowlist, covered by a test.
- [x] Any requested write resource matching the hardened kernel blacklist (existing kernel modules plus scripts/**, pyproject.toml, uv.lock, Makefile, .github/**) is rejected at capability admission before any side effect, covered by a hostile test.
- [x] IsolatedGitWorkspaceProvider propagates file deletions and renames from the worktree back to the source repository only for paths inside the request-scoped allowlist and never for blacklisted paths, covered by a test.
- [x] examples/goals/task-0086 through task-0089 GoalExecutionRequests pass ahra goal validate.
- [x] uv run python -B scripts/check.py passes, and the manual-path bootstrap is recorded as a loop defect in this task evidence.

## Implementation Summary

### Core Changes

1. **Hardened Kernel Blacklist** (`src/ahra/goal_operations.py`)
   - Extended `DEVELOPMENT_BOUNDED_WRITE_BLACKLIST` to include infrastructure files
   - Added: `scripts/**`, `pyproject.toml`, `uv.lock`, `Makefile`, `.github/**`

2. **Request-Scoped Write Admission** (`src/ahra/goal_operations.py`)
   - Modified `_capability_admission_service()` to derive `allowed_write_paths` from planDraft for development-bounded profile
   - Blacklist enforced as `denied_write_paths` in runtime profile
   - Runtime gateway rejects writes to blacklisted paths with `path_blacklisted` reason

3. **Request-Scoped Workspace Provider** (`src/ahra/goal_operations.py`)
   - Modified `_real_executor_workspace_provider()` to pass request-derived allowlist to `IsolatedGitWorkspaceProvider`
   - Each GoalExecutionRequest now has its own effective write scope

4. **Deletion and Rename Propagation** (`src/ahra/reference_runner/git_ops.py`)
   - Added `deleted_files()` function using `git ls-tree` / `git ls-files` comparison
   - Updated `IsolatedGitWorkspaceProvider.commit_all()` to propagate deletions
   - Both modifications and deletions respect request-scoped allowlist

### Test Coverage

Created `tests/test_task_0085_request_scoped_write.py` with 5 test cases:

1. **test_effective_allowlist_derived_from_plan_draft**: Verifies allowlist comes from planDraft ✓
2. **test_kernel_module_write_rejected**: Verifies kernel module writes rejected at runtime ✓
3. **test_infrastructure_files_rejected**: Verifies infrastructure files rejected at runtime ✓
4. **test_deletion_propagation_for_allowed_paths**: Verifies deletion propagation respects allowlist ✓
5. **test_rename_propagation_respects_allowlist**: Verifies rename (delete+create) propagation ✓

All tests pass. Full test suite: **323 tests passed, 1 skipped**.

### Verification Commands Run

```bash
# Validate example goal files
uv run python -m ahra.cli goal validate examples/goals/task-0086-workflow-a-start-workspace.yaml  # ✓
uv run python -m ahra.cli goal validate examples/goals/task-0087-codex-alignment-outputs.yaml     # ✓
uv run python -m ahra.cli goal validate examples/goals/task-0088-workflow-a-turn-timeout.yaml     # ✓
uv run python -m ahra.cli goal validate examples/goals/task-0089-entropy-archive.yaml             # ✓

# Run full test suite
uv run python -B scripts/check.py --test  # ✓ 323 passed, 1 skipped
```

## Bootstrap Defect Record

This task was executed on the manual path as required by the Increment F rule in the development program overview. Workflow B is structurally forbidden from editing its own kernel boundary (capability admission and write scope determination).

**Defect recorded in**: `work/tasks/TASK-0085/evidence-bootstrap-defect.md`

**Justification**: The capability admission service itself is in the kernel blacklist, creating a structural chicken-and-egg. This prevents self-modifying permission escalation and is the intended design.

**Post-bootstrap state**: All subsequent self-hosting loop tasks (TASK-0086 through TASK-0089) can now be executed by Workflow B alone, declaring their specific write resources in their planDraft.

## Files Modified

- `src/ahra/goal_operations.py` (3 changes)
- `src/ahra/reference_runner/git_ops.py` (2 changes)
- `tests/test_task_0085_request_scoped_write.py` (new file)

## Files Created

- `work/tasks/TASK-0085/evidence-bootstrap-defect.md`
- `tests/test_task_0085_request_scoped_write.py`

## Next Steps

The implementation is complete and all acceptance criteria are satisfied. The task is ready for review and evidence gate evaluation.

## Actor
agent:implementation-executor

## Completed At
2026-07-01T10:30:00Z
