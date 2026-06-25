---
type: Handoff
id: HANDOFF-TASK-0025-0002
schema_version: awkp/0.1
title: TASK-0025 fingerprint reuse repair ready for review
description: Producer handoff for the EvidenceGate request_changes repair on criterion 3.
status: active
owner: agent:codex-dynamic-kernel-operator
source_refs: [../task.md, ../state.json, ../artifact-manifest.json, ../evidence-manifest.json, ../evidence/evidence-gate-report-5.json]
evidence_refs: [EVD-TASK-0025-0007, EVD-TASK-0025-0008, EVD-TASK-0025-0009]
confidence: reviewed
last_verified_at: 2026-06-25T16:52:00+08:00
review_after: 2026-09-25T00:00:00Z
tags: [handoff, task-0025, repair, evidence-reuse]
---

# Summary

TASK-0025 request_changes has been addressed and is ready for independent EvidenceGate review. The producing agent did not mark the task completed.

# Completed Repair

- select_gates() now reuses Evidence only when stored_fingerprint exists and equals the canonical evidence.fingerprint().
- Current passed Evidence without stored_fingerprint is treated as stale for selection and receives fingerprint_not_matched:<evidence_id> rationale.
- tests/test_verification.py now covers EVD-no-stored-fingerprint, matching the independent verifier probe.

# Verification

- uv run python -B -m unittest tests.test_verification tests.test_schemas -v: passed, 8 tests OK.
- PowerShell probe with no stored fingerprint: passed; reusedEvidenceRefs=[], staleEvidenceRefs=[EVD-no-stored-fingerprint].
- uv run python -B scripts/check.py: passed, 100 tests OK.
- uv run python -B scripts/lint_awkp.py: passed, 0 errors and 0 warnings.
- git diff --check: passed with no output.

# Next Action

Run independent EvidenceGate review for TASK-0025 using current state_version after the producer moves the task to review.
