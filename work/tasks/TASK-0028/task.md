---
type: WorkItem
id: TASK-0028
schema_version: awkp/0.1
title: Create the node executor registry and refactor standard-harness into bounded_task
description: Replace fixed workflow ownership with registered execution primitives that cannot complete the Goal by themselves.
context_id: CTX-ahra-dynamic-kernel
priority: P0
risk_level: R1
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-25T00:00:00Z
depends_on: [TASK-0027]
input_refs:
  - src/ahra/reference_runner/standard_harness.py
  - PlanIR contracts
  - capability gateway
  - verification service
output_contract:
  - kind: node_executor_protocol
  - kind: executor_registry
  - kind: bounded_task_executor
  - kind: compatibility_adapter
  - kind: node_artifact_evidence
  - kind: tests
---

# Goal

Preserve the useful bounded execution behavior while removing its role as a top-level fixed workflow.

# Scope

- Define NodeExecutor request/result contracts independent of provider SDKs.
- Implement registry resolution by immutable node type/release.
- Refactor path/size policy, isolated workspace, checks, review, retry and rollback into bounded_task executor components.
- Route all writes/commands through Capability Grants and the runtime gateway.
- Emit NodeRun, Artifact, Evidence, Gate and terminal failure records.
- Provide a temporary standard-harness compatibility adapter that constructs a one-node PlanIR or calls the same executor service.

# Non-goals

- Do not implement DAG scheduling.
- Do not allow bounded_task to mark Goal completed.
- Do not add new fixed Workflow Modules.

# Acceptance criteria

- [ ] bounded_task executes from a PlanNode and CapabilityGrant, not a bespoke WorkflowRunRequest path.
- [ ] The executor cannot update Goal/Task completed state.
- [ ] Deterministic checks are L0 Gates and semantic review is invoked only by declared Gate policy.
- [ ] Rollback and terminal failure preserve patch, command and error Evidence.
- [ ] Compatibility mode and native node mode produce equivalent observable Artifact/Evidence semantics.
- [ ] Provider-specific AgentDriver remains an adapter.

# Verification method

- python scripts/check.py
- bounded_task contract tests
- compatibility equivalence tests
- rollback/failure tests
- capability enforcement tests
- git diff --check

# Required evidence and handoff

- Publish an implementation/change report with exact files, contracts, migrations, known limitations, and unresolved items.
- Preserve deterministic command outputs or structured summaries with content digests.
- Map every acceptance criterion to one or more Evidence IDs.
- Record the producer Agent Release, Context Manifest, workspace/branch, base commit, and final commit or rejected patch.
- Create an immutable Handoff with one exact next action when blocked, failed, paused, or returned for changes.
- The producer must not mark this task completed; an independent verifier and EvidenceGate decide completion.

# Rollback and compatibility

- Do not silently overwrite released contracts or historical events.
- Use a new schema version when field meaning changes or compatibility is broken.
- Keep compatibility adapters until the task explicitly authorizes their removal.
- Any rollback must preserve Artifact/Evidence references and explain state projection changes.

# Risk and approvals

Risk level: **R1**. Do not delete standard-harness compatibility until TASK-0032.
