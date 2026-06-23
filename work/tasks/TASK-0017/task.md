---
type: WorkItem
id: TASK-0017
schema_version: awkp/0.1
title: Improve workflow runtime signals
description: Expose coarse workflow phase status, recent events, failures, and next actions for long-running Agent workflows.
context_id: CTX-ahra-workflow-runtime-signals
priority: P1
risk_level: R1
requester: human:maintainer
reviewer: agent:verifier
created_at: 2026-06-24T00:17:00+08:00
depends_on: [TASK-0016]
input_refs:
  - ../../../docs/architecture/observability-and-evaluation.md
  - ../../../docs/architecture/workflow-modules.md
  - ../../../src/ahra/cli.py
  - ../../../src/ahra/reference_runner/invocation.py
  - ../../../src/ahra/reference_runner/standard_harness.py
output_contract:
  - kind: workflow_phase_status
  - kind: cli_inspection_update
  - kind: documentation_update
  - kind: verification_report
---

# Goal

Give developers enough workflow progress signal to understand long Agent runs
without exposing private reasoning or requiring provider-specific internals.

# Scope

- Define a generic phase status model for workflow modules.
- Include current phase, terminal status, last event, last error, attempt
  counts, elapsed time or timestamps, and recommended next action.
- Extend `workflow inspect` with a stable machine-readable status shape.
- Add `workflow watch` only if it has unique value beyond repeated inspect and
  can be implemented without a fragile polling abstraction.
- Document which signals are audit events and which are operator convenience.

# Non-goals

- Do not record private chain of thought.
- Do not depend on Codex-specific streaming events.
- Do not add a dashboard UI.
- Do not make phase telemetry a substitute for EvidenceGate evidence.

# Acceptance criteria

- [ ] Workflow inspection returns current phase, terminal status, attempt
      summary, last relevant event, last error when present, and next action.
- [ ] The status model is generic across Agent providers and workflow modules.
- [ ] Long-running or failed runs can be diagnosed from CLI output without
      reading raw JSONL first.
- [ ] Any `watch` implementation is optional, documented, and covered by tests;
      if deferred, the missing unique value is stated.
- [ ] Tests cover accepted, failed, and in-progress or partial event streams.
- [ ] `python scripts\check.py`, `python scripts\lint_awkp.py`, and
      `git diff --check` pass.
- [ ] AWKP task state, events, artifact manifest, evidence manifest, and
      handoff exist.

# Verification method

- `python scripts\check.py`
- `python scripts\lint_awkp.py`
- `git diff --check`
- CLI smoke probe for `workflow inspect` on accepted and failed run artifacts.

# Risk and approvals

R1. This exposes operational status only. It must not expose private reasoning,
secrets, or untrusted tool output as trusted facts.
