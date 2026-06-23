---
type: WorkItem
id: TASK-0010
schema_version: awkp/0.1
title: Select ApprovalService implementation trigger
description: Decide the first concrete non-plan high-risk action that requires ApprovalService, or explicitly defer implementation until such an action exists.
context_id: CTX-ahra-approval-service-trigger
priority: P1
risk_level: R1
requester: human:maintainer
reviewer: agent:verifier
created_at: 2026-06-23T10:32:07+08:00
depends_on: [TASK-0009]
input_refs:
  - ../../../docs/architecture/framework-completion-roadmap.md
  - ../../../docs/architecture/approval-service.md
  - ../../../WORKFLOW.md
  - ../../../src/ahra/ports.py
output_contract:
  - kind: approval_trigger_decision
  - kind: architecture_update
  - kind: verification_report
---

# Goal

Prevent premature ApprovalService implementation by choosing the first concrete
non-plan high-risk action that needs scoped authorization, or by explicitly
deferring implementation when no such action exists.

# Scope

- Inventory candidate R2/R3 actions in the starter, such as external service
  calls, publishing, deletion, spending money, writing outside a workspace, or
  high-risk tool execution.
- Select one first ApprovalService implementation trigger, or record that no
  trigger exists yet.
- Define the minimum approval object fields required for that trigger: actor,
  action, resource, parameter digest, scope, expiry, decision, and reason.
- Update docs with the decision and create a follow-up implementation task only
  if a concrete trigger is selected.

# Non-goals

- Do not implement ApprovalStore, dashboard UI, external notification, or
  durable database backing in this task.
- Do not turn plan approval into a general permanent permission.
- Do not implement CI gates, scaffold helpers, or durable control plane.

# Acceptance criteria

- [ ] The first concrete ApprovalService trigger is selected, or implementation
      is explicitly deferred with the missing trigger named.
- [ ] The decision distinguishes task completion EvidenceGate from scoped action
      authorization.
- [ ] The minimum approval record fields are documented for the selected
      trigger or defer case.
- [ ] Any follow-up implementation task is created only if the trigger is
      concrete and unique.
- [ ] `python scripts\check.py`, `python scripts\lint_awkp.py`, and
      `git diff --check` pass.
- [ ] AWKP task state, events, artifact manifest, evidence manifest, and
      handoff exist.

# Verification method

- `python scripts\check.py`
- `python scripts\lint_awkp.py`
- `git diff --check`

# Risk and approvals

R1. This is a decision task. Actual R2/R3 side effects remain out of scope and
require explicit human approval before execution.
