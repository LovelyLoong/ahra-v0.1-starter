---
type: WorkItem
id: TASK-0074
schema_version: awkp/0.1
title: Isolate the development executor in a throwaway git worktree
description: Fix the safety-critical P1 defect from the first real dogfood run - the development-bounded real Agent ran directly in the main repository working tree and executed git reset --hard plus git clean -fd, destroying uncommitted work (including TASK-0072 and TASK-0073). Run the Agent in an isolated git worktree so agent-initiated git or filesystem actions cannot damage the main tree.
context_id: CTX-workflow-b-reliability
priority: P0
risk_level: R3
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-07-01T04:00:00.000000Z
depends_on: [TASK-0071, TASK-0072, TASK-0073]
input_refs:
  - ../../../src/ahra/reference_runner/bounded_task.py
  - ../../../src/ahra/reference_runner/git_ops.py
  - ../../../src/ahra/goal_operations.py
  - ../../../src/ahra/ports.py
  - ../../../work/tasks/TASK-0071/task.md
output_contract:
  - kind: development_worktree_isolation_change
  - kind: verification_summary
  - kind: handoff
---

# Goal

The development-bounded profile must run the real Agent inside an isolated,
throwaway git worktree (or equivalent isolated copy), never in the main
repository working tree. Even if the Agent runs `git reset --hard`,
`git clean -fd`, or writes arbitrary files, the main repository working tree and
its uncommitted changes must remain intact.

This fixes the P1 defect that destroyed TASK-0072 and TASK-0073 during the first
real dogfood run.

# Background

First real dogfood run (`goal start ... --allow-development-agent`) facts:

- `bounded_task.py:124` defaults to `LocalGitWorkspaceProvider()`; `:153` calls
  `resolve_path(request.workspace_ref)`, which only resolves the path. When the
  dogfood request pointed the workspace at the repository root, the real Agent
  operated directly in the main tree.
- The real Agent (codex) has shell access and, to "tidy" the tree, ran
  `git reset --hard` + `git clean -fd`. Framework code did not call rollback in
  the bounded_task path; the Agent did it itself.
- Result: all uncommitted work was wiped, including the completed but uncommitted
  TASK-0072 and TASK-0073 code and task records. `git reset --hard` on
  uncommitted changes is unrecoverable; they had to be rebuilt.
- The `filesystem.write` allowlist/blacklist from TASK-0071 cannot stop this: it
  governs `filesystem.write`, not git subcommands run via the Agent's shell.

`git_ops.py` already supports `worktree add` (`:115`) and `worktree remove`
(`:131`); this task should reuse that support rather than inventing new isolation.

# Scope

- Make the development-bounded execution path provision an isolated git worktree
  for the real Agent, distinct from the main repository working tree.
- After a run, materialize only allowlisted produced files back into the
  governed workspace through a controlled path (diff/patch or explicit
  allowlisted copy); do not propagate blacklisted or out-of-allowlist paths.
- Remove/clean up the throwaway worktree after the run, on both success and
  failure.
- Preserve the TASK-0071 filesystem.write allowlist/blacklist and the
  TASK-0072/0073 lease/timeout guarantees.

# Non-goals

- Do not change the M1 deterministic path's workspace behavior.
- Do not weaken capability admission, the write allowlist/blacklist, lease,
  timeout, or EvidenceGate boundaries.
- Do not attempt to sandbox the Agent's network or process access here (separate
  concern); this task is strictly about filesystem/git blast-radius isolation.
- Do not self-complete; EvidenceGate decides completion.

# Acceptance criteria

- [ ] The development-bounded execution path provisions an isolated git worktree
  whose resolved path is not the main repository working tree, and the real
  Agent's working directory is that isolated worktree. A unit test asserts the
  Agent workspace path differs from the main repo root.
- [ ] A fixture test simulates a hostile/careless Agent that runs
  `git reset --hard` and `git clean -fd` (or deletes/overwrites files) inside the
  isolated worktree, and asserts the main repository working tree and a seeded
  uncommitted file are left unchanged. This is the core safety guarantee.
- [ ] After a successful run, only allowlisted produced files are materialized
  back into the governed workspace; a test asserts a blacklisted or
  out-of-allowlist path produced in the worktree is not propagated.
- [ ] The throwaway worktree is removed after the run on both success and failure
  paths; a test asserts no leftover worktree remains.
- [ ] The M1 deterministic profile path is unaffected (regression test passes).
- [ ] `python scripts/check.py` (lint + full tests) passes, or blockers are
  recorded with exact command output.
- [ ] Producer moves TASK-0074 only to review; EvidenceGate decides completion.

# Verification method

- `.\.venv\Scripts\python.exe -B -m unittest tests.test_node_executor tests.test_goal_operations -v`
- New isolation test module, for example
  `.\.venv\Scripts\python.exe -B -m unittest tests.test_development_worktree_isolation -v`
- `.\.venv\Scripts\python.exe -B scripts\check.py`
- `git diff --check`

# Required evidence and handoff

- Publish `evidence/development-worktree-isolation-report.md` describing the
  isolation mechanism and the proven blast-radius containment.
- Publish `evidence/verification-summary.json`.
- Publish `handoffs/HANDOFF-0001.md` with one exact next action (expected: rerun
  the dogfood after TASK-0075 reliability fixes land).
