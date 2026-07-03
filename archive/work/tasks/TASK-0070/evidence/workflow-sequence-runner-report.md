---
type: EvidenceReport
id: ART-TASK-0070-0002
schema_version: awkp/0.1
title: TASK-0070 WorkflowSequence runner report
description: Producer evidence for the WorkflowSequence schema, runner loop, CLI, and failure halt tests.
status: review
owner: agent:codex-implementation
created_at: 2026-06-30T10:00:00Z
created_by: agent:codex-implementation
---

# WorkflowSequence Runner Report

TASK-0070 implementation adds a multi-task workflow sequence runner that wraps existing governed components without replacing them.

Implemented:
- `contracts/schemas/workflow-sequence.schema.json` defines `WorkflowSequence` with task IDs, dependencies, optional request/report templates, and verification strategy.
- `src/ahra/workflow_sequence.py` loads sequences, orders tasks by dependency, claims ready tasks, starts GoalExecution, bridges to AWKP, and halts on failure.
- `ahra workflow-sequence run <sequence.yaml>` invokes the runner.
- `examples/workflows/phase1-sequence.yaml` lists TASK-0062 through TASK-0069, with simple verification for each task and comprehensive verification for TASK-0069.
- `examples/workflows/phase1-goal-request-template.yaml` is a task-scoped request template for materialized runs.

Failure behavior:
- The runner stops on a failed GoalExecution.
- The runner stops on non-completed bridge/orchestrator state.
- The default bridge operation fails closed with a clear blocker when the configured verifier report file is missing.
- The runner records the blocker in the returned result and does not silently continue.

Governed component boundary:
- Task state transitions use `AwkpTaskStateWriter`.
- Goal execution uses `GoalOperationService`.
- AWKP review uses `GoalAwkpBridge`, which invokes the existing task review orchestrator and EvidenceGate path.
- The runner introduces no new completion authority.
- Verifier reports remain explicit inputs; the runner does not synthesize EvidenceGate approval reports.

Verified:
- Unit tests cover schema/example validation, a two-task success chain, a real claim->Goal->bridge->completion path using existing governed components, missing verifier report fail-closed behavior, failure halt, and CLI dry-run invocation.
- `ahra workflow-sequence run examples/workflows/phase1-sequence.yaml --dry-run` orders TASK-0062..TASK-0069 correctly.
