---
type: WorkItem
id: TASK-0007
schema_version: awkp/0.1
title: Implement local EvidenceGate verifier completion
description: Add a local file-backed EvidenceGate command and MCP operation surface for verifier-controlled AWKP task completion.
context_id: CTX-ahra-evidence-gate
priority: P0
risk_level: R1
requester: human:maintainer
reviewer: agent:verifier
created_at: 2026-06-22T23:30:00+08:00
depends_on: [TASK-0006]
input_refs:
  - ../../../docs/architecture/evidence-gate.md
  - ../../../docs/architecture/reference-runtime-adapters-and-mcp.md
  - ../../../src/ahra/ports.py
output_contract:
  - kind: evidence_gate_cli
  - kind: mcp_operation_surface
  - kind: tests
  - kind: verification_report
---

# Goal

Close the P0 manual-completion gap by implementing the first local
EvidenceGate path for AWKP tasks in `review`.

# Scope

- Add a stdlib local EvidenceGate module and CLI.
- Parse `task.md` acceptance criteria.
- Validate `state.json` expected version before transition.
- Validate artifact and evidence manifests, local evidence files, and SHA-256
  hashes.
- Require a verifier report mapping criteria to Evidence IDs.
- Reject producer self-verification.
- Write a gate report artifact/evidence record.
- Append an AWKP event and update `state.json` to `completed` or
  `changes_requested`.
- Expose task inspect and EvidenceGate evaluate through the local MCP server.
- Add focused tests for approve, request changes, stale version, self-verifier
  rejection, missing evidence rejection, inspect, and MCP dispatch.

# Non-goals

- Do not implement SQLite/Postgres durable stores.
- Do not implement dashboards, CI, OTel exporters, EvalRunner, ApprovalStore,
  or sandbox runtime providers.
- Do not mark TASK-0002, TASK-0003, TASK-0004, or TASK-0006 completed.
- Do not use EvidenceGate to self-complete this task.

# Acceptance criteria

- [x] `python -m ahra.evidence_gate evaluate` validates expected version,
      manifests, evidence hashes, verifier identity, and criterion evidence.
- [x] Approve transitions a task from `review` to `completed` and writes gate
      artifact/evidence/event records.
- [x] Request changes transitions a task from `review` to
      `changes_requested` and records blockers.
- [x] The gate fails closed for stale expected version, producer
      self-verification, and approve without evidence for every criterion.
- [x] MCP exposes task inspect and EvidenceGate evaluate tools backed by the
      same Python service.
- [x] Tests cover local service and MCP dispatch.
- [x] Documentation describes the implemented CLI report shape and MCP tools.
- [x] AWKP task state, events, artifact manifest, evidence manifest, and
      handoff exist.

# Verification method

- `python scripts\check.py`
- `python scripts\lint_awkp.py`
- `git diff --check`

# Risk and approvals

R1. This mutates AWKP task state when a verifier invokes it, so it must be
reviewed independently before being used as the normal completion path.

