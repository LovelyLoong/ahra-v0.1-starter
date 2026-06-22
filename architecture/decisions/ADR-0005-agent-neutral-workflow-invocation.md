# ADR-0005: Agent-neutral workflow invocation

- Status: accepted
- Date: 2026-06-22

## Decision

AHRA workflow modules must not depend on a specific interactive agent product,
agent framework, model SDK, or the current assistant session.

Workflow execution is started from a structured `WorkflowRunRequest`. The
request names the workflow module, input refs, workspace ref, driver ref,
store ref, approval mode, and run metadata. A local CLI, CI job, IDE agent,
MCP tool, or human-facing agent can all create the same request.

Agent execution is a separate adapter boundary. Workflow modules call an
agent-neutral `AgentDriver` port with role-specific requests:

1. `executor`
2. `task_reviewer`
3. `goal_reviewer`
4. `planner`

Adapters such as Codex, Claude Code, OpenAI Agents SDK, LangGraph, local
command agents, direct LLM APIs, or human review services are peer
implementations. None of them has special architectural status in AHRA core.

The first reference implementation may use a fake or local driver for tests.
A real Codex adapter can be added as one adapter, but it must not change the
workflow module contract.

## Consequences

- Users can say "start the loop-engineering workflow" in any compatible agent
  environment if that environment knows how to create a `WorkflowRunRequest`.
- The current Codex session is only an operator while developing the template;
  it is not part of the runtime architecture.
- Workflow modules stay stable when the project swaps Codex for Claude Code,
  an open-source agent framework, or a direct LLM API.
- Driver adapters own provider-specific prompting, structured-output parsing,
  credentials, tracing, and SDK calls.
- AHRA core owns request schema, driver registry semantics, artifact/evidence
  rules, and workflow module dispatch.

## Non-goals

- Do not implement every vendor adapter in the starter.
- Do not make `ProjectAdapter` mandatory for every project at template time.
- Do not let a launch agent self-declare an AWKP Task completed.
- Do not infer driver capabilities from runtime exceptions; adapters must
  register their declared capabilities.
