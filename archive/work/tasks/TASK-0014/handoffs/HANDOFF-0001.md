---
type: Handoff
id: HANDOFF-TASK-0014-0001
schema_version: awkp/0.1
title: TASK-0014 CLI plus Skill entrypoint handoff
description: Producer handoff for independent verification of the CLI plus Skill operation entrypoint.
status: active
owner: agent:codex-cli-skill-operator
---

# Goal

Make CLI plus local Skill the default operation surface and remove MCP from
the default route.

# Completed

- Added `uv run ahra workflow validate/start/inspect/resume`.
- Added `uv run ahra task inspect`.
- Added `uv run ahra evidence-gate evaluate`.
- Added `uv run ahra doctor`.
- Updated the local workflow-runner Skill to use CLI commands.
- Kept MCP documented as legacy optional, not the default path.
- Split `examples/workflow_runs/fixtures/` from `examples/workflow_runs/runnable/`.
- Added CLI unit tests and updated schema/reference/lint paths.

# Verification

- `uv run python -B scripts/check.py`: passed, 51 tests.
- `uv run python -B scripts/lint_awkp.py`: passed.
- `git diff --check`: passed with CRLF normalization warnings only.
- `uv run ahra workflow validate examples\workflow_runs\fixtures\standard-task.yaml`: passed.
- `uv run ahra workflow validate examples\workflow_runs\runnable\standard-task-codex.yaml`: passed.
- `uv run ahra doctor --dry-run`: passed.

# Important Finding

Before implementation, a standard-harness preflight using `driverRef:
codex-python-sdk` was attempted through the direct runner API. It failed closed
because the optional Codex SDK package is not installed:

`CodexSDKDriver requires the optional 'codex' extra: pip install -e .[codex]`

So the framework now has the CLI operation surface, but a real local AgentDriver
must still be installed or provided before a non-fixture workflow can execute
real agent work.

# Next Action

Run independent verifier review for TASK-0014. If accepted, invoke
EvidenceGate with the implementation report and move the task to completed.
