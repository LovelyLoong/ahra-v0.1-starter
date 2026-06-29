---
type: Roadmap
id: ROADMAP-phase1-minimal-loop-intent
schema_version: awkp/0.1
title: Phase 1 minimal-loop intent-closure roadmap
description: Orders the work that closes the input boundary of the minimal loop - an Agent-assisted alignment workflow that turns an abstract human Goal into a frozen GoalExecutionRequest, plus governed network and subjective-judgment gates - assuming TASK-0052 through TASK-0061 are complete.
status: proposed
owner: human:maintainer
source_refs:
  - ./dynamic-kernel-m1-roadmap.md
  - ../../work/tasks/TASK-0056/task.md
  - ../../work/tasks/TASK-0061/task.md
evidence_refs: []
confidence: draft
last_verified_at: 2026-06-29T00:00:00Z
review_after: 2026-09-29T00:00:00Z
tags: [roadmap, phase1, minimal-loop, intent, autonomy]
---

# Premise

This roadmap assumes the two prior increments are complete:

- Verification teeth: TASK-0052..0056 (real command gate, honest completion
  derivation, AWKP gate reviews kernel evidence, a demonstrated real failing
  gate).
- Workflow autonomy: TASK-0057..0061 (governed CAS state writer, task
  create/claim commands, producer-to-verifier orchestrator preserving
  producer != verifier, Goal-to-AWKP bridge, demonstrated autonomous end-to-end
  completion of one simple real task).

Phase 1 closes the input boundary of the minimal loop. Today the loop starts
from a hand-authored ~116-line GoalExecutionRequest; the heaviest step - turning
an abstract human intent into an executable, governed Goal - sits outside the
loop. Phase 1 moves that step inside, as a front "alignment workflow," and adds
the two governed gates that let arbitrary-direction Goals actually execute and
be verified.

# Two-stage target shape

```text
human gives an abstract Goal (any direction)
  -> [alignment workflow] Agent constrains scope, aligns acceptance/capabilities/plan over dialogue
  -> untrusted RequestDraft -> admission
  -> [human authorization gate] approve acceptance + capability boundary -> freeze
  -> immutable GoalExecutionRequest
  -> [execution workflow, the 57-61 autonomous path] runs all Tasks to completion
       objective artifacts -> command gate
       network side effects -> governed network.access admission gate
       subjective artifacts -> semantic_review / human_approval gate
```

# Non-negotiable order

```text
IntentDraft contract
  -> alignment workflow engine (multi-turn)
  -> RequestDraft admission
  -> human authorization gate (ApprovalService + waiting_auth)
  -> governed network.access admission gate
  -> real semantic_review / human_approval gates
  -> seamless handoff + autonomous multi-Task execution (simple task first)
```

# Why this order

- The intent contract must exist before a workflow can draft against it.
- The draft must pass admission before a human is asked to authorize it.
- The authorization gate must exist before the two governed side-effect/judgment
  gates hang off it; both network access and subjective judgment are admitted
  and audited through that gate.
- Network and subjective gates must be real before the alignment workflow is
  allowed to promise arbitrary-direction Goals - otherwise it would promise a
  scope the execution side cannot govern.
- End-to-end autonomous execution is validated last, with a simple task first.

# Stage Gates

## SG-P1-A after the IntentDraft contract task

- an IntentDraft schema and domain object exist;
- a declared scope / capability-need section lets out-of-envelope directions be
  rejected early with an explanation;
- the contract is additive and lint-clean.

## SG-P1-B after the alignment workflow engine task

- a multi-turn alignment workflow drafts ClaimGraph/acceptance/PlanDraft;
- it resolves profile and digests from the registry and never fabricates a
  digest;
- it emits an untrusted RequestDraft, never a frozen request.

## SG-P1-C after the RequestDraft admission task

- admission verifies every digest resolves, every capability is in the allowed
  set and not silently high-risk, and the ClaimGraph is structurally valid;
- a draft that fails any check is rejected with a structured reason.

## SG-P1-D after the human authorization gate task

- ApprovalService and the waiting_auth state are real;
- approval freezes the acceptance criteria and capability boundary into an
  immutable GoalExecutionRequest;
- an Agent can never freeze its own request without the authorization step.

## SG-P1-E after the network.access admission gate task

- network.access is no longer unconditionally denied;
- each network use is an explicitly admitted, audited side effect with evidence;
- denial still applies when no grant is present.

## SG-P1-F after the semantic / human-approval gate task

- semantic_review and human_approval are real gate runners, not just enum
  values;
- a subjective artifact can pass or fail verification through a recorded gate
  decision with lineage;
- the producer != verifier boundary holds for these gates too.

## SG-P1-G after the end-to-end task

- one abstract human Goal flows through alignment, authorization, and autonomous
  execution to completion;
- a simple objective Goal is validated first;
- no human opens multiple Agents between steps.

# Hard guarantee: every Phase 1 task is autonomously executable

The maintainer's requirement is that Phase 1 itself be executable by the
repaired workflow (the 57-61 autonomous path), not hand-driven. This section is
the binding contract for how every Phase 1 task must be written so that holds.

## The distinction that makes this coherent

There are two layers, and they must not be conflated:

- The Phase 1 DEVELOPMENT tasks - writing the IntentDraft schema, the alignment
  workflow engine, the admission checks, ApprovalService, the network gate, the
  subjective gates. These are ordinary framework-edit tasks of the same kind as
  TASK-0052..0061. They MUST be autonomously executable.
- The Phase 1 DELIVERABLE at runtime - the alignment workflow a human will later
  run, which by design contains a human authorization gate. That human gate is a
  product feature of the deliverable; it is NOT a manual step in building it.

Confusing the two would wrongly conclude "Phase 1 needs a human, so it cannot be
automated." It does not. Building the human-gated feature is itself an
objective, testable software task.

## Three conditions each Phase 1 task must satisfy

For the 57-61 autonomous path to execute a task, the task must be:

1. Expressible as a GoalExecution through the TASK-0060 Goal-to-AWKP bridge.
2. Within the capability envelope the execution profile can grant (filesystem
   writes to source/contracts/docs/tests; process.exec for tests and lint).
3. Verifiable by a COMMAND GATE - its acceptance criteria reduce to objective
   exit-0 checks (unit tests pass, lint passes, schema validates, diff clean).
   No Phase 1 development task may depend on subjective or human judgment for ITS
   OWN completion.

## The binding rule for authoring Phase 1 tasks

- Every Phase 1 task's acceptance criteria MUST be command-gate-decidable: each
  criterion is backed by a deterministic command (a unit test asserting the
  behavior, a lint check, a schema validation, a diff check) that the TASK-0053
  CommandGateRunner can run to a real PASS/FAIL.
- This applies even to the tasks that BUILD subjective machinery. The task that
  builds the semantic_review / human_approval gates is verified by tests that
  assert the gate correctly routes PASS vs FAIL on fixtures - an objective check
  of a subjective-judging component. The component judges subjectively at
  runtime; the task that builds it is judged objectively.
- The task that builds ApprovalService is verified by tests asserting that
  freezing requires the approval step and that an unapproved freeze is rejected -
  again objective.
- Any criterion that cannot be expressed as a command-gate check is a signal the
  task is mis-scoped for autonomous execution and must be split until it can.

## Consequence for the alignment workflow's runtime scope

The alignment workflow (the deliverable) may produce Goals whose RUNTIME
verification needs semantic_review or human_approval - that is fine and expected,
because SG-P1-F makes those gates real. The constraint above is only about how
the Phase 1 DEVELOPMENT tasks are verified, not about what the finished alignment
workflow may later authorize.

# Tasks (to be scaffolded as AWKP skeletons when 57-61 reduce the stall)

Numbering continues after TASK-0061; each will follow the contract order in
CLAUDE.md (schemas -> SPEC/ADR -> domain+ports -> adapters -> tests -> check.py)
and each acceptance criterion will be command-gate-decidable per the binding
rule above.

| Stage | Task theme | Command-gate verification anchor |
|---|---|---|
| SG-P1-A | IntentDraft contract + declared scope/capability-need | schema validates; domain round-trip test; lint clean |
| SG-P1-B | Alignment workflow engine (multi-turn drafting) | tests assert it emits an untrusted RequestDraft and never fabricates a digest |
| SG-P1-C | RequestDraft admission | tests assert digest/capability/ClaimGraph checks reject bad drafts |
| SG-P1-D | ApprovalService + waiting_auth | tests assert freeze requires approval; unapproved freeze rejected |
| SG-P1-E | Governed network.access admission gate | tests assert grant-required, audited, denied without grant |
| SG-P1-F | Real semantic_review / human_approval gates | fixture tests assert correct PASS/FAIL routing and lineage |
| SG-P1-G | End-to-end intent-to-completion (simple task first) | non-skipped end-to-end test; check.py green |

# Later phases (sketch, beyond Phase 1)

- Phase 2: deepen the governance bridge so Goal and AWKP are fully one surface.
- Phase 3: harden the authorization gate and govern work/proposed -> work/tasks
  promotion.
- Phase 4: the deferred self-iteration - memory-driven strategy synthesis that
  summarizes each work session into reusable strategy context. Scheduled last,
  only on top of Phases 1-3, and out of scope here.

