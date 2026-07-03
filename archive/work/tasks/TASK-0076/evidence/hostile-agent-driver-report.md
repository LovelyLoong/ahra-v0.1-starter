---
type: Evidence
id: EVD-TASK-0076-0002
schema_version: awkp/0.1
title: HostileAgentDriver adversarial replay adapter and free CI invariant suite
description: Producer evidence report for the HostileAgentDriver adapter and the consolidated D1-D5 free invariant regression suite.
task_id: TASK-0076
owner: agent:claude-code
status: review
created_by: agent:claude-code
created_at: 2026-07-01T09:05:00Z
---

# HostileAgentDriver — adversarial replay adapter and free CI invariant suite

## Summary

TASK-0076 adds `HostileAgentDriver`, a deterministic `AgentDriver` adapter that
replays the exact hostile/careless actions paid real-Agent dogfood runs have
already exposed, so the framework invariants proven by TASK-0071/0072/0073/
0074/0075 can be re-proven for free in `scripts/check.py` on every change. The
paid dogfood (`ahra goal start --allow-development-agent`) is now a pure
**capability** test — "can the real Agent produce a conformant artifact" — whose
failures give clean signal, while framework safety/reliability is owned by the
free HostileAgentDriver path.

## What was built

- `src/ahra/adapters/hostile_driver.py` — `HostileAgentDriver` implements the
  existing `AgentDriver` port (`src/ahra/ports.py`) and is exported from
  `src/ahra/adapters/__init__.py`. It is a **reference/test adapter**, not new
  domain infrastructure: it imports only stdlib + `ahra.ports` +
  `ahra.reference_runner.models`, so it obeys the non-negotiable "no domain code
  imports concrete cloud/model/Agent SDK" rule.
- It is **scenario-driven** via `HostileScenario` (`destructive_git`,
  `out_of_allowlist_write`, `fail`), so one driver covers all observed defects
  and future ones without code changes. It records every invocation on
  `invocations` so attempt-count invariants are assertable.
- It is registered under immutable-version refs (`HOSTILE_AGENT_DRIVER_REF`,
  `HOSTILE_AGENT_DRIVER_DESTRUCTIVE_GIT_REF`) following the same digest convention
  as other adapters. It is **opt-in only** and never on the default operation
  surface: the default development executor remains `REAL_BOUNDED_EXECUTOR_REF`.
- `tests/test_hostile_agent_driver.py` — the consolidated free invariant suite.

## Scenario set and which prior-task invariant each re-proves

### D1 — destructive git (re-proves TASK-0074 worktree isolation)
`HostileScenario.DESTRUCTIVE_GIT` runs `git reset --hard` + `git clean -fd`
inside the Agent workspace, then writes the allowlisted artifact. Driven through
`GoalOperationService`, the run **succeeds** and the allowlisted artifact is
materialized into the main workspace, while a seeded uncommitted sentinel file
in the main tree is left untouched and the throwaway worktree is removed. This
is the exact careless action that wiped uncommitted TASK-0072/0073 work when the
Agent ran in the main tree; under 0074 isolation it only damages the throwaway
worktree.
Test: `D1DestructiveGitIsolationTests.test_destructive_git_preserves_main_tree_and_materializes_allowlisted_artifact`.

### D2 — out-of-allowlist write (re-proves TASK-0071 write allowlist)
`HostileScenario.OUT_OF_ALLOWLIST_WRITE` writes the allowlisted artifact **and**
a blacklisted path (`src/ahra/evidence_gate.py`). The blacklisted write has no
`filesystem.write` capability grant, so the deterministic policy gate records a
violation and the run is rejected before any commit; the blacklisted path never
lands in the governed workspace. The main-tree sentinel survives. (The
`IsolatedGitWorkspaceProvider` materialization filter — the deny path of
`_is_materializable` — is additionally covered by TASK-0074's
`test_isolated_provider_materializes_only_allowlisted_files`.)
Test: `D2OutOfAllowlistWriteTests.test_blacklisted_write_is_not_propagated_into_main_workspace`.

### D3 — non-GBK subprocess (re-proves TASK-0075 P4)
`LocalRuntimeProvider.exec` is driven with a child process that emits bytes
(`\xff\xfe\x80`) that cannot decode as the Windows default (GBK). Because the
subprocess calls pin `encoding="utf-8", errors="replace"` (the 0075 P4 fix in
`src/ahra/reference_runner/runtime.py`; the same kwargs are used in
`git_ops.py`), no `UnicodeDecodeError` is raised and the readable prefix/suffix
survive. This is the free regression for the subprocess path that crashed in the
third dogfood run.
Test: `D3NonGbkSubprocessTests.test_local_runtime_exec_decodes_non_gbk_bytes_without_crashing`.

### D4 — retry past maxAttempts=1 (re-proves TASK-0075 P3)
`HostileScenario.FAIL` raises `RuntimeError` on every call. Driven through the
development bounded_task node (which declares `retryPolicy.maxAttempts: 1`), the
harness invokes the executor exactly once; the always-failing executor does not
start a second attempt. `len(driver.invocations) == 1`. This re-proves the 0075
P3 invariant at the TaskHarness layer (the bounded-task execution path), which
is the layer the third dogfood run's extra attempt came from.
Test: `D4MaxAttemptsTests.test_max_attempts_one_runs_exactly_one_attempt_on_failure`.

### D5 — None gate-selection at the wall (re-proves TASK-0075 P2)
A `VerificationSelection` with `selected_gate_refs=None` is constructed and
wrapped in a `VerificationExecutionReport`; `.passed`, `.gate_execution_integrity`,
and `.to_dict()` must not raise `TypeError: object of type 'NoneType' has no
len()`. This is the free regression for the gate path that crashed in the third
dogfood run (the 0075 P2 null-safety fix in `verification.py:186,198`).
Test: `D5NoneGateSelectionTests.test_none_selected_gate_refs_treated_as_empty`.

## Why the paid dogfood is now a pure capability test

Before TASK-0076, each new class of framework defect was discovered mid-run
during a paid real-Agent dogfood, and the first was destructive. The
HostileAgentDriver suite now owns every framework invariant the dogfood has
exposed, for free, in CI. With this suite green, a paid dogfood re-run can only
fail for **Agent capability** reasons (the real Agent failed to produce a
conformant artifact), not for framework reliability reasons whose regression is
already pinned here. This is the documented dogfood precondition recorded in the
handoff.

## Opt-in / no-regression guarantees

- `HostileAgentDriver` satisfies the `@runtime_checkable` `AgentDriver` protocol
  and round-trips through `AgentDriverRegistry`.
- It is not the default development executor
  (`REAL_BOUNDED_EXECUTOR_REF`), and a fresh `AgentDriverRegistry()` does not
  contain the hostile ref.
- The M1 deterministic path and the real development-bounded path are
  unaffected: `scripts/check.py` (lint + full tests) passes with 299 tests
  passing, 1 skipped; `git diff --check` clean.
- Producer did not mark TASK-0076 completed; EvidenceGate decides completion.
