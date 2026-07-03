---
type: Evidence
id: EVD-TASK-0057-0001
schema_version: awkp/0.1
title: TASK-0057 governed state writer implementation report
description: Producer evidence for the governed CAS writer for AWKP task state transitions.
status: active
owner: agent:codex-implementation
created_at: 2026-06-29T14:41:41Z
source_refs: [../task.md, ../state.json, ../../../src/ahra/awkp_state_writer.py, ../../../tests/test_evidence_gate.py]
---

# Summary

TASK-0057 adds `src/ahra/awkp_state_writer.py` as the governed producer-side writer for AWKP task state transitions.

# Implemented Surface

- `AwkpTaskStateWriter.acquire_working`: `ready -> working` with expected-version CAS, lease creation, and a unique fencing token.
- `AwkpTaskStateWriter.request_review`: `working -> review` with expected-version CAS and current lease holder/fencing-token validation.
- `AwkpTaskStateWriter.reclaim_working`: `changes_requested -> working` with expected-version CAS and previous fencing-token validation from append-only event history.
- `AwkpTaskStateWriterPort`: structural port boundary in `src/ahra/ports.py`.

# Governance Properties

- Each transition reads `state.json`, validates `state_version` against `expected_version`, and rejects stale writers with `AwkpTaskStateCasError`.
- Each transition appends an `events.jsonl` record with a unique `idempotency_key`; duplicates raise `AwkpTaskStateIdempotencyError`.
- Each transition uses a monotonic `occurred_at`; if the local clock is not ahead of the last event, the writer advances by one microsecond.
- Working states include a lease with `holder`, `fencing_token`, `acquired_at`, `heartbeat_at`, and `expires_at`.
- Conflicting or stale fencing tokens raise `AwkpTaskStateFenceError`.
- A per-task `.state-writer.lock` serializes local writers so concurrent attempts cannot silently clobber state.

# Verification

Final command results are recorded in `verification-summary.json`.

- `.\.venv\Scripts\python.exe -B -m unittest tests.test_evidence_gate -v`: exit code 0, 11 tests OK.
- `.\.venv\Scripts\python.exe -B scripts\lint_awkp.py`: exit code 0, AWKP lint 0 errors and 0 warnings.
- `.\.venv\Scripts\python.exe -B scripts\check.py --lint`: exit code 0, AHRA lint 0 failures.
- `git diff --check`: exit code 0. Git printed CRLF/LF normalization warnings for TASK-0057 state/events, with no whitespace errors.

# Review Boundary

The producer transition will move TASK-0057 only to `review`. Completion remains reserved for independent EvidenceGate approval.
