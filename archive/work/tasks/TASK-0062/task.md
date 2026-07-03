---
type: WorkItem
id: TASK-0062
schema_version: awkp/0.1
title: IntentDraft contract with declared scope and capability-need
description: Define the IntentDraft schema and domain object that captures a human's abstract Goal plus declared scope and capability needs, so out-of-envelope directions can be rejected early with explanation.
context_id: CTX-phase1-intent-closure
priority: P0
risk_level: R2
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-30T10:00:00Z
depends_on: [TASK-0061]
input_refs:
  - ../../../contracts/schemas/goal-execution-request.schema.json
  - ../../../src/ahra/goal_operations.py
  - ../../../docs/roadmaps/phase1-minimal-loop-intent-roadmap.md
output_contract:
  - kind: intent_draft_contract_report
  - kind: verification_summary
  - kind: handoff
---

# Goal

Open the input boundary contract. Define `IntentDraft` as the human-authored
entry point: an abstract Goal statement plus constraints, declared capability
needs, and context. This lets the alignment workflow (TASK-0063) know what it is
drafting toward, and lets out-of-envelope requests (e.g. requiring capabilities
not yet governed) be rejected early with a structured reason.

# Scope

- Add `contracts/schemas/intent-draft.schema.json` defining IntentDraft with:
  abstract goal text, constraints, declared capability needs
  (filesystem/network/etc), context, optional priority/risk hints.
- Implement the domain object `IntentDraft` in `src/ahra/intent_draft.py` that
  round-trips from the schema.
- Add an example `examples/intents/phase1-example-intent.yaml` validated by the
  schema.
- Register the example in `scripts/lint_contracts.py` MAPPINGS.

# Non-goals

- Do not implement the alignment workflow engine here (that is TASK-0063).
- Do not implement capability admission here (that comes in later tasks).
- Do not self-complete this task; EvidenceGate decides completion.

# Acceptance criteria

- [ ] `contracts/schemas/intent-draft.schema.json` exists, defines IntentDraft
  with abstract goal, constraints, and declared capabilities, and is
  backward-compatible (additiveProperties allowed).
- [ ] `IntentDraft` domain object in `src/ahra/intent_draft.py` round-trips from
  schema via `from_mapping()`, covered by a unit test.
- [ ] `examples/intents/phase1-example-intent.yaml` validates against the schema
  and is registered in `scripts/lint_contracts.py` MAPPINGS.
- [ ] The domain module imports no adapter/model/cloud dependency (lint passes).
- [ ] Unit tests, lint, and diff checks pass: `.\.venv\Scripts\python.exe -B -m
  unittest tests.test_intent_draft -v` and `.\.venv\Scripts\python.exe -B
  scripts\check.py --lint` green.
- [ ] Producer moves TASK-0062 only to review; EvidenceGate decides completion.

# Verification method

- .\.venv\Scripts\python.exe -B -m unittest tests.test_intent_draft -v
- .\.venv\Scripts\python.exe -B scripts\check.py --lint
- git diff --check

# Required evidence and handoff

- Publish `evidence/intent-draft-contract-report.md` describing the schema, the
  domain round-trip, and the example intent.
- Publish `evidence/verification-summary.json`.
- Publish `handoffs/HANDOFF-0001.md` with one exact next action for TASK-0063.
