---
type: Roadmap
id: ROADMAP-dynamic-workflow-synthesis
schema_version: awkp/0.1
title: Dynamic workflow synthesis roadmap
description: Orders the next-phase work for replacing fixed workflow defaults with task-specific WorkflowIR synthesis, module composition, metadata-filtered knowledge, lesson distillation, and validated Skill evolution.
status: proposed
owner: human:maintainer
source_refs:
  - ../architecture/dynamic-workflow-synthesis.md
  - ../policies/document-governance.md
  - ../policies/data-lifecycle.md
evidence_refs: []
confidence: draft
last_verified_at: 2026-07-06T00:00:00Z
review_after: 2026-10-06T00:00:00Z
tags: [roadmap, workflow, synthesis, modules, skill-evolution]
---

# Purpose

This roadmap turns the agreed next-stage direction into implementation order.
The target is a system where an Agent synthesizes a task-specific workflow from
rules, modules, and metadata-filtered project knowledge instead of selecting a
fixed named workflow.

# Stage Order

```text
Authority update
  -> Goal Intake and GoalSpec admission
  -> WorkflowIR contract
  -> Module manifest contract
  -> metadata-filtered knowledge retrieval
  -> Synthesizer Skill v1
  -> WorkflowIR validation
  -> Loop-style self-verifiable execution profile
  -> lesson distillation into docs
  -> successful workflow distillation into `skills/workflows/`
  -> module promotion
  -> Skill improvement validation
```

# Stage Gates

## SG-DWS-0: Authority accepted

- `docs/architecture/dynamic-workflow-synthesis.md` is the active owner of the
  next-phase design.
- Authority map, architecture index, roadmap index, and program overview point
  to the new direction.
- Existing Workflow A and Workflow B are described as reference patterns, not
  removed or reclassified as obsolete.

## SG-DWS-1: Goal Intake and GoalSpec admission

- Goal Intake emits `GoalSpec`, `AcceptanceSpec`, optional `VerifierSpec`,
  `OpenQuestions`, `KnownAssumptions`, `ScopeBoundary`, `NonGoals`, and
  `AdmissionDecision`.
- `GoalSpec` records the user's desired outcome, scope boundary, endpoint, and
  non-goals without prescribing workflow topology or modules.
- `AcceptanceSpec` records whether acceptance is `tool_verifier` or
  `human_acceptance`.
- When `AcceptanceSpec.mode = tool_verifier`, `VerifierSpec` is produced by
  Goal Intake and frozen by manual user confirmation before synthesis. The
  Synthesizer cannot choose, combine, or alter the verification standard later.
- Tool verifier results include status, claim or criterion coverage, failed or
  unresolved claims, evidence or observation refs, diagnostic summary, and a
  next repair boundary or a reason no repair boundary can be proposed.
- Bare pass/fail tool verifiers are rejected for iterative topologies because
  they cannot drive reliable repair.
- When `AcceptanceSpec.mode = human_acceptance`, the synthesized workflow may
  execute and deliver, but it must terminate as `awaiting_user_acceptance`
  instead of claiming automatic completion.
- Requests without a clear goal, clear scope, or clear endpoint do not enter
  synthesis; they return `clarification_needed`,
  `exploratory_context_needed`, `split_required`, `not_clear_enough`, or
  `unsupported_for_execution_workflow`.
- `AdmissionDecision = accepted` is not enough by itself. The user must manually
  confirm the `GoalSpec`, `AcceptanceSpec`, `ScopeBoundary`, assumptions, and
  non-goals before Synthesizer execution starts.
- Bounded exploratory steps may run automatically to discover context or
  candidate verifier strategies, but they must not silently rewrite the user's
  intent or lower the target.
- Exploratory steps are lightweight: they may read code/docs/context, run
  non-mutating diagnostics or tests, do bounded network lookup, and write only
  ephemeral notes or scratch artifacts. They must not implement the task or
  create heavyweight work just to clarify the goal.

## SG-DWS-2: WorkflowIR contract

- A schema or domain object records goal, acceptance mode, optional verifier,
  selected modules, permissions, gates, budgets, loop limits, artifacts, and
  terminal states.
- Every executable subgoal, phase, or module objective maps back to frozen
  `GoalSpec` criteria; Synthesizer cannot add, delete, or rewrite criteria.
- WorkflowIR is a run artifact by default and cannot become project authority
  without distillation or promotion.
- Tests reject missing acceptance mode, missing verifier for `tool_verifier`,
  unbounded loops, and unauthorized side effects.

## SG-DWS-3: Module manifest contract

- Modules declare inputs, outputs, side effects, permissions, verification
  signals, failure modes, lifecycle class, and promotion status.
- Task-local temporary modules are allowed but constrained to the declared write
  scope.
- Candidate reusable and core reusable module promotion paths are explicit.

## SG-DWS-4: Metadata-filtered knowledge retrieval

- Lesson, pattern, module, and anti-pattern docs carry structured metadata.
- The synthesizer filters by authority, scope, applies_to, evidence_refs,
  failure_modes, and review_after before semantic matching.
- Superseded, archived, task-local, or stale docs cannot silently override an
  active authority.

## SG-DWS-5: Synthesizer Skill v1

- A project-local Skill reads the accepted `GoalSpec`, `AcceptanceSpec`,
  optional `VerifierSpec`, state summary, module catalog, and filtered docs,
  then emits WorkflowIR.
- The Skill may choose A-like, B-like, Loop-like, or custom structures, but it
  must not weaken the goal or stop condition.
- The Skill may bind verifier modules only to implement a frozen `VerifierSpec`
  when one exists; it must not change the verification standard.
- For `human_acceptance`, the Skill should generate a delivery/review handoff
  topology instead of pretending automatic verification exists.
- The Skill must include verifier and review modules needed by the accepted
  goal, but it must not default every task to Loop Engineering. One-pass,
  staged, fan-out/fan-in, score-and-select, and bounded-loop topologies are all
  valid when the WorkflowIR validator accepts them.
- The Skill records why selected modules fit the task and why rejected modules
  were not selected.

## SG-DWS-6: WorkflowIR validation and execution

- A validator blocks unsafe or unverifiable WorkflowIR before execution.
- A small end-to-end task proves a generated WorkflowIR can execute and produce
  evidence.
- Completion remains an independent verifier or EvidenceGate decision, not a
  synthesizer assertion.

## SG-DWS-7: Lesson distillation

- Runs capture raw task-local notes during execution.
- End-of-run distillation emits structured lesson docs with provenance,
  applicability, non-applicability, and evidence refs.
- Bulky process traces remain archive or evidence; durable facts land in docs.

## SG-DWS-8: Workflow Skill distillation

- A synthesized workflow that completes normally and reaches its confirmed
  acceptance condition must emit a project-local Skill artifact under
  `skills/workflows/` describing the reusable workflow pattern.
- During execution, workflow self-adjustments, loop notes, temporary scripts,
  and generated WorkflowIR remain task-local byproducts.
- The distillation pass filters the task-local material before writing the
  reusable Skill, including applicability, non-applicability, required modules,
  gates, loop limits, protected boundaries, and evidence refs.
- Failed, blocked, interrupted, abandoned, or not-yet-accepted runs cannot
  create reusable Skills; they may only create lessons, anti-patterns,
  evidence, or rejected Skill material.

## SG-DWS-9: Module and Skill evolution

- Repeatedly useful task-local modules can be proposed as candidate reusable
  modules.
- Skill changes are proposed as patch candidates and validated against
  historical or held-out tasks.
- A Skill patch is promoted only when it improves measured outcomes without
  weakening protected rules.

# Deferred Work

Do not implement these before SG-DWS-6:

- autonomous modification of protected policy or EvidenceGate files;
- full plan-combination across multiple Planner candidates;
- global memory promotion without metadata and provenance;
- workflow synthesizer self-modification without held-out validation;
- production distributed orchestration.

# Stop Conditions

Stop and create a Defect or design handoff when:

- generated WorkflowIR with `tool_verifier` acceptance can pass validation
  without a real verifier;
- a tool verifier only returns pass/fail without claim coverage, evidence refs,
  or repair boundary diagnostics;
- the Synthesizer changes, combines, or replaces the frozen `VerifierSpec`;
- the Synthesizer adds, removes, or rewrites `GoalSpec` criteria under the name
  of execution decomposition;
- generated WorkflowIR is forced into Loop Engineering when a simpler topology
  satisfies the frozen goal and verifier;
- a `human_acceptance` workflow claims automatic completion instead of
  `awaiting_user_acceptance`;
- synthesis runs directly from a vague raw request instead of an accepted
  `GoalSpec`;
- synthesis starts from an accepted `GoalSpec` without explicit human
  confirmation;
- exploratory work changes the user's real target instead of surfacing context
  and verifier options;
- exploratory work performs implementation changes, persists authority, or
  becomes a heavyweight task before goal confirmation;
- a synthesized workflow changes what counts as done;
- metadata filtering selects stale or superseded guidance as active truth;
- a task-local module writes outside its declared scope;
- Skill edits improve one task by weakening general safety boundaries;
- lesson docs lack evidence refs or applicability boundaries.
