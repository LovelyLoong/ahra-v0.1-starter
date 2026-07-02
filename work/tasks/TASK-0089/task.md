---
type: WorkItem
id: TASK-0089
schema_version: awkp/0.1
title: "Physically archive completed tasks and superseded documents"
description: "Reduce default-context entropy: move completed task directories TASK-0001 through TASK-0080 to archive/work/tasks/ and documents whose authority-map status is superseded or archived to archive/docs/, replace them with a digest in work/index.md, and update the authority map and docs index so archived material is trace-only. Git history remains the audit authority. Executed by Workflow B alone through examples/goals/task-0089-entropy-archive.yaml."
context_id: "CTX-self-hosting-loop"
priority: "P1"
risk_level: "R1"
requester: "human:maintainer"
reviewer: "agent:independent-verifier"
created_at: 2026-07-02T04:07:15.217817Z
depends_on: ["TASK-0085"]
input_refs: ["work/index.md", "docs/architecture/authority-map.md", "docs/index.md", "examples/goals/task-0089-entropy-archive.yaml"]
output_contract:
  - kind: "ahra/artifact/doc-change/0.1"
  - kind: "ahra/evidence/test-report/0.1"
---

# Goal

Reduce default-context entropy: move completed task directories TASK-0001 through TASK-0080 to archive/work/tasks/ and documents whose authority-map status is superseded or archived to archive/docs/, replace them with a digest in work/index.md, and update the authority map and docs index so archived material is trace-only. Git history remains the audit authority. Executed by Workflow B alone through examples/goals/task-0089-entropy-archive.yaml.

# Acceptance criteria

- [ ] work/tasks contains only TASK-0081 and later; TASK-0001 through TASK-0080 directories are moved unmodified to archive/work/tasks/ with state.json and events.jsonl byte-identical.
- [ ] work/index.md lists live tasks plus a one-line digest table for archived tasks with their final state, and every remaining relative link resolves.
- [ ] Documents with authority-map status superseded or archived are moved to archive/docs/, the authority map and docs/index.md are updated, and uv run python -B scripts/check.py --lint passes.
- [ ] The change is produced by a Workflow B development-bounded GoalExecution with kernel-derived completion, then approved through the AWKP EvidenceGate by an independent verifier.
