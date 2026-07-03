---
type: EvidenceReport
id: ART-TASK-0063-0006
schema_version: awkp/0.1
title: TASK-0063 refreshed alignment workflow engine report
description: Producer evidence for the post-review RequestDraft boundary and deterministic final draft repair.
status: review
owner: agent:codex-implementation
created_at: 2026-06-30T10:00:01.000010Z
created_by: agent:codex-implementation
supersedes: ART-TASK-0063-0002
---

# Refreshed Alignment Workflow Engine Report

This producer refresh addresses the EvidenceGate finding that the prior `RequestDraft` boundary exposed a direct GoalExecutionRequest-shaped mapping.

Implemented after the prior review:
- Removed `RequestDraft.to_goal_execution_request_mapping()`. A `RequestDraft` no longer exposes a GoalExecutionRequest-shaped bypass around `ApprovalService`.
- Kept `RequestDraft.to_mapping()` as `kind: RequestDraft`; freezing remains owned by `ApprovalService.freeze()`.
- Made final `RequestDraft.request_id` deterministic over structured intent, selected profile, runtime/store refs, claim graph digest, capability policy, and PlanDraft content. Free-text dialogue turns remain auditable session context, but identical structured inputs converge to the same final draft.
- Added regression coverage that different dialogue transcripts with the same structured intent produce the same final `RequestDraft`.

Verification run:
- `uv run python -B -m unittest tests.test_alignment_engine tests.test_request_admission tests.test_approval_service -v` passed.
- `uv run python -B -m unittest tests.test_alignment_engine tests.test_capabilities tests.test_phase1_comprehensive tests.test_cli tests.test_repository_consolidation tests.test_workflow_sequence -v` passed.
- `uv run python -B scripts/check.py` passed: 272 tests passed, 1 Windows symlink skip.
- `uv run python -B scripts/check.py --test` passed: 272 tests passed, 1 Windows symlink skip.
- `uv run python -B scripts/check.py --lint` passed.
- `uv run python -B scripts/lint_awkp.py` passed with 0 errors and 0 warnings.
- `git diff --check` passed.

Boundary:
- Producer does not declare task completion.
- This refreshed report supersedes `ART-TASK-0063-0002` without changing that original artifact's semantics.
