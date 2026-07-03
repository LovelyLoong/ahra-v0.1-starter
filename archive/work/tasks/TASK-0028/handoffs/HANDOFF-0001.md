---
type: Handoff
id: HANDOFF-TASK-0028-0001
schema_version: awkp/0.1
title: TASK-0028 bounded_task executor ready for review
description: Producer handoff for NodeExecutor contracts, bounded_task executor, standard-harness compatibility adapter, NodeRun records, and tests.
status: active
owner: agent:codex-dynamic-kernel-operator
source_refs: [../task.md, ../state.json, ../artifact-manifest.json, ../evidence-manifest.json]
evidence_refs: [EVD-TASK-0028-0001, EVD-TASK-0028-0002, EVD-TASK-0028-0003, EVD-TASK-0028-0004]
confidence: reviewed
last_verified_at: 2026-06-25T18:37:18+08:00
review_after: 2026-09-25T00:00:00Z
tags: [handoff, task-0028, node-executor, bounded-task]
---

# Summary

TASK-0028 implementation is ready for independent verifier review and EvidenceGate. The producing agent did not mark the task completed.

# Completed Work

- Added provider-neutral NodeExecutor request/result contracts and immutable release registry.
- Added bounded_task executor over PlanIR PlanNodeIR and runtime CapabilityGrants.
- Routed deterministic command execution and changed-file authorization through LocalRuntimeGateway.
- Kept standard-harness as a compatibility adapter that builds a one-node PlanIR and calls the same executor service.
- Added NodeRun schema/example and tests for native execution, compatibility equivalence, capability denial, semantic gate selection, and provider-SDK boundary checks.

# Verification

- uv run python -B -m unittest tests.test_node_executor -v: passed, 6 tests OK.
- uv run python -B scripts/check.py: passed, 124 tests OK with 1 Windows symlink privilege skip.
- uv run python -B scripts/lint_contracts.py: passed, 0 AHRA lint failures.
- uv run python -B scripts/lint_awkp.py: passed, 0 errors and 0 warnings.
- git diff --check: passed with no output.

# Next Action

Run independent EvidenceGate review for TASK-0028 at the current state_version after the producer moves the task to review.
