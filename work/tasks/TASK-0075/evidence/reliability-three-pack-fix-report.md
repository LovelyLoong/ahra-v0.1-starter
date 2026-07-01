---
type: Evidence
id: EVD-TASK-0075-0001
schema_version: awkp/0.1
title: Reliability three-pack fix report
description: Producer evidence report for TASK-0075 reliability defect repairs.
task_id: TASK-0075
owner: agent:codex
status: review
created_by: agent:codex
created_at: 2026-07-01T07:35:00Z
---

# Summary

TASK-0075 repairs the three reliability defects from the dogfood run without changing verification semantics or scheduler retry semantics.

# P2 Gate NoneType

Root cause: `VerificationExecutionReport.passed` and `gate_execution_integrity` called `len(self.selection.selected_gate_refs)`. A malformed or external `VerificationSelection` could carry `None`, triggering `TypeError` during gate evaluation or report serialization.

Fix:

- `VerificationSelection.__post_init__` normalizes all tuple fields from missing/`None` to `()`.
- `VerificationExecutionReport` defensively treats `selection.selected_gate_refs` as empty when missing.

Regression: `tests.test_verification.VerificationSelectionTests.test_execution_report_treats_none_selected_gate_refs_as_empty`.

# P3 Over-Retry

Root cause: the scheduler's `_maybe_retry` already respected `node.retry_policy.max_attempts`; the second attempt came from the bounded-task internal `TaskHarness` loop. `_execution_policy_for_node` passed timeouts into `TaskHarness` but did not cap `ExecutionPolicy.max_attempts` from `node.retry_policy.max_attempts`. A node with `retryPolicy.maxAttempts: 1` could still run twice because `TaskSpec.max_attempts` defaults to 2.

Fix:

- `src/ahra/reference_runner/bounded_task.py` caps `ExecutionPolicy.max_attempts` to `node.retry_policy.max_attempts` before invoking `TaskHarness`.

Regression: `tests.test_node_executor.NodeExecutorTests.test_bounded_task_honors_node_retry_policy_max_attempts_one`.

# P4 Encoding And SQLite Store Path

Root cause:

- `git_ops.py` and `runtime.py` used `subprocess.run(..., text=True, capture_output=True)` without explicit encoding/error policy, so Windows locale decoding could raise `UnicodeDecodeError`.
- SQLite connect/migration errors could surface as bare `sqlite3.OperationalError` or OS errors on invalid/missing parent paths.

Fix:

- `src/ahra/reference_runner/git_ops.py` and `src/ahra/reference_runner/runtime.py` now pass `encoding="utf-8"` and `errors="replace"`.
- `runtime.py` timeout byte decoding also uses UTF-8 replacement.
- `sqlite_control_store.py` wraps connect/migration open failures in `SQLiteControlStoreError` with database and parent path.
- `goal_operations.py` maps `SQLiteControlStoreError` to structured `GoalOperationError("sqlite_control_store_unavailable")`.

Regressions:

- `tests.test_reference_runner.ReferenceRunnerSubprocessTests.test_git_helpers_request_utf8_replace_decoding`.
- `tests.test_reference_runner.ReferenceRunnerSubprocessTests.test_local_runtime_replaces_invalid_utf8_output`.
- `tests.test_sqlite_control_store.SQLiteControlStoreTests.test_nested_store_path_creates_parent_directory`.
- `tests.test_sqlite_control_store.SQLiteControlStoreTests.test_invalid_store_parent_fails_with_structured_error`.

# Verification

- `uv run python -B -m unittest tests.test_verification tests.test_plan_execution -v` passed.
- `uv run python -B -m unittest tests.test_node_executor tests.test_reference_runner -v` passed.
- `uv run python -B -m unittest tests.test_sqlite_control_store tests.test_goal_operations -v` passed.
- `uv run python -B scripts/check.py` passed: 291 tests passed, 1 Windows symlink skip.
- `git diff --check` passed.

Producer did not mark TASK-0075 completed. EvidenceGate remains the completion authority.
