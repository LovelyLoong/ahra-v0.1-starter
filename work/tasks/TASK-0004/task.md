---
type: WorkItem
id: TASK-0004
schema_version: awkp/0.1
title: Add reference driver adapter, workflow resume, and MCP operation surface
description: Document and implement optional Codex SDK driver integration, manual plan resume, and a thin local MCP entrypoint without coupling AHRA core to a provider.
context_id: CTX-ahra-runtime-adapters-mcp
priority: P1
risk_level: R1
requester: human:maintainer
reviewer: agent:verifier
created_at: 2026-06-22T10:20:00Z
depends_on: [TASK-0003]
input_refs:
  - ../../../architecture/decisions/ADR-0005-agent-neutral-workflow-invocation.md
  - ../../../docs/architecture/agent-drivers-and-workflow-invocation.md
  - ../../../skills/ahra-workflow-runner/SKILL.md
output_contract:
  - kind: architecture_decision
  - kind: workflow_resume_request_schema
  - kind: optional_agent_driver_adapter
  - kind: mcp_entrypoint
  - kind: verification_report
---

# Goal

Make the AHRA starter usable as a local agent-friendly harness template by
adding the missing reference operation layer: optional Codex SDK driver
adapter, explicit manual-plan resume, and MCP tools that call the same runner
contracts.

# Scope

- Document reference runtime adapter rules before implementation.
- Add `WorkflowResumeRequest` for manual plan approval and resume.
- Preserve `WorkflowRunRequest` as the launch object.
- Add an optional Codex Python SDK `AgentDriver` adapter outside AHRA core.
- Add a thin local MCP stdio entrypoint for agents.
- Keep local execution as the only implemented runtime profile.
- Leave cloud and sandbox runtime profiles as future adapters behind ports.

# Non-goals

- Do not make Codex mandatory.
- Do not implement Claude Code, OpenAI Agents SDK, or open-source framework
  adapters in this task.
- Do not implement a production multi-tenant MCP gateway.
- Do not make `ProjectAdapter` mandatory.
- Do not mark this task completed before independent verification.

# Acceptance criteria

- [ ] Docs define Codex SDK driver as an optional adapter behind `AgentDriver`.
- [ ] Docs define local/cloud/sandbox runtime profile boundaries.
- [ ] Docs define MCP as an agent entrypoint, not a workflow engine or trust
      boundary.
- [ ] `WorkflowResumeRequest` schema and example validate.
- [ ] Manual `loop-engineering` plan approval resumes only when the approved
      plan SHA-256 matches the stored plan artifact.
- [ ] Codex SDK adapter can be unit-tested with a fake SDK client and does not
      require Codex in baseline tests.
- [ ] MCP tool handlers validate and dispatch through the same runner APIs.
- [ ] AWKP task state, events, artifact manifest, evidence manifest, and
      handoff exist.

# Verification method

- `git diff --check`
- `$env:PYTHONPATH='src'; python scripts\lint_awkp.py`
- `$env:PYTHONPATH='src'; python scripts\lint_contracts.py`
- `$env:PYTHONPATH='src'; python -m unittest discover -s tests -v`

# Risk and approvals

R1. This adds operation surfaces and an optional provider adapter. It should be
reviewed independently before the task is completed.
