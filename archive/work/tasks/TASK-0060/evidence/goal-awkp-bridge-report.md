---
type: Evidence
id: EVD-TASK-0060-0001
schema_version: awkp/0.1
title: GoalExecution to AWKP task bridge report
description: Records how TASK-0060 associates a completed GoalExecution with an AWKP task and feeds kernel EvidenceV2/GateRun records into EvidenceGate.
status: current
owner: agent:codex-implementation
source_refs:
  - ../../../../src/ahra/goal_operations.py
  - ../../../../src/ahra/awkp_state_writer.py
  - ../../../../src/ahra/orchestrator.py
  - ../../../../src/ahra/evidence_gate.py
evidence_refs: []
confidence: high
last_verified_at: 2026-06-29T16:30:05Z
review_after: 2026-07-29T00:00:00Z
tags: [task-0060, goal-execution, awkp-task, evidencegate]
---

# Summary

TASK-0060 adds `GoalAwkpBridge` as the active GoalExecution to AWKP task bridge.
The bridge only accepts a `succeeded` GoalExecution, copies its materialized
kernel EvidenceV2 and GateRun records into the AWKP task evidence manifests,
records a `goal_awkp_associated` task event through the governed writer, and
then delegates review/completion to `AwkpTaskReviewOrchestrator`.

# Association Model

The durable association is recorded in two places:

- task event `goal_awkp_associated`, with `goal_execution_id` and `goal_status`;
- task-local `evidence/goal-awkp-association-<GEXEC>.json`, referenced by the
  task manifests.

The association event is CAS-protected, requires the current task lease holder,
and checks the current fencing token. It increments `state_version` without
changing the `working` lease, so the review orchestrator can immediately use
the same lease token to request review.

# Kernel Evidence Flow

`GoalOperationService.start` and `GoalOperationService.resume` now materialize
the in-memory `VerificationExecutor` records under the Goal artifact directory:

- `kernel-evidence/<EVD>.json`;
- `kernel-gate-runs/<GATERUN>.json`.

`GoalAwkpBridge` copies the GoalExecution's referenced EvidenceV2 records and
their matching GateRun documents into `work/tasks/<TASK-ID>/evidence/`, then
adds `kernel_evidence_v2` and `kernel_gate_run_v2` manifest records. The AWKP
EvidenceGate already validates command-backed criteria by checking that the
EvidenceV2 is current, passed, fingerprinted, and linked to a command-backed
GateRun.

# Authority Boundaries

The bridge is not a completion authority. It fails before state writes when the
producer and verifier actors are the same, requires a succeeded GoalExecution,
and invokes the TASK-0059 review orchestrator for `working -> review ->
EvidenceGate`. EvidenceGate remains the only component that can transition the
AWKP task to `completed`.
