---
type: Handoff
id: HANDOFF-TASK-0014-0002
schema_version: awkp/0.1
title: TASK-0014 real workflow usability handoff
description: Producer handoff for independent verification of the codex-cli workflow route and fail-closed fixes.
status: active
owner: agent:codex-cli-skill-operator
---

# TASK-0014 Handoff 0002

## Status

The task is ready for independent review again after the maintainer expanded
scope to include real workflow usability blockers.

## What changed after HANDOFF-0001

- Added `codex-cli` as a real local non-fixture `AgentDriver` route.
- Made CLI workflow `error`, `rejected`, and `blocked` terminal statuses fail
  closed instead of returning `ok:true`.
- Fixed generated worktree branch names so shared run-id prefixes do not
  collide.
- Added a clean-source guard before creating isolated worktrees. Dirty source
  repositories now fail closed because the runner would otherwise execute stale
  `HEAD`.
- Updated Skill/docs/examples to make `codex-cli` the default runnable local
  route and keep fixtures explicit.

## Verification already run

- `uv run python -B -m unittest tests.test_git_ops tests.test_codex_cli_driver tests.test_cli -v`
- `uv run python -B scripts/check.py`
- `uv run python -B scripts/lint_awkp.py`
- `git diff --check`
- `uv run ahra workflow validate examples\workflow_runs\runnable\standard-task-codex.yaml`
- `uv run ahra doctor --dry-run`
- `uv run ahra workflow start <temporary dirty-source probe>`
- `uv run ahra workflow start <temporary codex-cli probe request>`

## Review focus

- Confirm the CLI does not duplicate workflow logic and calls existing local
  APIs.
- Confirm `codex-cli` implements the `AgentDriver` port and is registered by
  CLI without MCP.
- Confirm workflow terminal failure states are exposed as CLI failures.
- Confirm dirty source worktrees are rejected before isolated runs.
- Confirm `fake-reference` is still fixture-only and gated by
  `--enable-fixture-driver`.
- Confirm docs and Skill no longer present MCP as the default operation path.

## Known limits

The current repository worktree is dirty, so new workflow runs against this
workspace correctly fail until the changes are committed or stashed. This is a
deliberate isolation rule, not an acceptance claim that the current dirty tree
can be executed directly.
