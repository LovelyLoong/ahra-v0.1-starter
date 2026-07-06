---
type: Architecture
id: ARCH-dynamic-workflow-synthesis
schema_version: awkp/0.1
title: Dynamic workflow synthesis
description: Defines the next-phase direction where fixed named workflows become reference patterns, and an Agent synthesizes a task-specific workflow from rules, modules, metadata-filtered knowledge, and validation gates.
status: active
owner: human:maintainer
source_refs:
  - ./authority-map.md
  - ./dynamic-agent-kernel.md
  - ../policies/document-governance.md
  - ../policies/data-lifecycle.md
  - https://aws.amazon.com/blogs/machine-learning/structured-memory-filtering-with-metadata-in-agentcore-memory/
  - https://www.microsoft.com/en-us/research/blog/skillopt-agent-skills-as-trainable-parameters/
evidence_refs: []
confidence: draft
last_verified_at: 2026-07-06T00:00:00Z
review_after: 2026-10-06T00:00:00Z
tags: [architecture, workflow, synthesis, modules, knowledge]
---

# Summary

The next AHRA direction is not to add more fixed default workflows. Fixed names
such as Workflow A, Workflow B, and Loop Engineering remain useful reference
patterns, but the long-term unit of execution is a task-specific workflow
synthesized at runtime.

```text
User Goal
  -> Goal Intake / Requirement Clarification
  -> confirmed GoalSpec + AcceptanceSpec
  -> Human Goal Confirmation
  -> Dynamic Workflow Synthesizer Skill
  -> metadata-filtered docs, lessons, and module catalog
  -> task-specific WorkflowIR
  -> WorkflowIR validation against minimum rules
  -> execution with task-local modules allowed
  -> verification and review
  -> lesson distillation back into docs
  -> successful workflow distillation into `skills/workflows/`
  -> optional module or Skill improvement proposal
```

The durable project assets are the rules, module contracts, documentation
metadata, evidence model, and Skill improvement process. A generated workflow is
a run artifact, not a permanent authority by default.

Dynamic Workflow Synthesis begins only after Goal Intake accepts the goal as
specific enough to execute, with scope and endpoint clear enough for the user
to confirm. Goal Intake also records how acceptance will happen. It must not be
the component that turns an unclear human request into its own goal.

# Why Workflows Exist

Workflows exist because a single Agent pass often cannot reliably solve complex
work. A workflow adds structure: staged context gathering, planning, execution,
verification, repair, scoring, or review. Each structure is a means to improve
outcomes for a specific task, not a product boundary that must be preserved.

Examples:

- The current governed execution path separates implementation from evidence
  and independent completion review.
- Loop Engineering repeats plan, execute, verify, defect, and repair until the
  goal is reached or the loop budget is exhausted.
- Intent alignment pushes ambiguity resolution forward so the executable
  request and stop condition are not invented during execution.

The synthesizer may use these patterns, combine them, or skip them when the
task is simple.

# Non-Negotiable Boundary

Dynamic workflow generation does not mean dynamic truth generation.

- The user goal, scope boundary, endpoint, protected files, and acceptance mode
  are fixed inputs to synthesis.
- If the request lacks a clear goal, clear scope, or clear endpoint, the system
  must run Goal Intake rather than synthesize an execution workflow.
- Even when Goal Intake accepts a request, synthesis must wait for explicit
  human confirmation of the `GoalSpec`, `AcceptanceSpec`, scope boundary, and
  non-goals.
- The generated workflow may choose how to reach the goal, but it may not weaken
  what counts as done.
- The Synthesizer may split execution into stages, modules, or subgoals only as
  WorkflowIR structure. It may not add, delete, or rewrite `GoalSpec`
  criteria, and every executable subgoal must map back to frozen criteria.
- The `AcceptanceSpec` is produced by Goal Intake and manually confirmed by the
  user before synthesis. When it includes a tool-based `VerifierSpec`, the
  Synthesizer may bind modules that implement the frozen `VerifierSpec`, but it
  may not change or recombine the verification standard.
- Policy, EvidenceGate, permission boundaries, protected schemas, and human
  authorization requirements are protected. An Agent may propose changes to
  them through review, but a normal run may not silently edit them.
- Generated workflows and task-local scripts are untrusted until their outputs
  pass the declared gates.

# Core Concepts

## Goal Intake

Goal Intake is the outer clarification and admission flow before workflow
synthesis. Its job is to protect the user from sending a vague or
misunderstood request into an execution loop.

Goal Intake determines:

- whether the user appears to understand the request scale and relevant
  context;
- which critical blind spots or assumptions remain;
- whether the request can be split into clear goals;
- whether acceptance can be tool-verified or requires user acceptance;
- whether the verifier can return an accurate machine-readable status for the
  accepted goal when the acceptance mode is tool-based;
- whether the request should proceed, ask clarifying questions, run exploratory
  context gathering, split, or stop as not currently executable.

Goal Intake may ask the user questions. It may also run a bounded, lightweight
exploratory step automatically when the purpose is to gather context or discover
candidate verification strategies. Exploratory work must stay faithful to the
user's intent: it may reveal options, risks, examples, and verifier candidates,
but it must not silently replace the user's goal with an easier one.

Allowed exploratory actions:

- read code, docs, task state, manifests, and prior context;
- search existing local context;
- run non-mutating diagnostics, linters, or tests when they are needed to
  understand current state or possible verifiers;
- perform bounded network lookup when current external facts or sources are
  needed;
- create only ephemeral notes or scratch artifacts needed to report the
  exploratory result.

Exploratory work must not:

- make product/source changes intended to satisfy the user's task;
- create a heavyweight implementation task just to clarify the goal;
- persist new project authority;
- broaden permissions beyond the intake purpose;
- treat a prototype or experiment as accepted requirements.

Goal Intake emits:

- `GoalSpec`;
- `AcceptanceSpec`;
- optional `VerifierSpec` when acceptance is tool-based;
- `OpenQuestions`;
- `KnownAssumptions`;
- `ScopeBoundary`;
- `NonGoals`;
- `AdmissionDecision`.

`GoalSpec` is intentionally small. It captures what the user wants, the scope
boundary, the endpoint, and explicit non-goals. It does not prescribe the
workflow topology, modules, scoring strategy, or execution process.

`AcceptanceSpec` records how the result will be accepted:

- `tool_verifier`: Goal Intake freezes a `VerifierSpec`.
- `human_acceptance`: the workflow may execute and deliver, but final
  acceptance is explicitly reserved for the user.

When `AcceptanceSpec.mode = tool_verifier`, `VerifierSpec` must identify a
verifier that can return an accurate structured status for the accepted goal. It
is part of Goal Intake output, is manually confirmed with the `GoalSpec`, and
is frozen before synthesis. Typical verifiers are commands, tests, schemas,
deterministic checks, reproducible probes, or other programmatic evaluators.

A tool verifier result must include at least:

- terminal status: `pass`, `fail`, `blocked`, or `inconclusive`;
- claim or criterion coverage;
- failed or unresolved claims when status is not `pass`;
- evidence references or observation references;
- diagnostic summary;
- next repair boundary or reason no repair boundary can be proposed.

A bare pass/fail tool verifier result is not sufficient for iterative
topologies, because iterative execution needs to know why the current state did
or did not reach the goal. For `human_acceptance`, the WorkflowIR must not claim
automatic completion; it should produce a deliverable package and terminal state
such as `awaiting_user_acceptance`.

Only `AdmissionDecision = accepted` plus explicit human confirmation of the
`GoalSpec` and `AcceptanceSpec` may enter Dynamic Workflow Synthesis. Other
decisions return to the user or to an exploratory/intake path:

- `clarification_needed`;
- `exploratory_context_needed`;
- `split_required`;
- `not_clear_enough`;
- `unsupported_acceptance_mode`;
- `unsupported_for_execution_workflow`.

Human confirmation is a lightweight gate, but it is mandatory. It confirms that
the user understands the accepted goal, acceptance mode, assumptions, scope, and
non-goals before the system generates an execution workflow.

## Workflow Synthesizer Skill

The synthesizer is a project-local Skill whose job is to build the best current
workflow for one accepted `GoalSpec`. It reads the frozen goal, acceptance spec,
optional verifier spec, current state, allowed resources, module catalog,
metadata-filtered documents, and prior lessons, then emits a WorkflowIR.

When a frozen `VerifierSpec` exists, the Synthesizer may choose verifier modules
only as implementations of that `VerifierSpec`. It must not alter, weaken,
broaden, split, merge, or replace the verification standard during WorkflowIR
generation. When acceptance is `human_acceptance`, the Synthesizer should choose
a topology that supports delivery and review handoff rather than pretending it
can automatically verify final acceptance.

The Synthesizer must include verifier and review modules in WorkflowIR when the
accepted goal needs them. This does not force a Loop Engineering topology.
WorkflowIR may be a one-pass plan, staged pipeline, fan-out/fan-in review,
score-and-select path, loop with bounded repair, or another validated topology.
The topology is chosen to fit the goal, acceptance mode, module catalog, budget,
and frozen verifier if one exists, not to satisfy a fixed workflow pattern.

The Skill is not itself the project truth. It is an operating method. Durable
facts and accepted lessons live in `docs/`.

## WorkflowIR

WorkflowIR is the run-specific graph or sequence that records what will happen
for this task:

- goal and immutable stop condition;
- mapping from every executable subgoal or phase to frozen `GoalSpec` criteria;
- acceptance mode and any frozen `VerifierSpec`;
- selected modules and their order;
- module inputs, outputs, permissions, and expected artifacts;
- verifier and review gates;
- budgets and loop limits;
- lesson capture and distillation plan;
- terminal states: succeeded, failed, blocked, interrupted, or needs human
  input.

WorkflowIR is stored with the run evidence. During execution, workflow drafts,
loop notes, temporary scripts, and self-adjustments remain task-local run
byproducts. WorkflowIR becomes reusable only after a separate successful-run
distillation step promotes its lessons, modules, or workflow shape into docs,
module catalogs, or a project-local Skill under `skills/workflows/`.

## Module Catalog

Modules are generic capabilities that can be composed by the synthesizer. They
should be small, typed, and easy to replace. A module declares:

- inputs and required state;
- outputs and artifact kinds;
- side effects and permission needs;
- verification signals;
- expected failure modes;
- whether it is task-local, candidate reusable, or core reusable.

Examples include state readers, planners, planner pools, scorers, plan
combiners, executors, verifiers, defect analyzers, lesson recorders,
distillers, reviewers, and temporary script generators.

## Task-Local Temporary Modules

A run may create short scripts, fixtures, parsers, probes, or validators when
the existing module catalog is insufficient. These are task-local by default.

Promotion path:

```text
task-local temporary module
  -> candidate reusable module after repeated usefulness
  -> core reusable module after validation, documentation, and review
```

Temporary modules must stay inside the declared write scope and must not become
implicit project authority.

## Metadata-Filtered Knowledge

The synthesizer must not read all documents indiscriminately. It first filters
knowledge by structured metadata, then reads the smallest relevant set.

Required metadata for future lesson and pattern docs should include:

- `doc_kind`: architecture, policy, pattern, lesson, module, runbook, or
  anti_pattern;
- `authority`: active, proposed, experimental, archived, or superseded;
- `scope`: project, workflow, module, task_family, or task_local;
- `applies_to`: task types, risk levels, modules, or file areas;
- `evidence_refs`: task ids, run ids, gate reports, or verifier reports;
- `failure_modes`: known ways the guidance can mislead;
- `review_after`: freshness boundary.

This follows the same principle as structured memory filtering: use metadata to
avoid pulling irrelevant or stale context before semantic matching.

## Lesson Distillation

During a run, Agents may record raw loop notes in task-local storage. At the end
of the run, a distiller summarizes:

- effective strategies;
- failed strategies and why they failed;
- verifier signals that mattered;
- cost and iteration count;
- reuse conditions;
- non-reuse conditions;
- related WorkflowIR, module, and evidence references.

Only distilled lessons with provenance enter `docs/`. Process traces and bulky
run byproducts remain evidence or archive material.

## Workflow Skill Distillation

When a synthesized workflow completes normally and reaches its confirmed
acceptance condition, the run must produce a project-local Skill artifact under
`skills/workflows/` that captures the reusable operating method. This is the
workflow equivalent of lesson distillation: raw execution material stays in the
task-local temporary area, then a final filtering pass extracts only the
reusable pattern.

The distilled Skill must record:

- the goal and task family it applies to;
- the workflow topology that actually succeeded;
- modules, gates, verifier or review steps, and loop limits used;
- required preconditions and protected boundaries;
- reuse conditions and non-reuse conditions;
- evidence references proving the workflow completed normally.

Failed, blocked, interrupted, abandoned, or not-yet-accepted workflows must not
produce reusable Skills. They may still leave lessons, anti-patterns, evidence,
or rejected Skill material for later analysis.

## Skill Improvement

Skills may evolve, but the process is train-like rather than ad hoc:

```text
run-time adaptation
  -> skill patch candidate
  -> validation against held-out or historical tasks
  -> promotion only if metrics improve without weakening boundaries
  -> rejected patch buffer for future learning
```

This keeps the system open to improvement while preventing short-term success
from silently degrading long-term workflow quality.

# Relationship To Current AHRA Work

- Current Workflow A remains a reference pattern for intent alignment and
  contract freezing.
- Current Workflow B remains a reference pattern for governed execution and
  EvidenceGate-backed completion.
- Loop Engineering becomes a reference pattern for self-verifiable iterative
  tasks.
- None of these names should become permanent mandatory defaults for all future
  work.

The dynamic-kernel objects remain valuable. Goal, Claim, Gate, PlanDraft,
PlanIR, Capability, Artifact, Evidence, Defect, and Completion are reusable
building blocks for WorkflowIR validation and execution.

# Minimum Implementation Surface

The first implementation increment should avoid overbuilding. It needs only:

1. a WorkflowIR schema or domain object;
2. a small module manifest shape;
3. a Synthesizer Skill that can emit WorkflowIR from a goal and filtered docs;
4. a WorkflowIR validator that rejects missing acceptance mode, missing verifier
   for `tool_verifier`, unbounded loops, and unauthorized side effects;
5. task-local lesson capture plus end-of-run distillation into docs.

Scorers, plan combiners, module promotion, and Skill optimization are later
increments.

# Non-Goals

- No claim that dynamic synthesis is already implemented.
- No removal of existing A/B paths during this design step.
- No run-time self-modification of protected policy or verifier boundaries.
- No global memory dump as a substitute for metadata-filtered docs.
- No permanent promotion of a generated workflow without evidence and review.
