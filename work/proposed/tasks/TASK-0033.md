---
type: WorkItem
id: TASK-0033
schema_version: awkp/0.1
title: Execute selected Gates and produce GateRun-backed Evidence
description: Replace selection-only verification with an actual GateRunner execution pipeline that blocks success when required Gates do not pass.
context_id: CTX-ahra-dynamic-kernel
priority: P0
risk_level: R2
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-26T00:00:00Z
depends_on: [TASK-0032]
input_refs:
  - ../../../docs/architecture/verification-system.md
  - ../../../docs/architecture/gate-execution-pipeline.md
  - ../../../src/ahra/verification.py
  - ../../../src/ahra/evidence_v2.py
  - ../../../src/ahra/plan_execution.py
  - ../../../src/ahra/ports.py
  - ../../../tests/test_dynamic_fixture.py
output_contract:
  - kind: gate_runner_port
  - kind: gate_runner_registry
  - kind: gate_execution_records
  - kind: gate_run_to_evidence_pipeline
  - kind: scheduler_gate_enforcement
  - kind: fixture_migration
  - kind: verification_report
---

# Goal

Make verification operational: every selected required Gate must actually run, produce a terminal GateRun, and create validated Evidence before a Node or Goal can succeed.

# Why now

The current path can calculate which Gates are affected, but selection is not execution. Continuing to repair, persist or expose the workflow before this boundary is real would preserve a false-success path.

# Scope

- Add provider-neutral GateExecutionRequest, GateExecutionResult, GateRunner and GateRunnerRegistry contracts.
- Add a VerificationExecutor service that executes a VerificationSelection and returns a structured report.
- Implement at least one deterministic command/check GateRunner for local tests.
- Create GateRunV2 and EvidenceV2 only from validated terminal GateExecutionResult values.
- Wire normal Node gates, explicit gate_verification nodes and goal_verification nodes through the same execution service.
- Replace direct or synthetic passed Evidence in the dynamic fixture with actual GateRunner output.
- Persist or publish GateRun/Evidence Artifact references through the current local store boundary.

# Non-goals

- Do not add SQLite persistence.
- Do not add generic Goal CLI commands.
- Do not introduce an LLM verifier as the only GateRunner.
- Do not redesign Capability Admission.
- Do not implement repair scheduling beyond changes required to consume actual Gate results.

# Architectural invariants

- VerificationSelection remains a pure selection decision.
- Only a GateRunner attempt may produce a new GateRun result.
- A selected required Gate without a runner fails closed.
- A Node cannot reach succeeded before its required terminal GateRuns pass.
- Completion cannot infer a passed Gate from an Evidence ID string.
- Gate retries append attempts and never overwrite prior GateRuns.

# Implementation slices

1. Define schemas and ports before scheduler integration.
2. Implement a deterministic GateRunner and registry.
3. Implement GateRun-to-Evidence conversion and validation.
4. Wire scheduler Node verification.
5. Wire L2 Goal verification.
6. Migrate the fixture and add negative tests.

# Acceptance criteria

- [ ] Every selected required Gate produces exactly one terminal GateRun per attempt or a structured execution failure.
- [ ] Every newly current Evidence record references the GateRun that produced it.
- [ ] A failed, blocked, timed-out, malformed or missing GateRunner result prevents the owning NodeRun from succeeding.
- [ ] A goal_verification node cannot pass when any required Claim lacks current passed Evidence produced by an executed Gate or validated reuse.
- [ ] The dynamic fixture no longer constructs final passed Evidence directly in host code.
- [ ] Tests distinguish selectedGateRefs, executedGateRunRefs and reusedEvidenceRefs.
- [ ] L0, L1 and L2 Gate paths have at least one passing and one failing test.
- [ ] Full local checks, schema lint and git diff checks pass.

# Required negative and adversarial cases

- selected Gate with no registered runner
- runner exception
- runner timeout
- malformed GateExecutionResult
- failed Gate followed by an attempted Node success transition
- Evidence whose gate_run_id does not exist
- verification command mutates governed workspace unexpectedly
- duplicate idempotency key

# Verification method

- python scripts/check.py
- python scripts/lint_awkp.py
- git diff --check
- targeted GateRunner unit tests
- scheduler test proving Gate failure blocks Node success
- dynamic fixture with actual GateRun assertions
- SG-5 executable-verification review

# Required metrics

- gate_execution_integrity
- unrun_gate_pass_count
- GateRun count by status and level
- Gate wall time and usage
- Evidence records with valid GateRun lineage / all new Evidence records

# Stop conditions

- Stop if any selected required Gate can still reach success without a GateRun.
- Stop if passed Evidence must still be hand-authored by fixture orchestration.
- Stop if the only implementation path couples Gate execution to one provider.

# Required evidence and handoff

- Publish an implementation/change report with exact files, contracts, schema
  versions, migrations, known limitations and unresolved items.
- Preserve deterministic command outputs or structured summaries with content
  digests.
- Map every acceptance criterion to one or more Evidence IDs.
- Record producer Agent Release, Context Manifest, workspace/branch, base
  commit, final commit or rejected patch.
- Publish the required metrics for this Task.
- Create an immutable Handoff with one exact next action when blocked, failed,
  paused or returned for changes.
- The producer must not mark this Task completed; an independent verifier and
  EvidenceGate decide completion.

# Rollback and compatibility

- Do not silently overwrite released contracts or historical events.
- Use a new schema version when field meaning changes or compatibility breaks.
- Keep legacy adapters explicit and outside the default path.
- A rollback must preserve Artifact/Evidence references and explain state
  projection changes.

# Risk and approvals

Risk level: **R2**. This changes completion and Node success semantics. Independent review must inspect both happy-path and failure transitions.
