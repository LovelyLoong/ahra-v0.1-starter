---
type: Architecture
id: ARCH-gate-execution-pipeline
schema_version: awkp/0.1
title: Gate execution pipeline
description: Defines the difference between Gate selection and Gate execution and the only valid path from a declared Gate to current Evidence.
status: proposed
owner: team:quality
source_refs:
  - verification-system.md
  - ../../src/ahra/verification.py
  - ../../src/ahra/evidence_v2.py
  - ../../src/ahra/plan_execution.py
evidence_refs: []
confidence: draft
last_verified_at: 2026-06-26T00:00:00Z
review_after: 2026-09-26T00:00:00Z
tags: [architecture, verification, gate, evidence]
---

# Summary

`VerificationSelection` is a planning decision. It is not verification.

A Gate is satisfied only after a registered GateRunner executes the exact Gate
definition in an admitted environment and produces a terminal GateRun. Evidence
may be created from that GateRun only after output validation and fingerprint
binding.

# Required object flow

```text
VerificationTrigger
        ↓
VerificationSelection
        ↓
GateExecutionRequest
        ↓
GateRunnerRegistry
        ↓
GateRunner
        ↓
GateExecutionResult
        ↓
GateRunV2
        ↓
EvidenceV2
        ↓
EvidenceRegistry
```

# Proposed interfaces

```python
class GateRunnerPort(Protocol):
    gate_kind: str
    release_ref: str

    async def run(
        self,
        request: GateExecutionRequest,
    ) -> GateExecutionResult: ...


class GateRunnerRegistryPort(Protocol):
    def register(self, runner: GateRunnerPort) -> None: ...
    def resolve(self, gate_kind: str, release_ref: str) -> GateRunnerPort: ...


class VerificationExecutorPort(Protocol):
    async def execute_selection(
        self,
        selection: VerificationSelection,
        context: VerificationExecutionContext,
    ) -> VerificationExecutionReport: ...
```

# GateExecutionRequest minimum fields

- `goal_execution_id`
- `plan_execution_id`
- optional `node_run_id`
- `gate_ref`
- `gate_definition_digest`
- `claim_refs`
- immutable subject refs and digests
- dependency Evidence refs and fingerprints
- runtime profile ref and digest
- policy ref and digest
- verifier release ref and digest
- test definition ref and digest
- command or semantic input contract
- deadline and budget
- idempotency key
- workspace or Artifact refs
- trust labels for all external inputs

# GateExecutionResult minimum fields

- terminal status: `passed | failed | blocked | error | timed_out | canceled`
- started/completed timestamps
- normalized command or verifier identity
- Artifact refs
- observed subject digests
- usage and cost
- failure class
- concise reason
- raw-output Artifact ref where policy allows
- no private chain of thought

# Enforcement rules

1. A selected required Gate without a registered runner fails closed.
2. A Gate cannot be marked passed from a declared Evidence ID alone.
3. Every current Evidence record must reference one terminal GateRun.
4. GateRun must bind the exact Gate definition digest.
5. GateRun must bind the exact test/verifier/runtime/policy environment.
6. A Node with required Gates may enter `succeeded` only after all required
   GateRuns pass.
7. A goal verification node may pass only after Completion sees current passed
   Evidence for every required Claim.
8. Gate retry creates a new GateRun attempt; it never overwrites history.
9. Reused Evidence is not a new GateRun. The reuse decision must be recorded in
   VerificationSelection and validated by EvidenceRegistry.
10. Verification commands that mutate the governed workspace fail the Gate
    unless mutation is explicitly part of an isolated test fixture contract.

# Layer semantics

## L0

Purpose: cheap local rejection.

Typical runners:

- schema validation;
- path and change-size policy;
- syntax/static checks;
- targeted unit tests;
- output contract validation.

L0 normally does not need an LLM.

## L1

Purpose: protect an integration or risk boundary.

Typical runners:

- affected integration tests;
- API contract tests;
- security policy tests;
- independent semantic review for non-deterministic outputs.

L1 is selected based on dependency impact and risk.

## L2

Purpose: decide Goal completion.

L2 does not need to re-run every Gate. It must:

- inspect every required Claim;
- resolve the current Evidence set;
- reject missing, failed, blocked, stale, expired, revoked, contradicted, or
  uncovered Claims;
- reject open Defects;
- record every reused current Evidence ref and every historical excluded
  Evidence ref separately;
- run mandatory safety baselines required by policy.

# Idempotency

A Gate attempt idempotency key should bind:

```text
goal_execution_id
plan_execution_id
node_run_id or goal scope
gate_ref
gate_definition_digest
subject digests
test_definition_digest
verifier_release_digest
attempt
```

The same key must not create duplicate side effects or conflicting GateRuns.

# Metrics

Every verification report should include:

- selected Gate count;
- executed Gate count;
- reused Evidence count;
- failed/blocked/error count;
- wall time per Gate;
- model/tool/token/cost usage;
- full-baseline estimated or measured cost;
- weighted verification saving;
- Gate cache/reuse hit ratio;
- invalidated Evidence count and reasons.

# Failure handling

A failed Gate produces a `VerificationResult`. A Defect may be derived only from
a terminal failed/blocked Gate result with:

- exact expected and actual outcome;
- direct Claim refs for the immediate failed contract;
- affected Claim refs from deterministic reverse dependency closure or an
  independently validated equivalent;
- reproduction;
- subject refs/digests;
- repair boundary;
- failure class;
- GateRun ref.

# Compatibility

Legacy task Evidence without GateRun lineage remains `legacy_partial`. It may
support historical AWKP review but must not be silently promoted into current
M1 Goal Evidence.
