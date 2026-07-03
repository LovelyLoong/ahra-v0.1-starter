---
type: Handoff
id: HANDOFF-TASK-0007-0001
schema_version: awkp/0.1
title: TASK-0007 verifier handoff
description: Handoff for reviewing the local EvidenceGate implementation.
status: active
owner: agent:codex
task_id: TASK-0007
context_id: CTX-ahra-evidence-gate
artifact_refs: [ART-TASK-0007-0001]
evidence_refs: [EVD-TASK-0007-0001]
created_at: 2026-06-22T23:37:34+08:00
review_after: 2026-09-22T00:00:00Z
tags: [handoff, verification, evidence-gate]
---

# Summary

TASK-0007 is in `review`. It implements the local EvidenceGate path but does
not mark itself completed.

# Review focus

- Confirm `src/ahra/evidence_gate.py` fails closed for stale state versions,
  malformed or missing evidence, hash mismatches, and producer self-review.
- Confirm `ahra.evidence_gate_evaluate` in MCP calls the same service rather
  than duplicating state mutation logic.
- Confirm the CLI and tests match `docs/architecture/evidence-gate.md`.
- Rerun `python scripts\check.py`, `python scripts\lint_awkp.py`, and
  `git diff --check`.

# Files to inspect

- `src/ahra/evidence_gate.py`
- `src/ahra/mcp_server.py`
- `tests/test_evidence_gate.py`
- `docs/architecture/evidence-gate.md`
- `docs/architecture/reference-runtime-adapters-and-mcp.md`
- `work/tasks/TASK-0007/evidence/evidence-gate-implementation-report.json`

