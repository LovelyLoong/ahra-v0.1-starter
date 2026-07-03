# HANDOFF-0001 — TASK-0090 A→B run blocked at Workflow A draft stage

**From**: agent:alignment-session (operator driving the first real A→B loop)
**Date**: 2026-07-03
**Task state at handoff**: working v1 (claimed, not completed)

## What was attempted

TASK-0090 is the Phase S milestone: drive one real project improvement end-to-end
through a real-driver Workflow A alignment session into Workflow B execution.

Chosen improvement (aligned with maintainer): promote the "new work defaults to
the Workflow A+B loop; any manual path is a loop defect" rule from an aside in the
Increment F execution note into an explicit, standalone binding-rule section of
`docs/roadmaps/development-program-overview.md` (satisfies TASK-0090 criterion 3,
and is small enough for the development-bounded ≤30-file / ≤800-line policy gate).

## Progress through Workflow A (real codex-python-sdk driver)

1. `workflow-a start` — session materialized, workspaceRef resolved to repo root
   `E:\ahra-v0.1-starter` (correct; avoids the TASK-0086 nested-workspace defect). OK.
2. `workflow-a advance` — real Alignment Agent converged in one turn, produced a
   faithful `frozenRequirement`, stage → `awaiting_requirement_approval`. OK.
   **This validates the real-driver alignment path, previously unproven.**
3. `workflow-a approve-requirement --actor human:maintainer` — Human Gate 1,
   stage → `frozen`, approver distinct from producer. OK.
4. `workflow-a draft` — **FAILED deterministically (twice)**:
   `ClaimGraph apiVersion must be ahra.dev/v1alpha1`.

## Blocker

See `work/defects/DEF-wf-a-draft-contract-apiversion.md`.

Root cause: `_output_contract` (`src/ahra/alignment_session.py:614-622`) declares
the nested `claimGraph` (and `planDraft`) only as `{"type": "object"}`, so the
real Agent is never told to emit `apiVersion`/`kind`/`claims`, but the parser
(`acceptance_contracts.py:130`, `plan_ir.py:283`) hard-requires `apiVersion`.
The defect was masked because `workflow-a draft` had only ever run against the
deterministic `WorkflowAFixtureDriver`, never a real Agent.

TASK-0090's A→B loop cannot complete until this Workflow A contract defect is
fixed. The fix touches Workflow A's own code, which — per the maintainer's
explicit "do not intervene in the workflow" instruction — was NOT applied. No
workflow/kernel code and no Agent output were modified.

## Next action for maintainer

Decide remediation for DEF-wf-a-draft-contract-apiversion (correct the two
output contracts + add a real-driver regression test), then re-run the A→B loop
from `workflow-a draft` using the existing frozen session
(`work/tasks/TASK-0090/runs/loop-001/session.json`, stage `frozen`).

## Faithful status

TASK-0090 is NOT complete. It remains `working`, honestly reflecting that the
A→B loop is blocked at the A stage by a real, newly discovered Workflow A defect.
