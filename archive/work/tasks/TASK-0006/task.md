---
type: WorkItem
id: TASK-0006
schema_version: awkp/0.1
title: Document framework completion roadmap and verifier gate
description: Establish implementation-facing architecture docs for the remaining AHRA starter gaps before writing more code.
context_id: CTX-ahra-framework-completion-roadmap
priority: P0
risk_level: R1
requester: human:maintainer
reviewer: agent:verifier
created_at: 2026-06-22T23:00:00+08:00
depends_on: [TASK-0005]
input_refs:
  - ../../../architecture/SPEC.md
  - ../../../README.md
  - ../../../docs/architecture/index.md
output_contract:
  - kind: architecture_update
  - kind: roadmap
  - kind: verification_report
---

# Goal

Document the next AHRA starter implementation decisions before starting more
code work, with EvidenceGate identified as the immediate P0 implementation gap.

# Scope

- Add an implementation-facing framework completion roadmap.
- Define the local EvidenceGate concept and minimum verifier behavior.
- Explain ApprovalService as scoped action authorization, not a visual panel.
- Define minimal observability and evaluation records.
- Update the architecture index.
- Record AWKP task state, events, artifact manifest, evidence manifest, and
  handoff.

# Non-goals

- Do not implement EvidenceGate code in this task.
- Do not implement durable stores, dashboards, sandbox runtimes, ApprovalStore,
  scaffold commands, CI, OTel exporters, or EvalRunner code in this task.
- Do not mark TASK-0002, TASK-0003, or TASK-0004 completed.
- Do not mark this task completed before independent verification.

# Acceptance criteria

- [x] Roadmap doc distinguishes immediate, deferred, optional, and pending
      alignment items.
- [x] Roadmap clarifies durable control plane is not a visual panel and can be
      operated through MCP by AI.
- [x] EvidenceGate doc defines verifier inputs, outputs, decisions, and
      fail-closed rules.
- [x] ApprovalService doc explains the difference between task completion and
      scoped action authorization.
- [x] Observability/Evaluation doc defines minimal local records without
      requiring a hosted UI or CI.
- [x] Architecture index links all new docs.
- [x] AWKP task state, events, artifact manifest, evidence manifest, and
      handoff exist.

# Verification method

- `python scripts\lint_awkp.py`
- `python scripts\check.py --lint`
- `git diff --check`

# Risk and approvals

R1. This changes architecture direction only. It should be reviewed before the
next implementation task uses these docs as contract.

