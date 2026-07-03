---
type: Handoff
id: HANDOFF-TASK-0014-0003
schema_version: awkp/0.1
title: TASK-0014 live workflow verification handoff
description: Producer handoff after fixing reviewer workspace context and passing a real codex-cli standard-harness probe.
status: active
owner: agent:codex-cli-skill-operator
---

# TASK-0014 Handoff 0003

## Status

Ready for independent review. The standard Harness workflow now has a confirmed
real local route through `driverRef: codex-cli` on a clean source worktree.

## Additional Blocker Found And Fixed

A live probe after commit showed that task reviewer requests did not include
`workspace_ref`. Codex CLI therefore launched reviewer sessions without `--cd`
and the reviewer inspected the wrong directory. The runner now passes the
execution workspace to task reviewers, goal reviewers, and planners.

## Latest Verification

- `uv run python -B -m unittest tests.test_driver_requests tests.test_reference_runner tests.test_codex_cli_driver -v`: passed, 16 tests.
- `uv run python -B scripts/check.py`: passed, 57 tests.
- `uv run python -B scripts/lint_awkp.py`: passed.
- `git diff --check`: passed.
- `uv run ahra workflow start C:\Users\SkyUser\AppData\Local\Temp\RUN-codex-cli-clean-165552.yaml`: passed with `ok:true`, `status: accepted`.

## Live Probe Evidence

- Artifact: `.runtime/ahra-runs/probes/RUN-codex-cli-clean-165552`
- Base checkpoint: `c6a6e253b086cf0a9b53aabe90293d9fdb112f9c`
- Workflow branch: `ahra/ahra-reference-runner/RUN-d1f2164dd57e416ca175-fe044996`
- Workflow commit: `6fdb324072d43e8d21ae5ee36d8444244f715a11`

## Remaining Operational Limits

- Source worktree must be clean before starting a workflow run.
- Repeated examples need a unique or empty `artifactDir`.
- `codex-cli` requires the local Codex CLI to be installed and authenticated.
- Producer still cannot complete TASK-0014; independent review and EvidenceGate
  approval remain required.
