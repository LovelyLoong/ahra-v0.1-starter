---
type: Handoff
id: HANDOFF-TASK-0025-0001
schema_version: awkp/0.1
title: TASK-0025 layered verification ready for review
description: Producer handoff for VerificationSelection, DefectRecord, selective reverification, and completion-gate v2 implementation.
status: active
owner: agent:codex-dynamic-kernel-operator
source_refs: [../task.md, ../state.json, ../artifact-manifest.json, ../evidence-manifest.json]
evidence_refs: [EVD-TASK-0025-0001, EVD-TASK-0025-0002, EVD-TASK-0025-0003, EVD-TASK-0025-0004, EVD-TASK-0025-0005]
confidence: reviewed
last_verified_at: 2026-06-25T16:30:05+08:00
review_after: 2026-09-25T00:00:00Z
tags: [handoff, task-0025, dynamic-kernel, verification]
---

# Summary

TASK-0025 is implemented and ready for independent EvidenceGate review. The producing agent did not mark the task completed.

# Completed Work

- Added VerificationTrigger, VerificationSelection, VerificationResult, and DefectRecord schemas and examples.
- Added src/ahra/verification.py with deterministic reverse-dependency impact analysis, L0/L1/L2 gate wrappers, mandatory safety baseline selection, completion evaluation, and defect creation.
- Added VerificationServicePort without introducing provider SDK dependencies.
- Added tests for deterministic selection, failed/affected/integration/mandatory selection, evidence reuse by fingerprint, completion fail-closed states, defect records, selective fixture coverage, and old EvidenceGate fail-closed behavior.

# Verification

- uv run python -B -m unittest tests.test_verification tests.test_schemas -v: passed, 8 tests OK.
- uv run python -B scripts/lint_contracts.py: passed, 0 failures.
- uv run python -B scripts/check.py: passed, 100 tests OK.
- uv run python -B scripts/lint_awkp.py: passed, 0 errors and 0 warnings.
- git diff --check: passed with no output.

# Next Action

Run independent EvidenceGate review for TASK-0025 using current state_version after the producer moves the task to eview.

# Notes

Repair planning, arbitrary Agent node execution, and replacement of the existing task EvidenceGate path remain outside TASK-0025 scope.