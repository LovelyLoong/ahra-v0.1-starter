---
type: WorkItem
id: TASK-0075
schema_version: awkp/0.1
title: Fix dogfood reliability three-pack - gate NoneType, over-retry, subprocess encoding and store path
description: Repair the three reliability defects that surfaced in the third dogfood run after the isolation fix - the deterministic gate NoneType len() crash, an extra attempt that ignored retryPolicy.maxAttempts, and the Windows GBK subprocess decode failure plus the SQLite control-store open failure.
context_id: CTX-workflow-b-reliability
priority: P1
risk_level: R2
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-07-01T00:00:00Z
depends_on: [TASK-0074]
input_refs:
  - ../../../src/ahra/verification.py
  - ../../../src/ahra/plan_execution.py
  - ../../../src/ahra/reference_runner/git_ops.py
  - ../../../src/ahra/reference_runner/runtime.py
  - ../../../src/ahra/reference_runner/bounded_task.py
  - ../../../src/ahra/goal_operations.py
  - ../../../work/tasks/TASK-0074/task.md
  - ../../../.claude/projects/E--ahra-v0-1-starter/memory/first-dogfood-run-lease-timeout-defect.md
output_contract:
  - kind: reliability_three_pack_fix
  - kind: verification_summary
  - kind: handoff
---

# Goal

Repair the three reliability defects that surfaced in the third dogfood run
(the run that first got real Agent code written before failing). These are the
defects that remain after TASK-0074 removes the destructive workspace-reset
root cause. Each is independent and objectively testable. TASK-0074 (isolation)
must land first so this task is verified in a safe workspace.

# Background (observed in the third dogfood run)

The third dogfood run crossed the 300s wall (TASK-0072/0073 fix held), and a
real Agent produced `src/ahra/alignment_session.py` (~39963 bytes) and
`tests/test_alignment_session.py` (~6324 bytes) at ~374s. It then failed with a
chain of three distinct defects, all separate from the TASK-0074 reset problem:

- P2: deterministic gate raised `TypeError("object of type 'NoneType' has no len()")`.
- P3: a second attempt started even though the node's `retryPolicy.maxAttempts` was 1.
- P4: `stderr` showed a Windows GBK `UnicodeDecodeError`, and the final CLI JSON
  was `OperationalError('unable to open database file')`.

# Verified code facts (confirm before editing; do not assume)

- P2: `src/ahra/verification.py:186` and `:197` call `len(self.selection.selected_gate_refs)`.
  The crash means a `VerificationSelection` (or its `selected_gate_refs`) was
  `None` on some path. Find the exact producer that passed `None` rather than an
  empty tuple, and fix at the source plus defend the len() sites.
- P3: `src/ahra/plan_execution.py:2039` `_maybe_retry` ALREADY checks
  `failed.attempt >= node.retry_policy.max_attempts` and returns early. So the
  scheduler path already honors maxAttempts. The extra attempt therefore comes
  from a DIFFERENT layer - most likely the executor/TaskHarness internal retry
  loop inside the bounded_task path, or a retry triggered as a side effect of
  the P2 crash. The fix must first identify the true source, then make it honor
  the node's `retryPolicy.maxAttempts`. Do NOT assume `_maybe_retry` is the bug.
- P4: `src/ahra/reference_runner/git_ops.py:25,44` and `runtime.py:25` call
  `subprocess.run(..., text=True, capture_output=True)` with no `encoding`, so
  on Windows they decode as GBK and crash on non-GBK bytes. The SQLite
  `unable to open database file` in the third run was a downstream effect of the
  TASK-0074 reset (store dir removed); after 0074 it should not recur, but the
  store-path resolution must still be robust to a relative store path and a
  missing parent directory.

# Scope

- P2: ensure `VerificationSelection.selected_gate_refs` is never `None` at its
  source; make the `len()` sites in `verification.py` treat missing/None as an
  empty selection instead of crashing.
- P3: locate the layer that started attempt 2 despite `maxAttempts: 1`, and make
  it honor the node retry policy; add a regression test proving a
  `maxAttempts: 1` node runs exactly one attempt on failure.
- P4: pass `encoding="utf-8"` (and `errors="replace"`) to the subprocess calls
  in `git_ops.py` and `runtime.py`; ensure the SQLite control store parent
  directory is created (or a clear error is raised) when the store path is
  relative or its parent is missing.
- Preserve all TASK-0072/0073 lease/timeout behavior and TASK-0074 isolation.

# Non-goals

- Do not re-run the paid real-Agent dogfood as part of this task; a deterministic
  regression is sufficient. The real dogfood re-run is a separate step after
  both TASK-0074 and TASK-0075 land and are committed.
- Do not change verification semantics beyond null-safety.
- Do not weaken retry safety to paper over P3; the fix is to honor maxAttempts,
  not to disable retries globally.
- Do not self-complete; EvidenceGate decides completion.

# Acceptance criteria

- [ ] P2 fixed: a verification/gate path that previously received a `None`
  selection now treats it as an empty selection and does not raise; a unit test
  reproduces the old `NoneType` len() condition and asserts it no longer crashes.
- [ ] P3 root cause identified and fixed at the true layer (documented in the
  report); a regression test proves a node with `retryPolicy.maxAttempts: 1`
  executes exactly one attempt on failure and does not start a second.
- [ ] P4a fixed: the `subprocess.run` calls in `git_ops.py` and `runtime.py`
  pass explicit `encoding="utf-8"` with `errors="replace"`; a test asserts
  non-GBK/UTF-8 bytes in git/command output no longer raise `UnicodeDecodeError`.
- [ ] P4b fixed: opening the SQLite control store with a relative path whose
  parent does not yet exist either creates the parent or fails with a clear,
  structured error (not a bare `OperationalError`); covered by a test.
- [ ] TASK-0072/0073 lease/timeout invariants and TASK-0074 isolation still hold
  (no regression in their tests).
- [ ] `python scripts/check.py` (full lint + tests) passes; new regression tests
  are non-skipped.
- [ ] Producer moves TASK-0075 only to review; EvidenceGate decides completion.

# Verification method

- .\.venv\Scripts\python.exe -B -m unittest tests.test_verification tests.test_plan_execution -v
- .\.venv\Scripts\python.exe -B -m unittest tests.test_node_executor tests.test_reference_runner -v
- .\.venv\Scripts\python.exe -B scripts\check.py
- git diff --check

# Required evidence and handoff

- Publish `evidence/reliability-three-pack-fix-report.md` documenting each of
  P2/P3/P4 with the exact root cause, the code location changed, and the test
  that proves the fix. For P3, state explicitly which layer started attempt 2.
- Publish `evidence/verification-summary.json`.
- Publish `handoffs/HANDOFF-0001.md` whose single next action is: after both
  TASK-0074 and TASK-0075 are committed, re-run the dogfood in the isolated
  worktree with the development-bounded budget.
