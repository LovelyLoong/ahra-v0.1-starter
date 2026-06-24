---
type: Concept
id: DOCS-architecture-approval-service
schema_version: awkp/0.1
title: ApprovalService
description: Defines first-class approval records for scoped risky actions without requiring a human-facing UI.
status: active
owner: team:platform
source_refs: [../../architecture/SPEC.md, ../../contracts/schemas/approval.schema.json, ../../src/ahra/ports.py]
evidence_refs: [EVD-TASK-0010-0001]
confidence: reviewed
last_verified_at: 2026-06-24T10:25:00+08:00
review_after: 2026-09-22T00:00:00Z
tags: [architecture, approval, policy]
---

# Purpose

ApprovalService records authorization for a specific risky action. It answers a
different question from EvidenceGate:

- EvidenceGate: "May this task be marked complete?"
- ApprovalService: "May this specific action happen now?"

ApprovalService does not require a visual panel. In an AI-operated framework,
the AI can ask a human through conversation, then call an MCP tool that records
the human's decision as a structured approval object.

# Current Starter Status

The starter already has:

- an `ApprovalService` Port in `src/ahra/ports.py`;
- an `approval.schema.json` contract;
- `WorkflowResumeRequest` plan approval by artifact digest.

The starter does not yet have:

- a concrete ApprovalStore;
- a first-class approval lifecycle;
- policy integration that automatically creates approval requests;
- expiry handling;
- audit events for approval decisions beyond the narrow resume path.

# Approval Object

An approval must bind:

- approval ID;
- task ID and run ID;
- requested actor;
- approving actor;
- action;
- resource;
- parameter digest;
- preview artifact or diff;
- risk level;
- scope;
- expiry;
- decision and reason.

An approval must not be a broad permission like "allow this agent to do
anything." The scope must be narrow enough that another verifier can later
decide exactly what was authorized.

# Lifecycle

```text
requested
  -> approved
  -> consumed

requested
  -> rejected

requested
  -> expired

requested
  -> canceled
```

Consuming an approval should be idempotent and tied to the action digest. A
stale or already-consumed approval must not authorize a different action.

# AI-only Operation

For this project shape, the default operation path can be:

1. policy engine says approval is required;
2. framework emits an approval request artifact;
3. AI presents the request to the human in conversation;
4. human says approve or reject;
5. AI calls an MCP approval tool;
6. ApprovalService records the structured decision;
7. the waiting run resumes or fails.

No dashboard is required for this path. A dashboard can be added later as
another client over the same approval records.

# When To Implement

Implement ApprovalService when at least one of these becomes real scope:

- high-risk tool execution;
- deployment, publishing, deletion, spending, or external side effects;
- plan approval beyond the current file-backed resume contract;
- multi-run or delayed approvals;
- audit requirements for who authorized what and when.

Until then, keep it documented and do not add a partial service that duplicates
the current `WorkflowResumeRequest` path without stronger semantics.

## TASK-0010 Decision

TASK-0010 explicitly defers ApprovalService implementation. The current starter
does not yet have a unique concrete non-plan R2/R3 action that needs a scoped
authorization object. EvidenceGate completion and task-level human review are
separate governance mechanisms, not ApprovalService triggers by themselves.

The missing trigger is a real action such as high-risk tool execution,
deployment, publishing, deletion, spending, external service calls, writing
outside the normal workspace, approval beyond the current file-backed resume
contract, multi-run or delayed approvals, or a concrete audit requirement for
who authorized one specific action.
