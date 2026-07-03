---
type: WorkItem
id: TASK-0011
schema_version: awkp/0.1
title: Define durable control plane implementation boundary
description: Turn the deferred durable control plane roadmap item into a concrete backlog boundary without implementing stores, queues, or dashboards.
context_id: CTX-ahra-durable-control-plane-boundary
priority: P2
risk_level: R1
requester: human:maintainer
reviewer: agent:verifier
created_at: 2026-06-23T11:09:51+08:00
depends_on: [TASK-0010]
input_refs:
  - ../../../docs/architecture/framework-completion-roadmap.md
  - ../../../architecture/SPEC.md
  - ../../../WORKFLOW.md
  - ../../../src/ahra/ports.py
output_contract:
  - kind: architecture_decision
  - kind: backlog_boundary
  - kind: verification_report
---

# Goal

Define exactly what would make durable control plane implementation necessary,
and what the first implementation boundary must include.

# Scope

- Separate durable control plane from dashboard/UI work.
- Name the state authorities that would move behind durable services: Run
  state, lease/fencing, Task transitions, Artifact/Evidence references,
  Approval records, event publication, and reconciliation.
- Define the minimum local-to-durable migration boundary and compatibility
  expectations.
- Record defer criteria when current file-backed operation remains sufficient.
- Create follow-up implementation tasks only if a concrete durable boundary is
  selected.

# Non-goals

- Do not implement SQLite, Postgres, queue, outbox, reconciler, dashboard, or
  MCP mutation tools in this task.
- Do not change existing AWKP state files or EvidenceGate behavior.
- Do not choose a hosted product by default.

# Acceptance criteria

- [ ] Durable control plane is documented as a state authority and command
      surface, not a visual dashboard.
- [ ] The first durable boundary is either selected or explicitly deferred with
      the missing operational trigger named.
- [ ] Required Port or schema changes are identified without implementing them.
- [ ] Any follow-up implementation task is created only if the durable boundary
      is concrete and unique.
- [ ] `python scripts\check.py`, `python scripts\lint_awkp.py`, and
      `git diff --check` pass.
- [ ] AWKP task state, events, artifact manifest, evidence manifest, and
      handoff exist.

# Verification method

- `python scripts\check.py`
- `python scripts\lint_awkp.py`
- `git diff --check`

# Risk and approvals

R1. This is a planning boundary task. Durable store implementation remains out
of scope until a later task has a concrete selected boundary.
