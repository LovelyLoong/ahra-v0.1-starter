---
type: WorkIndex
id: WORK-index
schema_version: awkp/0.1
title: Work index
description: Generated-style view of current tasks; task state files remain authoritative in filesystem mode.
status: active
owner: harness:dispatcher
source_refs: [tasks/TASK-0001/state.json, tasks/TASK-0002/state.json, tasks/TASK-0003/state.json, tasks/TASK-0004/state.json, tasks/TASK-0005/state.json, tasks/TASK-0006/state.json, tasks/TASK-0007/state.json, tasks/TASK-0008/state.json, tasks/TASK-0009/state.json, tasks/TASK-0010/state.json, tasks/TASK-0011/state.json, tasks/TASK-0012/state.json, tasks/TASK-0013/state.json]
evidence_refs: []
confidence: verified
last_verified_at: 2026-06-23T11:29:09+08:00
review_after: 2026-09-22T00:00:00Z
tags: [work, index]
---

# Tasks

| Task | State | Owner | Next action |
|---|---|---|---|
| [TASK-0001](tasks/TASK-0001/task.md) | ready | unassigned | Claim with CAS and run baseline lint |
| [TASK-0002](tasks/TASK-0002/task.md) | review | unassigned | Verifier reruns workflow module fusion checks |
| [TASK-0003](tasks/TASK-0003/task.md) | review | unassigned | Verifier reruns port, descriptor, registry, and invocation probes |
| [TASK-0004](tasks/TASK-0004/task.md) | review | unassigned | Verifier reruns adapter, resume, MCP, and AWKP evidence checks |
| [TASK-0005](tasks/TASK-0005/task.md) | completed | unassigned | Completed by independent verification |
| [TASK-0006](tasks/TASK-0006/task.md) | completed | unassigned | Completed by EvidenceGate verifier approval |
| [TASK-0007](tasks/TASK-0007/task.md) | completed | unassigned | Completed by EvidenceGate verifier approval |
| [TASK-0008](tasks/TASK-0008/task.md) | completed | unassigned | Completed by EvidenceGate verifier approval. |
| [TASK-0009](tasks/TASK-0009/task.md) | queued | unassigned | Wait for TASK-0008 to complete, then align the default local runtime sandbox profile |
| [TASK-0010](tasks/TASK-0010/task.md) | queued | unassigned | Wait for TASK-0009 to complete, then select the first concrete ApprovalService trigger or explicitly defer |
| [TASK-0011](tasks/TASK-0011/task.md) | queued | unassigned | Wait for TASK-0010 to complete, then define the durable control plane boundary or defer trigger |
| [TASK-0012](tasks/TASK-0012/task.md) | queued | unassigned | Wait for TASK-0010 to complete, then decide whether scaffold helper has unique value |
| [TASK-0013](tasks/TASK-0013/task.md) | queued | unassigned | Wait for TASK-0010 to complete, then decide whether optional CI gates have one concrete wrapper target |
