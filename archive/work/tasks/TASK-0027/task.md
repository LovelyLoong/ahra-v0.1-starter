---
type: WorkItem
id: TASK-0027
schema_version: awkp/0.1
title: Implement capability admission and a default-deny runtime gateway
description: Turn plan capability requests into narrower signed grants and enforce them at side-effect boundaries.
context_id: CTX-ahra-dynamic-kernel
priority: P0
risk_level: R2
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-25T00:00:00Z
depends_on: [TASK-0026]
input_refs:
  - docs/policies/agent-authority-boundaries.md
  - src/ahra/policy.py
  - src/ahra/ports.py
  - PlanIR contracts
output_contract:
  - kind: capability_request_schema
  - kind: capability_grant_schema
  - kind: admission_service
  - kind: runtime_gateway
  - kind: audit_records
  - kind: security_tests
---

# Goal

Prevent Planner or Executor Agents from granting themselves filesystem, tool, network, secret, or spawn permissions.

# Scope

- Define CapabilityRequest and CapabilityGrant with resource, action, scope, expiry, plan/node binding and digest.
- Implement admission that intersects Goal scope, policy, runtime support, risk and approval.
- Implement a local gateway for filesystem writes and command execution used by the new node path.
- Record policy decision, grant, argument digest, result digest and actor for every side effect.
- Deny path escape, undeclared command, expired grant, wrong node/plan, stale grant, unsupported network/secret request, and privilege widening.
- Document explicitly which isolation properties the local profile does and does not provide.

# Non-goals

- Do not claim host/process/network isolation that is not implemented.
- Do not implement production secret brokers or remote sandboxes.
- Do not expose irreversible external actions.

# Acceptance criteria

- [ ] No request can compile into a grant broader than Goal/Policy scope.
- [ ] Planner and verifier roles receive no filesystem write grant by default.
- [ ] Executor writes outside allowed globs and commands outside allowlists are blocked before execution.
- [ ] Every allowed and denied side effect emits an audit record linked to plan, node and policy decision.
- [ ] Unsupported high-risk capabilities pause/fail closed rather than silently downgrade.
- [ ] Security tests cover path traversal, symlink escape where applicable, command substitution, stale grant, role mismatch, spawn limit and approval absence.

# Verification method

- python scripts/check.py
- security test suite
- policy/admission contract tests
- audit completeness test
- git diff --check

# Required evidence and handoff

- Publish an implementation/change report with exact files, contracts, migrations, known limitations, and unresolved items.
- Preserve deterministic command outputs or structured summaries with content digests.
- Map every acceptance criterion to one or more Evidence IDs.
- Record the producer Agent Release, Context Manifest, workspace/branch, base commit, and final commit or rejected patch.
- Create an immutable Handoff with one exact next action when blocked, failed, paused, or returned for changes.
- The producer must not mark this task completed; an independent verifier and EvidenceGate decide completion.

# Rollback and compatibility

- Do not silently overwrite released contracts or historical events.
- Use a new schema version when field meaning changes or compatibility is broken.
- Keep compatibility adapters until the task explicitly authorizes their removal.
- Any rollback must preserve Artifact/Evidence references and explain state projection changes.

# Risk and approvals

Risk level: **R2**. R2 because this establishes a security boundary. Independent security review is mandatory.
