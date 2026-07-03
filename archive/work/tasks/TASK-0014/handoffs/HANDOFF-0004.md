---
type: Handoff
id: HANDOFF-TASK-0014-0004
schema_version: awkp/0.1
title: TASK-0014 Codex SDK correction handoff
description: Producer handoff after removing the separate command-line Codex route and restoring codex-python-sdk as the agreed default.
status: active
owner: agent:codex-sdk-correction-operator
---

# TASK-0014 Handoff 0004

## Status

Ready for independent review after correction. The active non-fixture Codex
driver reference is `codex-python-sdk`.

## Correction

The earlier command-line driver route was introduced without prior agreement.
It has been removed from active code, tests, docs, Skill guidance, and runnable
examples. Historical events and old evidence remain as audit records, but this
handoff and `implementation-report-4.json` supersede them.

## Verification Already Run

- `uv run python -B -m unittest tests.test_codex_driver tests.test_cli tests.test_driver_requests tests.test_git_ops -v`: passed, 14 tests.
- `uv run ahra workflow validate examples\workflow_runs\runnable\standard-task-codex.yaml`: passed with `driver_ref: codex-python-sdk`.
- `uv run --extra codex python -B -c "from openai_codex import AsyncCodex, CodexConfig; import inspect; print(inspect.signature(CodexConfig)); print(inspect.signature(AsyncCodex.thread_start))"`: passed.
- `uv run python -B scripts/check.py`: passed, 56 tests.
- `uv run python -B scripts/lint_awkp.py`: passed.
- `git diff --check`: passed.

## User Verification Commands

- `uv sync --extra codex`
- `uv run --extra codex python -B -c "from openai_codex import AsyncCodex; print('openai_codex ok')"`
- `uv run --extra codex ahra workflow start examples\workflow_runs\runnable\standard-task-codex.yaml`
- `uv run ahra workflow inspect .runtime\ahra-runs\runnable\codex-standard-task`

If the last command fails because the Codex account or authentication is not
ready, that is a user-environment setup blocker, not a reason to fall back to a
different driver.

## Review Focus

- Confirm no active code path registers a separate command-line Codex driver.
- Confirm active examples and Skill instructions use `codex-python-sdk`.
- Confirm SDK client binds `cwd` to the run-owned execution workspace.
- Confirm prior incorrect evidence is superseded, not treated as acceptance.
