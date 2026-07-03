---
type: Handoff
id: HANDOFF-TASK-0027-0001
schema_version: awkp/0.1
title: TASK-0027 capability admission ready for review
description: Producer handoff for capability admission, default-deny local runtime gateway, contracts, and security tests.
status: active
owner: agent:codex-dynamic-kernel-operator
source_refs: [../task.md, ../state.json, ../artifact-manifest.json, ../evidence-manifest.json]
evidence_refs: [EVD-TASK-0027-0001, EVD-TASK-0027-0002, EVD-TASK-0027-0003, EVD-TASK-0027-0004]
confidence: reviewed
last_verified_at: 2026-06-25T18:01:11+08:00
review_after: 2026-09-25T00:00:00Z
tags: [handoff, task-0027, capabilities, security]
---

# Summary

TASK-0027 implementation is ready for independent security review and EvidenceGate. The producing agent did not mark the task completed.

# Completed Work

- Added runtime CapabilityRequest, CapabilityGrant and CapabilityAuditRecord models and schemas.
- Added CapabilityAdmissionService with Goal/Policy scope intersection, approval checks, high-risk fail-closed behavior, role defaults and spawn-limit checks.
- Added LocalRuntimeGateway for filesystem writes and command execution with default-deny grant checks and audit records.
- Added provider-neutral CapabilityAdmissionPort and RuntimeGatewayPort.
- Documented local profile isolation guarantees and explicit non-guarantees.
- Added security tests for path traversal, symlink escape where supported, command substitution, stale grant, role mismatch, spawn limit, approval absence, command allowlists and audit completeness.

# Verification

- uv run python -B -m unittest tests.test_capabilities -v: passed, 11 tests OK with 1 skip for unavailable Windows symlink privilege.
- uv run python -B -m unittest tests.test_capabilities tests.test_schemas tests.test_acceptance_contracts -v: passed, 24 tests OK with 1 skip for unavailable Windows symlink privilege.
- uv run python -B scripts/lint_contracts.py: passed, 0 AHRA lint failures.
- uv run python -B scripts/check.py: passed, 118 tests OK with 1 symlink privilege skip.
- uv run python -B scripts/lint_awkp.py: passed, 0 errors and 0 warnings.
- git diff --check: passed with no output.

# Next Action

Run independent EvidenceGate security review for TASK-0027 at the current state_version after the producer moves the task to review.
