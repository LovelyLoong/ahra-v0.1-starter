---
type: Evidence
id: EVD-TASK-0059-0001
schema_version: awkp/0.1
title: TASK-0059 producer-to-verifier orchestrator report
description: Producer evidence for the AWKP task review orchestrator that chains governed review, EvidenceGate, and bounded changes-requested cycles.
status: active
owner: agent:codex-implementation
created_at: 2026-06-29T15:50:00Z
source_refs: [../task.md, ../state.json, ../../../src/ahra/orchestrator.py, ../../../src/ahra/awkp_state_writer.py, ../../../src/ahra/evidence_gate.py, ../../../src/ahra/cli.py, ../../../src/ahra/ports.py, ../../../tests/test_evidence_gate.py, ../../../tests/test_cli.py]
---

# Summary

TASK-0059 adds `AwkpTaskReviewOrchestrator` and the CLI wrapper `ahra task orchestrate-review`.

The orchestrator does not make completion decisions itself. It chains existing governed components:

- `AwkpTaskStateWriter.request_review` moves the producer-held task from `working` to `review`.
- `evaluate_task_gate` runs EvidenceGate under a verifier actor.
- `AwkpTaskStateWriter.reclaim_working` reclaims `changes_requested` tasks for the producer when another cycle is allowed.
- `AwkpTaskStateWriter.add_blocker` records a bounded-loop blocker when the cycle budget is exhausted.

# Producer And Verifier Boundary

The orchestrator fails closed before any state write when `producer_actor == verifier_actor`.

EvidenceGate still performs the authoritative producer identity check. The implementation keeps real producer identities from task manifests and `lease_acquired` or `artifact_published` events, while excluding EvidenceGate-generated `evidence_gate_report` records so a prior verifier report does not falsely make the verifier an implementation producer during re-review.

# Changes Requested Loop

The loop is finite. Each cycle requests review, invokes EvidenceGate, and stops on `completed`. On `changes_requested`, the orchestrator reclaims the task through the TASK-0057 writer and enters another review cycle only while `cycle < max_cycles`.

When `max_cycles` is reached, the task remains in `changes_requested` and a `blocker_added` event records the bounded-loop stop condition.

# Real Verification Dependency

The orchestrator calls the real EvidenceGate implementation. It does not synthesize an approval and does not bypass command-backed kernel EvidenceV2 lineage checks.

The hollow-gate regression test drives the orchestrator with an approve report that references non-kernel evidence for a command-backed criterion. EvidenceGate rejects it, and the task remains in `review` rather than being completed.

# Test Outcomes

Targeted tests cover:

- approved path: `working -> review -> completed`;
- identity conflict: producer/verifier equality fails before state change;
- changes-requested path: `working -> review -> changes_requested -> working -> review -> completed`;
- bounded loop: `max_cycles` exhaustion records a blocker;
- real-gate dependency: hollow command-backed evidence is rejected.

The required command results are recorded in `verification-summary.json`.
