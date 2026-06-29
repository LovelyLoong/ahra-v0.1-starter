---
type: Evidence
id: EVD-TASK-0052-0001
schema_version: awkp/0.1
title: TASK-0052 contract schema change report
description: GateDefinition command-gate contract change, compatibility argument, and ADR location.
status: review
owner: agent:codex-dynamic-kernel-operator
created_at: 2026-06-29T10:20:00Z
created_by: agent:codex-dynamic-kernel-operator
task_id: TASK-0052
kind: contract_schema_change_report
---

# TASK-0052 contract schema change report

## Scope

TASK-0052 opens the GateDefinition contract for a real command gate. The
implementation changes only the contract surface, domain parser, examples,
tests, and architecture records. It does not implement CommandGateRunner and it
does not change AWKP completion logic.

## Schema diff

- `contracts/schemas/gate-definition.schema.json` now defines an optional
  `spec.expectation` object.
- `expectation.expectedExitCode` is required when `expectation` is present.
- `expectation.outputMatch` is optional and contains one match rule:
  `stream` is one of `stdout`, `stderr`, or `combined`, and `contains` is the
  required substring.
- Existing `spec.command` remains an optional command vector.

## Domain parsing

- `src/ahra/acceptance_contracts.py` now parses `GateDefinition.command` as a
  tuple of command arguments.
- It adds `CommandExpectation` and `CommandOutputMatch` domain value objects.
- `GateDefinition.to_mapping()` preserves the example record, including
  `name`, `subjectKinds`, `command`, and `expectation`.

## Compatibility argument

The new field is optional in the existing `ahra.dev/v1alpha1` profile. Existing
GateDefinition records that omit `command` and `expectation` remain valid. The
new unit test `test_gate_definition_expectation_is_backward_compatible`
validates this shape by removing both fields from the example record and
checking the schema still accepts it.

## Example and lint coverage

`examples/records/gate-definition.json` now includes both `command` and
`expectation`. The record was already registered in `scripts/lint_contracts.py`
`MAPPINGS`; `uv run python -B scripts/check.py --lint` validates it through the
same path.

## ADR

ADR location:

- `architecture/decisions/ADR-0008-command-gate-verification-engine.md`

The ADR records that the command gate is the default verification engine,
`DeterministicGateRunner` is a fixture and CI baseline, and AWKP EvidenceGate is
the reviewer of task evidence lineage.

## Architecture drift correction

`architecture/SPEC.md` no longer presents `standard-harness` or
`loop-engineering` as the default or recommended path. It now identifies the
governed dynamic kernel path as the recommended path and retains those workflow
modules only as legacy regression and migration compatibility inputs.
