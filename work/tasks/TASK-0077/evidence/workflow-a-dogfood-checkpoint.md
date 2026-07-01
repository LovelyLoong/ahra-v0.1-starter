---
type: Evidence
id: EVD-TASK-0077-0001
schema_version: awkp/0.1
title: Workflow A dogfood checkpoint and workflow hardening summary
description: Producer evidence summarizing successful Workflow B development-bounded dogfood run and immediate dogfood request hardening.
task_id: TASK-0077
owner: agent:codex
status: review
created_by: agent:codex
created_at: 2026-07-01T10:29:46.460060Z
---
# Workflow A Dogfood Checkpoint

## GoalExecution

- GoalExecution: `GEXEC-b4a41e0e3a22e6fb`
- Request: `examples/goals/dogfood-a-alignment-session.yaml` before hardening, `dogfood-a-003`
- Result: `succeeded`
- Completion: `complete=true`, `currentClaimCoverage=1.0`, `defects=0`
- Kernel evidence refs: `EVD-808a23cf72ea2ddc`, `EVD-e17537aeed441163`

## Produced Code

- `src/ahra/alignment_session.py`
- `tests/test_alignment_session.py`

The generated module is a usable first checkpoint for Workflow A: it consumes the provider-neutral `AgentDriver` port, preserves resumable immutable session snapshots, rejects mismatched profile/runtime digest references before Agent invocation, and emits an untrusted `RequestDraft` rather than a frozen `GoalExecutionRequest`.

## Workflow Hardening

`examples/goals/dogfood-a-alignment-session.yaml` was advanced to `dogfood-a-004` with fresh idempotency/artifact/store targets. The alignment-session node now declares `process.exec` for `uv run python -B scripts/check.py --test`, so the next dogfood run has a deterministic required command check instead of only file-existence checks.

## Known Boundary

This checkpoint is not the final ADR-0009 Workflow A implementation. Requirement and Acceptance Agent outputs are invoked and admitted, but the current implementation still retains fallback helpers from the deterministic `alignment_engine` for missing explicit `planDraft` or `claimGraph` output. That is the next semantic tightening item.
