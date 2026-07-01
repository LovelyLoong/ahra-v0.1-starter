---
type: Handoff
id: HANDOFF-TASK-0081-0001
schema_version: awkp/0.1
title: TASK-0081 producer handoff
description: Producer handoff for formal experimental Workflow A CLI lifecycle.
owner: agent:codex
status: active
created_by: agent:codex
created_at: 2026-07-01T12:08:30.623896Z
---

# Summary
Added explicit experimental `workflow-a` CLI lifecycle commands.

# Changes
- `src/ahra/workflow_a_cli.py` provides session start/advance/snapshot, Human Gate 1 approval, RequestDraft drafting, admission, and ApprovalService authorization helpers.
- `src/ahra/cli.py` exposes `workflow-a start`, `advance`, `snapshot`, `approve-requirement`, `draft`, `admit`, and `authorize`.
- `tests/test_cli.py` covers the lifecycle, including fail-closed draft before Human Gate 1 and non-human Gate 1 rejection.
- `component:alignment-session-manager` remains experimental/default_visible false.

# Verification
See `evidence/verification-summary.json`.

# Review Boundary
Producer evidence only. Do not mark TASK-0081 completed without independent EvidenceGate review.
