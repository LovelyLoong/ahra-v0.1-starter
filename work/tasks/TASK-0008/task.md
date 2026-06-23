---
type: WorkItem
id: TASK-0008
schema_version: awkp/0.1
title: Implement minimal local observability and evaluation artifacts
description: Add the first local-only observability and evaluation records after EvidenceGate so runs and gate decisions have durable, inspectable traces without requiring hosted services.
context_id: CTX-ahra-local-observability-eval
priority: P0
risk_level: R1
requester: human:maintainer
reviewer: agent:verifier
created_at: 2026-06-23T10:32:07+08:00
depends_on: [TASK-0007]
input_refs:
  - ../../../docs/architecture/framework-completion-roadmap.md
  - ../../../docs/architecture/observability-and-evaluation.md
  - ../../../docs/architecture/evidence-gate.md
  - ../../../src/ahra/ports.py
output_contract:
  - kind: local_observability_records
  - kind: local_eval_records
  - kind: tests
  - kind: verification_report
---

# Goal

Implement the next roadmap item after EvidenceGate: minimal local
observability and evaluation artifacts that are useful in an AI-operated
starter without requiring a hosted UI, CI service, OTel collector, or EvalRunner.

# Scope

- Define local JSON record shapes for run/gate audit, trace summary, cost or
  usage summary, and evaluation result.
- Add stdlib helpers or service code that writes these records as local
  artifacts with stable IDs and SHA-256 hashes.
- Connect the local records to the existing AWKP artifact/evidence pattern
  without making telemetry the source of task truth.
- Add inspectable examples or fixtures that show how EvidenceGate and workflow
  runs can reference these records.
- Add focused tests for deterministic record generation, hash stability, and
  no private thought-chain persistence.
- Update documentation only where it describes the implemented local record
  shape.

# Non-goals

- Do not implement OTel exporters, hosted dashboards, Langfuse/APM integration,
  online eval runners, CI gates, or durable database storage.
- Do not implement runtime sandbox providers.
- Do not implement ApprovalService.
- Do not mark TASK-0007 completed as part of this task.

# Acceptance criteria

- [ ] Local audit, trace summary, usage/cost summary, and eval result record
      shapes are defined and documented.
- [ ] Record writing produces content-addressed local artifact/evidence records
      with deterministic JSON serialization.
- [ ] EvidenceGate or reference workflow examples can attach the local records
      without replacing AWKP state, event, artifact, or evidence authority.
- [ ] Tests prove hash stability, schema validity, and no private thought-chain
      field is persisted.
- [ ] `python scripts\check.py`, `python scripts\lint_awkp.py`, and
      `git diff --check` pass.
- [ ] AWKP task state, events, artifact manifest, evidence manifest, and
      handoff exist.

# Verification method

- `python scripts\check.py`
- `python scripts\lint_awkp.py`
- `git diff --check`

# Risk and approvals

R1. This adds local records that may later become audit inputs, so it must be
reviewed independently before completion.
