---
type: WorkIndex
id: WORK-index
schema_version: awkp/0.1
title: Work index
description: Generated-style view of current tasks; task state files remain authoritative in filesystem mode.
status: active
owner: harness:dispatcher
source_refs: [tasks/TASK-0001/state.json, tasks/TASK-0002/state.json, tasks/TASK-0003/state.json, tasks/TASK-0004/state.json]
evidence_refs: []
confidence: verified
last_verified_at: 2026-06-22T09:37:04Z
review_after: 2026-09-22T00:00:00Z
tags: [work, index]
---

# Active tasks

| Task | State | Owner | Next action |
|---|---|---|---|
| [TASK-0001](tasks/TASK-0001/task.md) | ready | unassigned | Claim with CAS and run baseline lint |
| [TASK-0002](tasks/TASK-0002/task.md) | review | unassigned | Verifier reruns workflow module fusion checks |
| [TASK-0003](tasks/TASK-0003/task.md) | review | unassigned | Verifier reruns port, descriptor, registry, and invocation probes |
| [TASK-0004](tasks/TASK-0004/task.md) | review | unassigned | Verifier reruns adapter, resume, MCP, and AWKP evidence checks |
