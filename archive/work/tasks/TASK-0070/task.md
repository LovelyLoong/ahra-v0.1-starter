---
type: WorkItem
id: TASK-0070
schema_version: awkp/0.1
title: Multi-task workflow sequence runner
description: Build the WorkflowSequence definition format and WorkflowSequenceRunner that automatically orchestrates multiple AWKP tasks end-to-end (claim -> Goal execution -> bridge -> review -> completion) so Phase 1 and future increments can be executed as a single coherent workflow instead of manual per-task invocations.
context_id: CTX-workflow-infrastructure
priority: P0
risk_level: R2
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-30T10:00:00Z
depends_on: [TASK-0061]
input_refs:
  - ../../../src/ahra/orchestrator.py
  - ../../../src/ahra/goal_operations.py
  - ../../../src/ahra/cli.py
  - ../../../docs/roadmaps/phase1-minimal-loop-intent-roadmap.md
  - ../../../docs/roadmaps/development-program-overview.md
output_contract:
  - kind: workflow_sequence_runner_report
  - kind: verification_summary
  - kind: handoff
---

# Goal

Solve the "scattered parts" problem. Build a multi-task workflow orchestrator so
you can write a workflow definition (YAML) listing N tasks in sequence, then run
`ahra workflow-sequence run workflow.yaml` to automatically execute the entire
sequence: claim each task, execute its Goal, bridge to AWKP, trigger review, and
move to the next task. This makes Phase 1 (TASK-0062..0069) executable as a
single coherent workflow instead of 8 manual invocations.

# Scope

- Define `WorkflowSequence` format (YAML schema): list of task IDs, optional
  per-task Goal request templates, dependencies, verification strategy (per-task
  simple + final comprehensive).
- Implement `WorkflowSequenceRunner` in `src/ahra/workflow_sequence.py` that:
  - Iterates task IDs in dependency order
  - For each task: `ahra task claim` (if not claimed) -> execute Goal (from
    template or convention) -> `ahra goal bridge-awkp-task` (triggers 0059
    orchestrator) -> wait for task completion
  - On task failure: halt sequence, surface blocker
  - Per-task verification: simple (unit boundary)
  - Final task verification: comprehensive (integration)
- Add CLI: `ahra workflow-sequence run <sequence.yaml>`
- Keep runner domain-only (adapts existing CLI commands, no new side effects).

# Non-goals

- Do not replace the Goal kernel or AWKP orchestrator; this wraps them.
- Do not weaken any task verification boundary (each task still goes through
  EvidenceGate).
- Do not implement Goal request auto-generation here (Phase 1 provides that).
- Do not self-complete this task; EvidenceGate decides completion.

# Acceptance criteria

- [ ] `contracts/schemas/workflow-sequence.schema.json` defines WorkflowSequence
  with task list, dependencies, and optional per-task templates, and validates
  an example sequence.
- [ ] `WorkflowSequenceRunner` executes a multi-task sequence: claim -> Goal
  execution -> bridge -> completion for each task in order, covered by a test.
- [ ] On task failure, the runner halts and surfaces the blocker; it does not
  silently skip or continue, covered by a test.
- [ ] `ahra workflow-sequence run` CLI command exists and invokes the runner.
- [ ] Per-task verification remains simple (unit); final task verification
  remains comprehensive (as designed in TASK-0069).
- [ ] An example `examples/workflows/phase1-sequence.yaml` lists
  TASK-0062..0069 and validates against the schema.
- [ ] The runner depends only on existing governed components (task claim,
  Goal start, goal bridge-awkp-task, orchestrate-review); no new side effects.
- [ ] Unit tests, lint, and diff checks pass: `.\.venv\Scripts\python.exe -B -m
  unittest tests.test_workflow_sequence -v` and `.\.venv\Scripts\python.exe -B
  scripts\check.py --lint` green.
- [ ] Producer moves TASK-0070 only to review; EvidenceGate decides completion.

# Verification method

- .\.venv\Scripts\python.exe -B -m unittest tests.test_workflow_sequence -v
- .\.venv\Scripts\python.exe -B scripts\check.py --lint
- git diff --check
- Test the runner on a simple 2-task sequence to validate orchestration before
  applying to Phase 1.

# Required evidence and handoff

- Publish `evidence/workflow-sequence-runner-report.md` describing the
  WorkflowSequence format, the runner's claim->Goal->bridge loop, and the
  failure-halt test.
- Publish `evidence/verification-summary.json`.
- Publish `handoffs/HANDOFF-0001.md` stating: TASK-0070 complete, Phase 1 can
  now be executed as `ahra workflow-sequence run phase1-sequence.yaml`.
