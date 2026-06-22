---
type: Concept
id: DOCS-architecture-evidence-gate
schema_version: awkp/0.1
title: EvidenceGate
description: Defines the verifier-side completion gate that turns task acceptance criteria and evidence into AWKP state transitions.
status: active
owner: team:platform
source_refs: [../../WORKFLOW.md, ../../SPEC.md, ../../src/ahra/ports.py]
evidence_refs: []
confidence: reviewed
last_verified_at: 2026-06-22T00:00:00Z
review_after: 2026-09-22T00:00:00Z
tags: [architecture, evidence, verifier]
---

# Purpose

EvidenceGate is the component that decides whether an AWKP Task may transition
from `review` to `completed` or `changes_requested`.

It closes the current manual gap: a producer can publish artifacts and evidence,
but the task should only complete when a distinct verifier maps every
acceptance criterion to checkable evidence.

# Non-goals

- It does not generate implementation evidence by itself.
- It does not weaken, delete, or reinterpret `task.md` acceptance criteria.
- It does not allow the producing agent to self-declare completion.
- It does not replace human approval for high-risk actions.
- It does not require a human-facing dashboard.

# Inputs

EvidenceGate reads:

- `work/tasks/<TASK-ID>/task.md`;
- `work/tasks/<TASK-ID>/state.json`;
- `work/tasks/<TASK-ID>/artifact-manifest.json`;
- `work/tasks/<TASK-ID>/evidence-manifest.json`;
- referenced evidence files;
- optional verifier command results;
- caller identity and expected state version.

# Outputs

EvidenceGate writes, through AWKP rules:

- a verifier report artifact;
- an evidence record for the report;
- an append-only event;
- a CAS-protected `state.json` transition.

Allowed decisions:

| Decision | State transition | Meaning |
|---|---|---|
| `approve` | `review` -> `completed` | Every acceptance criterion has sufficient evidence. |
| `request_changes` | `review` -> `changes_requested` | At least one acceptance criterion is missing, stale, or contradicted. |
| `reject_gate` | no task-state change | Gate inputs are malformed, stale, unauthorized, or not in a reviewable state. |

# Verification Rules

EvidenceGate must fail closed when:

- the task is not in `review`;
- the caller is the same producer identity and no independent verifier is
  recorded;
- `expected_version` does not match `state.json.state_version`;
- an evidence reference is missing, malformed, or hash-mismatched;
- an acceptance criterion has no matching evidence;
- command results are stale relative to the changed files they claim to verify;
- a completed transition would remove blockers without recording why.

EvidenceGate may accept checked boxes in `task.md` as a verifier annotation, but
checked boxes alone are never sufficient evidence.

# Minimal Local Implementation

The first implementation should be a local stdlib-only verifier command that can
also be called by MCP:

```text
python -m ahra.evidence_gate evaluate TASK-0007 \
  --expected-version 4 \
  --report work/tasks/TASK-0007/evidence/verifier-input.json \
  --actor agent:verifier
```

The command should:

1. load task state and manifests;
2. parse acceptance criteria from `task.md`;
3. require a verifier report that maps criteria to evidence refs;
4. validate artifact and evidence hashes;
5. optionally rerun configured checks;
6. append a gate event;
7. CAS-update state to `completed` or `changes_requested`.

The local command can remain file-backed. A later durable control plane can move
the same semantics behind SQLite/Postgres and MCP without changing the task
contract.

The verifier report is a JSON object with this minimum shape:

```json
{
  "schema_version": "ahra/evidence-gate-input/0.1",
  "task_id": "TASK-0007",
  "verifier": "agent:verifier",
  "decision": "approve",
  "summary": "Verifier mapped every criterion to evidence.",
  "criteria": [
    {
      "criterion_index": 1,
      "status": "passed",
      "evidence_refs": ["EVD-TASK-0007-0001"],
      "notes": "Checked."
    }
  ],
  "commands": [
    {
      "command": "python scripts\\check.py",
      "status": "passed"
    }
  ]
}
```

The local implementation accepts `criterion_index` or an exact normalized
`criterion` string. For `approve`, every criterion must be passed and reference
at least one known Evidence ID. For `request_changes`, at least one criterion
must be failed or missing.

# MCP Operation

MCP may expose EvidenceGate as an AI-facing operation surface:

- `ahra_evidence_gate_evaluate`;
- `ahra_evidence_gate_apply`;
- `ahra_task_inspect`.

MCP must not bypass schema validation, expected-version checks, event append, or
producer/verifier separation.

The current starter exposes `ahra.task_inspect` and
`ahra.evidence_gate_evaluate`. A separate apply tool is unnecessary in the
local profile because evaluate validates and applies the state transition in one
CAS-style operation.
