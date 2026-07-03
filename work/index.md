---
type: WorkIndex
id: WORK-index
schema_version: awkp/0.1
title: Work index
description: Default live task index. Archived task records are trace-only under archive/work/tasks.
status: active
owner: harness:dispatcher
source_refs:
- tasks/TASK-0081/state.json
- tasks/TASK-0082/state.json
- tasks/TASK-0083/state.json
- tasks/TASK-0084/state.json
- tasks/TASK-0085/state.json
- tasks/TASK-0086/state.json
- tasks/TASK-0087/state.json
- tasks/TASK-0088/state.json
- tasks/TASK-0089/state.json
- tasks/TASK-0090/state.json
- tasks/TASK-0091/state.json
evidence_refs: []
confidence: verified
last_verified_at: 2026-07-02T00:00:00Z
review_after: 2026-09-25T00:00:00Z
tags: [work, tasks, dynamic-kernel]
---

# Work Index

Default work context lists only live task directories in `work/tasks/`.
TASK-0001 through TASK-0080 are archived unmodified under `archive/work/tasks/`
and are trace-only unless a current task, event, or evidence record references
them explicitly.

## Live Tasks

| Task | State | Owner | Version | Next action |
|---|---|---|---:|---|
| [TASK-0081](tasks/TASK-0081/task.md) | completed | unassigned | 3 | Completed by EvidenceGate verifier approval. |
| [TASK-0082](tasks/TASK-0082/task.md) | completed | unassigned | 3 | Completed by EvidenceGate verifier approval. |
| [TASK-0083](tasks/TASK-0083/task.md) | completed | unassigned | 3 | Completed by EvidenceGate verifier approval. |
| [TASK-0084](tasks/TASK-0084/task.md) | completed | unassigned | 3 | Completed by EvidenceGate verifier approval. |
| [TASK-0085](tasks/TASK-0085/task.md) | completed | unassigned | 3 | Completed by EvidenceGate verifier approval. |
| [TASK-0086](tasks/TASK-0086/task.md) | completed | unassigned | 3 | Completed by EvidenceGate verifier approval. |
| [TASK-0087](tasks/TASK-0087/task.md) | completed | unassigned | 3 | Completed by EvidenceGate verifier approval. |
| [TASK-0088](tasks/TASK-0088/task.md) | completed | unassigned | 3 | Completed by EvidenceGate verifier approval. |
| [TASK-0089](tasks/TASK-0089/task.md) | ready | unassigned | 0 | Task skeleton created; claim the task before producing evidence. |
| [TASK-0090](tasks/TASK-0090/task.md) | ready | unassigned | 0 | Task skeleton created; claim the task before producing evidence. |
| [TASK-0091](tasks/TASK-0091/task.md) | ready | unassigned | 0 | Task skeleton created; claim the task before producing evidence. |

## Archived Tasks

80 completed tasks (TASK-0001 through TASK-0080) have been archived to
`archive/work/tasks/` with their contract, authority state, evidence, and
handoffs preserved byte-identical. Git history remains the audit authority.

| Range | Count | Archive location |
|---|---:|---|
| TASK-0001 to TASK-0080 | 80 | [archive/work/tasks/](../archive/work/tasks/) |
