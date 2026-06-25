---
type: Handoff
id: HANDOFF-TASK-0022-0001
schema_version: awkp/0.1
title: TASK-0022 producer handoff
description: Producer handoff for dynamic-kernel authority and lifecycle integration.
status: active
owner: agent:codex-dynamic-kernel-operator
source_refs: [../task.md, ../state.json, ../evidence/implementation-report.json]
evidence_refs: [EVD-TASK-0022-0001, EVD-TASK-0022-0002, EVD-TASK-0022-0003, EVD-TASK-0022-0004]
confidence: reviewed
last_verified_at: 2026-06-25T07:00:05Z
review_after: 2026-09-25T00:00:00Z
tags: [handoff, dynamic-kernel, task-0022]
---

# TASK-0022 Handoff

Producer work is ready for independent verification. TASK-0022 is intentionally in `review`, not `completed`.

## What changed

- ADR-0007 is marked accepted.
- `docs/architecture/authority-map.md` is the active routing table for architecture concepts.
- README and AGENTS distinguish current implemented paths from target dynamic-kernel architecture.
- Architecture, policy, decision and roadmap indexes now expose the new authority chain.
- Duplicate/superseded documents remain traceable but are not default authorities.
- `scripts/lint_awkp.py` checks authority-map duplicate IDs, active owner links, and active owner status.

## Verification already run

- `uv run python -B scripts/check.py` passed.
- `uv run python -B scripts/lint_awkp.py` passed.
- `git diff --check` passed.

## Exact next action

Independent verifier should map every TASK-0022 criterion to the evidence files, rerun the verification commands, and use EvidenceGate with expected state_version 3.
