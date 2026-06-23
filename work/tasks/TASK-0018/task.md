---
type: WorkItem
id: TASK-0018
schema_version: awkp/0.1
title: Add runtime profile capability enforcement skeleton
description: Turn runtimeProfileRef into a provider-neutral capability contract for Agent tools, filesystem, network, approval, and limits.
context_id: CTX-ahra-runtime-profile-capabilities
priority: P1
risk_level: R1
requester: human:maintainer
reviewer: agent:verifier
created_at: 2026-06-24T00:17:00+08:00
depends_on: [TASK-0017]
input_refs:
  - ../../../contracts/schemas/agent.schema.json
  - ../../../contracts/schemas/workflow-run-request.schema.json
  - ../../../docs/architecture/reference-runtime-adapters-and-mcp.md
  - ../../../src/ahra/ports.py
  - ../../../src/ahra/reference_runner/invocation.py
output_contract:
  - kind: runtime_profile_contract
  - kind: capability_registry
  - kind: adapter_validation
  - kind: verification_report
---

# Goal

Make runtime profiles enforceable as a generic Agent capability contract while
keeping Codex as only one possible adapter.

# Scope

- Define the minimum runtime profile fields for role, tools, filesystem,
  network, approval behavior, timeouts, and attempt limits.
- Add a capability validation layer that can reject a driver/profile mismatch
  before execution.
- Keep the domain layer dependent on AHRA ports and contracts, not provider
  SDK types.
- Document how a future Agent provider can map its own permissions into the
  same profile contract.
- Preserve current Codex SDK operation through the generic adapter boundary.

# Non-goals

- Do not implement a full sandbox or external policy engine.
- Do not make Codex-specific fields mandatory for other providers.
- Do not execute high-risk actions without ApprovalService.
- Do not store secrets in runtime profiles, prompts, artifacts, traces, or
  memory.

# Acceptance criteria

- [ ] Runtime profiles have a documented generic capability schema or contract.
- [ ] Workflow startup fails closed when a requested driver cannot satisfy the
      selected runtime profile.
- [ ] Codex-specific permission mapping remains inside the Codex adapter.
- [ ] Tests cover compatible and incompatible driver/profile combinations.
- [ ] Docs explain how non-Codex Agent adapters should implement the contract.
- [ ] `python scripts\check.py`, `python scripts\lint_awkp.py`, and
      `git diff --check` pass.
- [ ] AWKP task state, events, artifact manifest, evidence manifest, and
      handoff exist.

# Verification method

- `python scripts\check.py`
- `python scripts\lint_awkp.py`
- `git diff --check`
- Unit tests for runtime profile validation and adapter capability mapping.

# Risk and approvals

R1. This task defines and enforces local execution capability contracts. It
does not grant new external permissions.
