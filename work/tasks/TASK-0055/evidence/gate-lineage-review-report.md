---
type: Evidence
id: EVD-TASK-0055-0001
schema_version: awkp/0.1
title: TASK-0055 gate lineage review report
description: Producer evidence for offline EvidenceGate command evidence lineage checks.
status: review
owner: agent:codex-dynamic-kernel-operator
created_at: 2026-06-29T12:25:00Z
created_by: agent:codex-dynamic-kernel-operator
task_id: TASK-0055
---

# TASK-0055 gate lineage review report

## Summary

TASK-0055 upgrades the AWKP EvidenceGate approve path for command-backed
criteria. A passed command can no longer be accepted from self-reported
`command.status` alone. On approve, command evidence must be backed by kernel
`EvidenceV2` JSON and a linked `GateRunV2` JSON record.

The implementation remains offline and stdlib-only inside
`src/ahra/evidence_gate.py`.

## Lineage Checks

EvidenceGate now builds a local index from task artifact and evidence manifests:

- `Evidence` documents are indexed by `metadata.evidenceId`.
- `GateRun` documents are indexed by `metadata.gateRunId`.
- Non-kernel JSON documents remain valid legacy AWKP evidence but do not satisfy
  command-backed approval.

For a command-backed approval, EvidenceGate requires:

- The command entry has `evidence_refs`.
- Each referenced command evidence is a kernel `EvidenceV2` document.
- The `EvidenceV2` result is `passed`.
- The `EvidenceV2` validity state is `current`.
- The stored Evidence fingerprint matches the recomputed fingerprint.
- The Evidence has a `gateRunId`.
- The referenced `GateRunV2` exists.
- The GateRun `evidenceRef` points back to the Evidence.
- GateRun fields match Evidence lineage fields: gate ref, gate definition
  digest, result, claim refs, subjects, dependencies, and environment.
- The GateRun validity state is `current`.
- The GateRun has a non-empty command array.
- The stored GateRun fingerprint matches the recomputed fingerprint.

## Fail-Closed Cases

The tests cover both required fail-closed cases:

- A command-backed criterion that references legacy self-reported evidence
  instead of kernel EvidenceV2 raises `EvidenceGateError`.
- A command-backed criterion whose EvidenceV2 fingerprint is stale or mismatched
  raises `EvidenceGateError`.

Existing EvidenceGate protections remain in place: producer self-verification is
rejected, artifact/evidence SHA-256 values are recomputed from local files, CAS
`state_version` is enforced, and append-only events are still emitted for
approved or changes-requested decisions.

## Verification

- `uv run python -B -m unittest tests.test_evidence_gate -v`: passed, 9 tests.
- `uv run python -B scripts\lint_awkp.py`: passed.
- `uv run python -B scripts\check.py --lint`: passed.
- `git diff --check`: passed.
- Extra regression: `uv run python -B scripts\check.py --test`: passed, 221
  tests with 1 Windows symlink-permission skip.
