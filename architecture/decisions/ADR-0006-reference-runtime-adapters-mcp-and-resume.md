# ADR-0006: Reference runtime adapters, MCP entrypoint, and resume requests

- Status: accepted
- Date: 2026-06-22

## Decision

AHRA keeps workflow module contracts independent from any one agent product.
The starter may still provide reference adapters that make the template usable
locally. Those adapters live outside AHRA domain code and must implement
stable ports.

The first concrete driver adapter is a Codex Python SDK adapter behind the
global `AgentDriver` port. It is optional. Users supply their own Codex login,
environment, sandbox policy, model, and SDK installation. The adapter owns
provider prompting and structured-output parsing; workflow modules only see
`AgentRunRequest` and `AgentRunResult`.

The reference runner supports a separate `WorkflowResumeRequest` for manual
plan approval. `WorkflowRunRequest` starts a run. `WorkflowResumeRequest`
continues an existing run after a bounded approval decision that references
the exact plan artifact digest. Resume is not encoded as a new start request.

The starter also exposes a thin local MCP server. MCP is only an integration
entrypoint for agents to list modules, validate requests, start runs, inspect
run artifacts, and resume approved plans. MCP does not become the security
boundary, the workflow engine, or the evidence authority.

## Consequences

- Codex, Claude Code, OpenAI Agents SDK, open-source agent frameworks, direct
  LLM APIs, and human adapters remain peer driver implementations.
- AHRA core does not import Codex SDKs or MCP SDKs.
- Agents can operate the starter through files, direct Python APIs, or MCP
  tools without changing workflow module descriptors.
- Manual approval is tied to a concrete plan artifact SHA-256, avoiding vague
  approvals such as "continue whatever the planner said".
- Local execution is the only supported reference runtime profile in v0.1.
  Cloud and sandbox execution are future adapters behind existing ports.

## Non-goals

- Do not make Codex mandatory.
- Do not store provider credentials in prompts, artifacts, evidence, memory,
  or snapshots.
- Do not implement a production multi-tenant MCP gateway in the starter.
- Do not make `ProjectAdapter` mandatory for projects using this template.
- Do not let MCP tools bypass request schema validation or workflow module
  registry resolution.
