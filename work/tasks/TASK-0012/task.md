---
type: WorkItem
id: TASK-0012
schema_version: awkp/0.1
title: Decide project scaffold helper necessity
description: Decide whether the optional project scaffold/init helper has a unique value over copying the starter manually.
context_id: CTX-ahra-project-scaffold-decision
priority: P2
risk_level: R1
requester: human:maintainer
reviewer: agent:verifier
created_at: 2026-06-23T11:09:51+08:00
depends_on: [TASK-0010]
input_refs:
  - ../../../docs/architecture/framework-completion-roadmap.md
  - ../../../README.md
  - ../../../work/index.md
  - ../../../scripts/check.py
output_contract:
  - kind: scaffold_decision
  - kind: verification_report
---

# Goal

Decide whether a scaffold/init helper is worth implementing, given that copying
the starter manually is already a valid adoption path.

# Scope

- Compare manual copy with a helper whose only valid purpose is reducing
  adoption mistakes.
- If justified, define the smallest helper scope: rename identifiers, clear or
  archive sample tasks, create the first task/context, refresh indexes, validate
  paths, and run local checks.
- If not justified, record defer criteria and keep manual copy as the default.
- Create a follow-up implementation task only if the helper has a unique,
  concrete scope.

# Non-goals

- Do not implement scaffold code in this task.
- Do not delete or archive current sample tasks in this repository.
- Do not choose a package manager, installer, or distribution channel.
- Do not change the default AWKP task lifecycle.

# Acceptance criteria

- [ ] Manual copy remains documented as a valid adoption path.
- [ ] Scaffold helper is either justified with one minimal scope or explicitly
      deferred.
- [ ] Any proposed helper behavior has a unique reason and avoids duplicating
      manual steps without reducing risk.
- [ ] Any follow-up implementation task is created only if the helper scope is
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

R1. This is an optional tooling decision. It must not turn into broad
generation logic without a concrete adoption risk.
