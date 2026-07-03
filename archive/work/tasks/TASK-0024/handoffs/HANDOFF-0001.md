---
type: Handoff
id: HANDOFF-TASK-0024-0001
schema_version: awkp/0.1
title: TASK-0024 Evidence v2 ready for review
description: Producer handoff for Evidence v2 validity, deterministic fingerprinting, invalidation, and legacy evidence manifest compatibility.
status: active
owner: agent:codex-dynamic-kernel-operator
source_refs: [../task.md, ../state.json, ../artifact-manifest.json, ../evidence-manifest.json]
evidence_refs: [EVD-TASK-0024-0001, EVD-TASK-0024-0002, EVD-TASK-0024-0003, EVD-TASK-0024-0004, EVD-TASK-0024-0005]
confidence: reviewed
last_verified_at: 2026-06-25T16:08:52+08:00
review_after: 2026-09-25T00:00:00Z
tags: [handoff, task-0024, dynamic-kernel, evidence-v2]
---

# Summary

TASK-0024 is implemented and ready for independent EvidenceGate review. The producing agent did not mark the task completed.

# Completed Work

- Added Evidence v2, GateRun v2, and EvidenceStatusEvent schemas and valid examples.
- Added src/ahra/evidence_v2.py with canonical fingerprinting, digest-bound Evidence/GateRun records, invalidation inspection, status events, and legacy AWKP evidence-manifest adaptation.
- Added EvidenceRegistryPort to src/ahra/ports.py without introducing provider SDK dependencies into domain or port layers.
- Added focused tests for canonical fingerprints, direct and transitive invalidation, unrelated changes, incomplete dependencies, policy/gate/runtime/test/verifier changes, TTL, revocation, contradiction, legacy manifest compatibility, and GateRun v2 digest/validity bindings.

# Verification

- uv run python -B -m unittest tests.test_evidence_v2 tests.test_schemas -v: passed, 12 tests OK.
- uv run python -B scripts/lint_contracts.py: passed, 0 failures.
- uv run python -B scripts/check.py: passed, 93 tests OK.
- uv run python -B scripts/lint_awkp.py: passed, 0 errors and 0 warnings.
- git diff --check: passed with no output.

# Next Action

Run independent EvidenceGate review for TASK-0024 using current state_version after the producer moves the task to eview.

# Notes

Existing EvidenceGate v1 task completion remains unchanged. Persistent EvidenceRegistry storage, Gate selection, and Defect repair are deferred to later tasks.