---
type: Handoff
id: HANDOFF-TASK-0004-0001
schema_version: awkp/0.1
title: Reference runtime adapters and MCP ready for verification
description: Handoff for independent review of optional Codex SDK adapter, WorkflowResumeRequest, and MCP entrypoint changes.
status: active
owner: agent:verifier
task_id: TASK-0004
from: agent:codex
to: agent:verifier
state: review
source_refs: [../task.md, ../state.json, ../artifact-manifest.json]
artifact_refs: [ART-TASK-0004-0001]
evidence_refs: [EVD-TASK-0004-0001]
confidence: tested
created_at: 2026-06-22T10:55:00Z
last_verified_at: 2026-06-22T10:55:00Z
review_after: 2026-09-22T00:00:00Z
tags: [handoff, adapter, mcp, resume]
---

# Goal and state

TASK-0004 is in `review`. The implementation agent has not marked the task
completed.

# Completed

- Added ADR-0006 and architecture documentation for reference runtime
  adapters, Codex SDK adapter, workflow resume, and MCP entrypoint.
- Added `WorkflowResumeRequest` schema and example.
- Added `resume_workflow()` with plan SHA-256 verification before execution.
- Added optional `CodexSDKDriver` behind the global `AgentDriver` port.
- Added `ahra-mcp` stdio entrypoint and tool handler tests.
- Added regression tests for manual resume, Codex parsing, and MCP dispatch.

# Verification

- `$env:PYTHONPATH='src'; python -m unittest discover -s tests -v`
- `$env:PYTHONPATH='src'; python scripts\lint_contracts.py`
- `$env:PYTHONPATH='src'; python scripts\lint_awkp.py`
- `git diff --check`

# Known limits

- The Codex SDK adapter is optional and tested with a fake SDK client.
- The current Codex SDK reference adapter expects the process to be started
  from the intended local workspace.
- Cloud and sandbox profiles remain future adapters.
- MCP is a local thin entrypoint, not a production gateway.
