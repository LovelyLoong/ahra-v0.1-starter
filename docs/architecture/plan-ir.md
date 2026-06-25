---
type: Architecture
id: ARCH-plan-ir
schema_version: awkp/0.1
title: PlanDraft and PlanIR
description: Defines the untrusted planner output, trusted compilation, executable DAG, and validation rules.
status: active
owner: team:platform
source_refs:
  - ../../AHRA_dynamic_kernel_master_plan_2026-06-25.md
  - dynamic-agent-kernel.md
evidence_refs: []
confidence: reviewed
last_verified_at: 2026-06-25T00:00:00Z
review_after: 2026-09-25T00:00:00Z
tags: [planning, compiler, workflow, dag]
---

# Boundary

`PlanDraft` is model-generated intent. `PlanIR` is a trusted, immutable, executable contract produced by host code. The Scheduler never executes PlanDraft directly.

# PlanDraft minimum shape

```yaml
apiVersion: ahra.dev/v1alpha1
kind: PlanDraft
metadata:
  goalId: GOAL-doc-staleness
  proposedBy: REL-planner@sha256:...
spec:
  rationale: Implement parser, command, and tests as separate bounded nodes.
  nodes:
    - id: NODE-parse-doc-frontmatter
      nodeType: bounded_task
      objective: Add deterministic parsing for review_after.
      claimRefs: [CLAIM-frontmatter-parses]
      dependsOn: []
      inputRefs: [DOC-document-governance]
      expectedOutputs:
        - name: parser-change
          schemaRef: ahra/artifact/code-change/0.1
      capabilityRequests:
        - capability: filesystem.write
          resources: [src/ahra/document_health/**, tests/**]
      gateRefs: [GATE-parser-unit]
      budgetRequest:
        maxModelCalls: 20
        maxToolCalls: 60
```

# Compiled PlanIR additions

Compiler adds or normalizes:

- `planId`, `version`, `goalDigest`, `claimGraphDigest`;
- canonical node ordering and dependency edges;
- resolved Executor/Gate/Runtime references by immutable digest;
- approved Capability Grants;
- exact budgets and deadlines;
- input/output contracts and content digests;
- retry, timeout, compensation and cancellation semantics;
- stage and integration boundaries;
- expected Artifact/Evidence responsibilities;
- plan digest and compiler version;
- validation report reference.

# Validation rules

## Structural

- IDs are unique and stable.
- DAG is finite and acyclic.
- Every dependency and ref resolves.
- Every non-terminal output has a declared consumer or formal delivery role.
- Node type and Gate type are registered.
- Plan has at least one terminal Goal verification node.

## Acceptance coverage

- Every required Claim is assigned to one or more producing/verification nodes.
- No node may claim completion without a Gate.
- Security and governance Claims use mandatory Gate classes.
- Plan cannot delete or reinterpret Claim text.
- Every node output used as Evidence has a schema and immutable Artifact requirement.

## Security

- Capability request is no broader than Goal scope.
- Compiler cannot turn request into a broader grant.
- Reviewer nodes are read-only unless an explicit separate repair node is created.
- Planner nodes cannot receive write grants.
- Secret, network, production and irreversible capabilities require policy/approval.
- Spawn limits are finite and included in total budget.

## Runtime

- Timeouts are positive and consistent.
- Retry only applies to classified retryable failures.
- Non-idempotent effects cannot be retried without idempotency or compensation.
- Cancellation propagates to child NodeRuns.
- Checkpoint boundaries are declared before external waits or long phases.

# Node states

```text
pending -> ready -> admitted -> running -> verifying -> succeeded
                                  ├------> failed
                                  ├------> paused_input
                                  ├------> paused_auth
                                  ├------> timed_out
                                  └------> canceled
```

A failed node does not automatically retry. The retry policy and failure classifier decide whether to create a new attempt, create a Defect, replan, or escalate.

# Planner strategies

Planner strategy is an adapter behind a stable interface. Initial strategies:

- `fixture-static-planner`：deterministic test planner;
- `single-agent-planner`：one model produces PlanDraft;
- `planner-reviewer`：planner draft plus independent plan review;
- future domain planners.

All strategies produce the same PlanDraft and cannot bypass the compiler.

# Plan patching

Repair does not mutate PlanIR. It creates a `PlanPatchDraft` referencing:

- parent plan digest;
- Defect IDs;
- nodes to supersede;
- new or replacement nodes;
- unchanged nodes and Evidence intended for reuse.

Compiler emits a new full PlanIR version after validation.
