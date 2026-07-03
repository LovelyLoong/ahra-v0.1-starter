---
type: Handoff
id: HANDOFF-TASK-0023-0001
schema_version: awkp/0.1
title: TASK-0023 acceptance contracts ready for review
description: Producer handoff for GoalContract, ClaimGraph, GateDefinition, and GatePlan contract implementation.
status: active
owner: agent:codex-dynamic-kernel-operator
source_refs: [../task.md, ../state.json, ../artifact-manifest.json, ../evidence-manifest.json]
evidence_refs: [EVD-TASK-0023-0001, EVD-TASK-0023-0002, EVD-TASK-0023-0003, EVD-TASK-0023-0004, EVD-TASK-0023-0005]
confidence: reviewed
last_verified_at: 2026-06-25T15:34:46+08:00
review_after: 2026-09-25T00:00:00Z
tags: [handoff, task-0023, dynamic-kernel]
---

# Summary

TASK-0023 is implemented and ready for independent EvidenceGate review. The producing agent did not mark the task completed.

# Completed Work

- Added GoalContract, ClaimGraph, GateDefinition, and GatePlan schemas under `contracts/schemas/`.
- Added provider-neutral dataclasses and deterministic validation in `src/ahra/acceptance_contracts.py`.
- Added valid examples and invalid examples for uncovered criteria, cyclic dependency, duplicate Claim ID, and forbidden security downgrade.
- Added contract unit tests and schema lint mappings.
- Corrected TASK-0022 `input_refs` metadata to point at TASK-0021 `component-inventory.json` evidence and recorded `EVT-TASK-0022-0005`.

# Verification

- `uv run python -B scripts/check.py`: passed, 82 tests OK.
- `uv run python -B scripts/lint_awkp.py`: passed, 0 errors and 0 warnings.
- `git diff --check`: passed with no output after LF normalization.

# Next Action

Run independent EvidenceGate review for TASK-0023 using current `state_version` after the producer moves the task to `review`.

# Notes

PlanIR, scheduling, Evidence v2 execution, and dynamic Claim generation are intentionally deferred by TASK-0023 non-goals.
