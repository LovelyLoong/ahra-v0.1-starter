---
type: Handoff
id: HANDOFF-TASK-0009-0001
schema_version: awkp/0.1
title: TASK-0009 runtime and entrypoint alignment handoff
description: Producer handoff for independent verification of local worktree isolation and entrypoint decisions.
status: active
owner: agent:codex
---

# Goal

Resolve the pending local runtime sandbox alignment and record the agreed
framework operation route.

# Completed

- Selected run-owned Git worktree isolation as the starter's default local
  boundary.
- Explicitly recorded that this does not provide process, network, host, or
  secret isolation.
- Added `docs/architecture/framework-entrypoints.md` as the default entrypoint
  authority.
- Updated roadmap, invocation docs, reference runtime docs, README, and the
  local workflow-runner Skill so the default route is Skill plus docs now and
  CLI plus Skill next.
- Deprecated MCP as a default starter route without removing code in this
  task.
- Created TASK-0014 as the next focused implementation task for CLI plus Skill
  operation and example separation.
- Updated TASK-0010 to wait for TASK-0014.

# Verification

- `uv run python -B scripts/check.py`: passed.
- `uv run python -B scripts/lint_awkp.py`: passed.
- `git diff --check`: passed.

# Artifacts

- Implementation report: `evidence/runtime-entrypoint-alignment-report.json`

# Next Action

Run independent verifier review for TASK-0009. If accepted, use EvidenceGate to
complete TASK-0009, then claim TASK-0014 for CLI plus Skill entrypoint
implementation.

# Notes

The existing MCP tests still pass because this task changed the default
architecture route, not the code surface. Actual MCP removal or quarantine is
assigned to TASK-0014.
