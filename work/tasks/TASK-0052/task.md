---
type: WorkItem
id: TASK-0052
schema_version: awkp/0.1
title: Add GateDefinition command-gate contract and verification-teeth ADR
description: Extend the GateDefinition contract with a command-gate expectation field, parse command and expectation in the domain object, and record an ADR establishing the command gate as the default verification engine.
context_id: CTX-verification-teeth
priority: P0
risk_level: R2
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-29T10:00:00Z
depends_on: []
input_refs:
  - ../../../contracts/schemas/gate-definition.schema.json
  - ../../../contracts/schemas/gate-execution-request.schema.json
  - ../../../src/ahra/acceptance_contracts.py
  - ../../../scripts/lint_contracts.py
  - ../../../architecture/SPEC.md
  - ../../../docs/architecture/authority-map.md
output_contract:
  - kind: contract_schema_change_report
  - kind: verification_summary
  - kind: handoff
---

# Goal

Open the contract surface for a real command gate. The GateDefinition schema
already permits an optional `command`, but the domain object never parses it
and there is no `expectation` to judge a command result against. This task adds
the `expectation` field, makes the domain parse both fields, ships an example
record under lint, and records the architecture decision that the command gate
is the default verification engine while the deterministic gate becomes a
fixture/CI baseline and the AWKP gate becomes an evidence-lineage reviewer.

# Scope

- Add an optional `expectation` object to `contracts/schemas/gate-definition.schema.json`
  (at minimum an expected exit code; optionally an output-match rule), as an
  additive optional field within the existing `v1alpha1` profile.
- Parse `command` (already in schema) and `expectation` in the `GateDefinition`
  domain object in `src/ahra/acceptance_contracts.py`.
- Add an example `examples/records/gate-definition.json` that exercises
  `command` + `expectation`, and register it in `scripts/lint_contracts.py`
  `MAPPINGS` (or confirm the existing record covers it).
- Write an ADR (under `docs/decisions/` or `architecture/decisions/`) recording:
  command gate = default verification engine; DeterministicGateRunner = fixture
  / CI baseline; AWKP EvidenceGate = reviewer of kernel evidence lineage.
- Correct the drift in `architecture/SPEC.md` so it no longer presents
  `standard-harness` / `loop-engineering` as the recommended path.

# Non-goals

- Do not implement the CommandGateRunner here (that is TASK-0053).
- Do not change completion logic or the AWKP gate here.
- Do not change the meaning of existing fields, delete fields, or tighten enums
  (that would require a new schema version).
- Do not self-complete this task; EvidenceGate decides completion.

# Acceptance criteria

- [ ] `contracts/schemas/gate-definition.schema.json` defines an optional
  `expectation` object including an expected exit code (and optional output
  match), and remains backward compatible so every pre-existing example still
  validates.
- [ ] The `GateDefinition` domain object in `src/ahra/acceptance_contracts.py`
  exposes `command` and `expectation`, and round-trips from a record through
  `from_mapping` without loss, covered by a unit test.
- [ ] `examples/records/gate-definition.json` includes `command` and
  `expectation` and is validated by `scripts/lint_contracts.py` (present in
  `MAPPINGS`).
- [ ] An ADR exists that states the command gate is the default verification
  engine, the deterministic gate is a fixture/CI baseline, and the AWKP gate is
  an evidence-lineage reviewer.
- [ ] `architecture/SPEC.md` no longer recommends `standard-harness` or
  `loop-engineering` as the default/recommended path.
- [ ] `src/ahra/acceptance_contracts.py` imports no adapter/model/cloud
  dependency (domain-import ban holds).
- [ ] Targeted tests, lint, and diff checks pass, or any failure is recorded as
  a blocker with exact command output.
- [ ] Producer moves TASK-0052 only to review; EvidenceGate decides completion.

# Verification method

- .\.venv\Scripts\python.exe -B -m unittest tests.test_acceptance_contracts -v
- .\.venv\Scripts\python.exe -B scripts\check.py --lint
- git diff --check

# Required evidence and handoff

- Publish `evidence/contract-schema-change-report.md` describing the schema
  diff, compatibility argument, and the ADR location.
- Publish `evidence/verification-summary.json`.
- Publish `handoffs/HANDOFF-0001.md` with one exact next action for TASK-0053.
