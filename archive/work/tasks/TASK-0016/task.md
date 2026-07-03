---
type: WorkItem
id: TASK-0016
schema_version: awkp/0.1
title: Systematize EvidenceGate workflow handoff
description: Turn workflow accepted and failed outcomes into explicit verifier handoffs without allowing producer self-approval.
context_id: CTX-ahra-evidencegate-workflow-handoff
priority: P0
risk_level: R1
requester: human:maintainer
reviewer: agent:verifier
created_at: 2026-06-24T00:17:00+08:00
depends_on: [TASK-0015]
input_refs:
  - ../../../docs/architecture/evidence-gate.md
  - ../../../docs/architecture/workflow-modules.md
  - ../../../skills/ahra-workflow-runner/SKILL.md
  - ../../../src/ahra/evidence_gate.py
  - ../../../src/ahra/reference_runner/awkp_task.py
  - ../../../src/ahra/reference_runner/invocation.py
output_contract:
  - kind: verifier_handoff_contract
  - kind: evidence_mapping
  - kind: documentation_update
  - kind: verification_report
---

# Goal

Make the transition from workflow run output to EvidenceGate review systematic,
auditable, and explicit for both accepted and failed formal AWKP runs.

# Scope

- Define one task-local handoff shape for workflow-produced evidence.
- Map acceptance criteria to evidence references, command results, changed
  files, run status, residual risks, and verifier next action.
- Keep workflow accepted as a request for independent review, not completion.
- Keep workflow failed as a user or verifier judgment point, not an automatic
  retry loop.
- Update CLI, docs, and Skill guidance so agents know the exact next command or
  handoff after a formal run.

# Non-goals

- Do not weaken EvidenceGate acceptance criteria.
- Do not allow the workflow producer identity to approve its own work.
- Do not create a dashboard or durable approval service in this task.
- Do not change unrelated AWKP task state machine rules.

# Acceptance criteria

- [ ] Formal workflow handoff records include criteria mapping, evidence refs,
      command results, changed files, run status, producer identity, and
      verifier next action.
- [ ] Accepted workflow runs move formal tasks only to `review` and name the
      EvidenceGate action required next.
- [ ] Failed workflow runs preserve failure evidence and identify the human or
      verifier judgment needed next.
- [ ] EvidenceGate docs and the local Skill describe the producer/verifier
      boundary unambiguously.
- [ ] Tests cover accepted handoff content and failed handoff content.
- [ ] `python scripts\check.py`, `python scripts\lint_awkp.py`, and
      `git diff --check` pass.
- [ ] AWKP task state, events, artifact manifest, evidence manifest, and
      handoff exist.

# Verification method

- `python scripts\check.py`
- `python scripts\lint_awkp.py`
- `git diff --check`
- Formal AWKP workflow fixture that reaches `review`.
- Formal AWKP workflow fixture that reaches terminal failure.

# Risk and approvals

R1. This changes workflow handoff contracts but does not approve task
completion. Completion remains controlled by EvidenceGate.
