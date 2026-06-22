---
type: WorkItem
id: TASK-0003
schema_version: awkp/0.1
title: Add agent-neutral workflow invocation
description: Document and implement a vendor-neutral AgentDriver registry and WorkflowRunRequest launch path for AHRA workflow modules.
context_id: CTX-ahra-workflow-invocation
priority: P1
risk_level: R1
requester: human:maintainer
reviewer: agent:verifier
created_at: 2026-06-22T08:30:00Z
depends_on: [TASK-0002]
input_refs:
  - ../../../architecture/decisions/ADR-0005-agent-neutral-workflow-invocation.md
  - ../../../docs/architecture/agent-drivers-and-workflow-invocation.md
  - ../../../docs/architecture/workflow-modules.md
output_contract:
  - kind: architecture_decision
  - kind: workflow_run_request_schema
  - kind: agent_driver_registry
  - kind: workflow_runner_api
  - kind: local_skill
  - kind: verification_report
---

# Goal

Make workflow startup agent-friendly without coupling AHRA to Codex, Claude
Code, OpenAI Agents SDK, LangGraph, direct LLM APIs, or any current chat
session.

# Scope

- Document agent-neutral driver and workflow invocation rules.
- Add `WorkflowRunRequest` contract and examples.
- Add a local skill that tells agents how to start workflow modules.
- Convert the reference runner to a role-based `AgentDriver` request model.
- Add a driver registry and stable runner API.
- Validate the flow with a fake driver.

# Non-goals

- Do not implement a production Codex adapter.
- Do not implement a Claude Code adapter.
- Do not require a project-specific `ProjectAdapter`.
- Do not add a mandatory CLI.
- Do not mark this task completed before independent verification.

# Acceptance criteria

- [ ] Codex has no special architectural path in AHRA core.
- [ ] Workflow modules use an agent-neutral role request contract.
- [ ] `driverRef` resolves through a fail-closed registry.
- [ ] `WorkflowRunRequest` examples validate against schema.
- [ ] A test can start `standard-harness` through `WorkflowRunRequest` and registry.
- [ ] A local skill documents how an Agent should start workflow modules.
- [ ] AWKP task state, events, artifact manifest, evidence manifest, and handoff exist.

# Verification method

- `git diff --check`
- `$env:PYTHONPATH='src'; python scripts\lint_awkp.py`
- `$env:PYTHONPATH='src'; python scripts\lint_contracts.py`
- `$env:PYTHONPATH='src'; python -m unittest discover -s tests -v`

# Risk and approvals

R1. This changes workflow invocation contracts and should be reviewed by an
independent verifier before the task is completed.
