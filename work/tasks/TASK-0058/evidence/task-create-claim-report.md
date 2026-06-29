---
type: Evidence
id: EVD-TASK-0058-0001
schema_version: awkp/0.1
title: TASK-0058 task create and claim CLI report
description: Producer evidence for governed ahra task create and ahra task claim commands.
status: active
owner: agent:codex-implementation
created_at: 2026-06-29T15:15:09Z
source_refs: [../task.md, ../state.json, ../../../src/ahra/cli.py, ../../../src/ahra/awkp_task_creator.py, ../../../src/ahra/awkp_state_writer.py, ../../../tests/test_cli.py]
---

# Summary

TASK-0058 adds governed CLI commands for AWKP task creation and claiming:

- `ahra task create`: writes a lint-clean AWKP task skeleton with task.md, ready state, seeded task_created event, empty manifests, and evidence/handoffs directories.
- `ahra task claim`: moves a ready task to working through the TASK-0057 CAS writer and records a lease with a fencing token.

# Generated Skeleton

`ahra task create` requires the task id, title, description, context id, and at least one explicit `--acceptance` value. It does not invent acceptance criteria.

The generated task directory includes:

- `task.md` with WorkItem frontmatter and a parseable `# Acceptance criteria` section.
- `state.json` with `state=ready`, `state_version=0`, no lease, and empty artifact/evidence refs.
- `events.jsonl` seeded with one `task_created` event and a unique idempotency key.
- `artifact-manifest.json` and `evidence-manifest.json` with empty record arrays.
- `evidence/` and `handoffs/` directories.

# Claim Path

`ahra task claim` requires `--expected-version` and `--actor`, then delegates to `AwkpTaskStateWriter.acquire_working`. The TASK-0058 producer used this command to claim TASK-0058 itself, producing event `EVT-TASK-0058-0002` and fencing token `FENCE-ef04a184f15c4ee6828178d0ed88aa5a`.

# Fail-Closed Validation

Malformed task ids are rejected before writing a task directory. Missing acceptance criteria are rejected with a clear structured CLI error. The CLI tests cover both paths.

# Default Exposure

The default CLI help now exposes `task create` and `task claim` through the default `task` command group while preserving the existing checks that hide default-excluded legacy tokens.
