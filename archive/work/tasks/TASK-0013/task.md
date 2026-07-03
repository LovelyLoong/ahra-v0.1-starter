---
type: WorkItem
id: TASK-0013
schema_version: awkp/0.1
title: Decide optional CI gates wrapper
description: Decide whether to add CI gates as an optional wrapper around authoritative local checks.
context_id: CTX-ahra-ci-gates-decision
priority: P2
risk_level: R1
requester: human:maintainer
reviewer: agent:verifier
created_at: 2026-06-23T11:09:51+08:00
depends_on: [TASK-0010]
input_refs:
  - ../../../docs/architecture/framework-completion-roadmap.md
  - ../../../WORKFLOW.md
  - ../../../Makefile
  - ../../../scripts/check.py
output_contract:
  - kind: ci_gate_decision
  - kind: verification_report
---

# Goal

Decide whether this starter should include optional CI gates, while keeping
local checks authoritative for projects that do not use CI.

# Scope

- Identify which local checks a CI wrapper would run.
- Decide whether to defer CI, provide a provider-neutral recipe, or add a
  concrete CI configuration later.
- Define the minimum failure surface: contract lint, AWKP lint, unit tests, and
  whitespace checks.
- Create a follow-up implementation task only if one CI wrapper target is
  selected.

# Non-goals

- Do not implement CI configuration in this task.
- Do not make CI required for framework correctness.
- Do not choose multiple CI providers or duplicate local check logic.
- Do not change `python scripts\check.py` semantics.

# Acceptance criteria

- [ ] CI is documented as optional and local checks remain authoritative.
- [ ] The CI wrapper is either deferred or narrowed to one concrete target.
- [ ] The wrapper check list maps directly to existing local commands without
      inventing parallel validation logic.
- [ ] Any follow-up implementation task is created only if the CI target is
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

R1. This is optional project automation. It must not weaken or replace local
verification.
