---
type: WorkItem
id: TASK-0014
schema_version: awkp/0.1
title: Implement CLI and Skill operation entrypoint
description: Make CLI plus local Skill the default operation surface and remove MCP from the starter default route.
context_id: CTX-ahra-cli-skill-entrypoint
priority: P1
risk_level: R1
requester: human:maintainer
reviewer: agent:verifier
created_at: 2026-06-23T14:32:49+08:00
depends_on: [TASK-0009]
input_refs:
  - ../../../docs/architecture/framework-entrypoints.md
  - ../../../docs/architecture/framework-completion-roadmap.md
  - ../../../docs/architecture/agent-drivers-and-workflow-invocation.md
  - ../../../skills/ahra-workflow-runner/SKILL.md
  - ../../../src/ahra/reference_runner/invocation.py
  - ../../../src/ahra/evidence_gate.py
  - ../../../src/ahra/mcp_server.py
output_contract:
  - kind: cli_entrypoint
  - kind: skill_update
  - kind: example_split
  - kind: verification_report
---

# Goal

Make the starter operable through CLI plus local Skill, with documentation as
the human-readable authority, and remove MCP from the default operation path.

# Scope

- Define and implement the smallest CLI wrapper around existing Python APIs:
  workflow validate/start/inspect/resume, task inspect, EvidenceGate evaluate,
  and doctor/check.
- Provide at least one real local non-fixture `AgentDriver` route usable on the
  maintainer workstation when the dependency is available locally.
- Update the local Skill so agents call the CLI commands once they exist.
- Keep direct Python APIs as implementation internals used by tests.
- Mark MCP as legacy or remove it from the starter default path; do not add
  MCP-only features.
- Split examples into schema/test fixtures and runnable local examples so
  `fake-reference` cannot be mistaken for a default driver.
- Ensure all CLI behavior fails closed on unknown modules, unknown drivers,
  driver execution errors, stale expected versions, invalid plan digests,
  missing manifests, and missing evidence.

# Non-goals

- Do not implement durable control plane, ApprovalService, scaffold helpers, CI
  workflows, dashboard UI, or stronger runtime sandboxing.
- Do not introduce a provider-specific driver as the only valid route.
- Do not make MCP required for local operation.
- Do not change EvidenceGate completion semantics.

# Acceptance criteria

- [ ] CLI commands wrap the existing local APIs without duplicating workflow
      logic.
- [ ] A non-fixture local driver can be selected from CLI without requiring the
      deprecated MCP route.
- [ ] Workflow terminal failure states are surfaced as CLI failures, not
      reported as successful command execution.
- [ ] The local Skill names the CLI commands agents should use.
- [ ] MCP is removed from the default docs/Skill path or explicitly quarantined
      as legacy.
- [ ] Runnable examples and test fixtures are clearly separated.
- [ ] `python scripts\check.py`, `python scripts\lint_awkp.py`, and
      `git diff --check` pass.
- [ ] AWKP task state, events, artifact manifest, evidence manifest, and
      handoff exist.

# Verification method

- `python scripts\check.py`
- `python scripts\lint_awkp.py`
- `git diff --check`
- CLI smoke probes for each implemented command group.
- Driver smoke probe for the non-fixture local driver when local credentials
  and binaries are available.

# Risk and approvals

R1. This changes local operation surfaces but should not perform external
side effects. Any future risky action exposed through CLI must go through a
separate ApprovalService task.
