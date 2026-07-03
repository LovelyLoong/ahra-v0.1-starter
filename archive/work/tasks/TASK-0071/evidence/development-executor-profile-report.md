---
type: Evidence
id: EVD-TASK-0071-0001
schema_version: awkp/0.1
title: TASK-0071 development executor profile report
description: Development bounded profile implementation summary for independent EvidenceGate review.
status: ready_for_review
owner: agent:codex-implementation
task_id: TASK-0071
created_at: 2026-06-30T12:00:00.000002Z
created_by: agent:codex-implementation
---

# Development Executor Profile Report

TASK-0071 adds `profile/development-bounded` as a guarded GoalOperationProfile for real development execution.

## Profile

- Profile ref: `profile/development-bounded`
- Planner: `INLINE_PLANNER_REF`
- Executor: `REAL_BOUNDED_EXECUTOR_REF`
- Gate runner: `DETERMINISTIC_GATE_RUNNER_REF`
- Runtime/store: local worktree plus local SQLite
- Budget: `maxModelCalls=10`, `maxToolCalls=50`, `maxSpawnedNodes=0`, `maxWallSeconds=300`, `maxCostUsd=1.0`

The profile stays explicit opt-in. `ahra goal start --allow-development-agent` constructs `GoalOperationService(real_executor_driver=CodexSDKDriver())`; the default service path remains unchanged.

## Filesystem Boundary

The development profile grants `filesystem.write` for A-workflow development paths:

- `alignment_*.py`, `intent_*.py`, `request_*.py`
- `src/ahra/alignment_*.py`, `src/ahra/intent_*.py`, `src/ahra/request_*.py`
- `contracts/schemas/**`
- `tests/test_alignment_*.py`, `tests/test_intent_*.py`, `tests/test_request_*.py`
- `docs/architecture/intent-*`
- `examples/intents/**`

The profile denies B-kernel trusted files even when a request tries to include them:

- `evidence_gate.py`
- `capabilities.py`
- `verification.py`
- `goal_operations.py`
- `sqlite_control_store.py`
- `ports.py`
- `awkp_state_writer.py`
- matching `src/ahra/<name>` forms

`CapabilityGrant` now carries optional `deniedResources`; `LocalRuntimeGateway.authorize_write_path()` and `write_text()` reject matching paths with `path_blacklisted` and emit an audit record. `BoundedTaskExecutor` also performs a literal declared-write preflight for grants carrying denied resources, so blacklisted literal node requests fail before invoking the AgentDriver.

This is not claimed as OS-level sandbox containment. It is a local AHRA reference-monitor boundary for declared capability grants, gateway writes, literal request preflight, and post-run changed-file policy checks.

## Process Execution

The profile grants `process.exec` for project verification commands:

- `uv run python -B scripts/check.py`
- `uv run python -B scripts/check.py --lint`
- `uv run python -B scripts/check.py --test`
- `uv run python -B scripts/lint_awkp.py`
- `uv run python -B scripts/lint_*.py`

`BoundedTaskExecutor` turns checkable script commands into deterministic checks only for the explicit verification script family. Legacy compatibility commands such as inline `python -c ...` checks remain governed by the existing TaskHarness path and are not lossy-split into new command checks.

## Coverage

Tests added or updated:

- `tests.test_goal_operations.GoalOperationCliTests.test_development_bounded_profile_is_registered_with_guardrails`
- `tests.test_goal_operations.GoalOperationCliTests.test_development_profile_runs_whitelisted_write_and_process_check`
- `tests.test_goal_operations.GoalOperationCliTests.test_development_profile_rejects_blacklisted_literal_write_preflight`
- `tests.test_capabilities.LocalRuntimeGatewayTests.test_blacklisted_write_path_is_rejected_with_audit_record`
- `tests.test_cli.CliTests.test_goal_start_allow_development_agent_injects_codex_driver`

The domain profile definition remains in `src/ahra/goal_operations.py` and does not import the Codex SDK. The SDK adapter import is isolated to the CLI opt-in construction path.
