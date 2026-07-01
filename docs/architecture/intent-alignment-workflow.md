---
type: Architecture
id: ARCH-intent-alignment-workflow
schema_version: awkp/0.1
title: Intent alignment front workflow (Workflow A)
description: Defines the Agent-driven intent-to-contract front workflow that turns a human's natural-language request into a frozen GoalExecutionRequest for the execution workflow, using role separation, requirement-as-acceptance, boundary front-loading, and two human gates.
status: active
owner: human:maintainer
source_refs:
  - ../../architecture/decisions/ADR-0009-agent-driven-intent-alignment-front-workflow.md
  - ../../AHRA_dynamic_kernel_master_plan_2026-06-25.md
  - ./dynamic-agent-kernel.md
  - ../policies/agent-authority-boundaries.md
  - ../roadmaps/phase1-minimal-loop-intent-roadmap.md
evidence_refs: [TASK-0077]
confidence: draft
last_verified_at: 2026-07-01T10:30:10Z
review_after: 2026-09-30T00:00:00Z
tags: [architecture, intent, alignment, workflow, phase1, agent-driven]
---

# Summary

The foundation has two workflows joined by one immutable contract.

- **Workflow B (contract to execution and verification)** is the governed
  dynamic Agent kernel that already exists (TASK-0021..0070). It takes a
  `GoalExecutionRequest`, runs the Loop Engineering cycle (goal, plan, execute,
  verify, repair, re-verify, complete), and decides completion through
  command-gate verification and AWKP EvidenceGate.
- **Workflow A (intent to contract)** is the Agent-driven front workflow defined
  here. It takes a human's raw natural-language request, aligns it through
  multi-turn dialogue, and produces a frozen `GoalExecutionRequest` that
  Workflow B can consume without further human prompt authoring.

This document is the active owner of the Workflow A concept. The decision record
is [ADR-0009](../../architecture/decisions/ADR-0009-agent-driven-intent-alignment-front-workflow.md).
Workflow A is **proposed and not yet implemented**; the prior deterministic
template `alignment_engine` is a stub and is being marked experimental.

# Core principle: requirement is the acceptance

The single most important rule of this workflow:

> The essence of the foundation is to satisfy the user's requirement.
> Verification is also judged against the user's requirement. When the
> requirement is satisfied, verification passes.

Implementation and acceptance therefore share one anchor: the **frozen
requirement**. The implementation Agent and the acceptance Agent do not invent
their own separate targets; they both express the same frozen requirement, one
as "what to build" and the other as "how completion is judged."

# Core principle: front-load the boundary

Subjective ambiguity is resolved at alignment time, not at verification time.

A vague request like "analyze the XX market" cannot be verified objectively. But
if the alignment Agent drives the user to constrain the output shape — "a table
with columns X/Y/Z plus three conclusion paragraphs, no predictive investment
advice" — then most of the acceptance becomes objectively decidable.

The alignment Agent's true value is to **move verification determinism forward
into the requirement-definition stage**. The better alignment is, the easier
implementation and verification become. Residual subjectivity that genuinely
cannot be made objective must be explicitly marked as a user-acknowledged free
zone, not left as an unspoken gap.

# Three-Agent role separation

Workflow A uses three distinct Agents. The separation mirrors the
Planner/Executor/Verifier power split in the master plan, applied to the
contract-generation stage so that the author of "what to build" is never the
author of "how it is judged."

```text
User: natural language ("analyze the XX market", "refactor the login module")
   |
   v
[1] Alignment Agent  -- multi-turn dialogue -->
        clarifies the requirement from multiple angles AND drives the user to
        constrain the output shape (format, must-haves, must-nots, completion
        signal, explicitly allowed free zones)
   |
   v  [HUMAN GATE 1 - light]  user confirms "my requirement and output boundary
   |                          are fully stated" -> requirement is frozen
   |
   +--> [2] Requirement Agent  reads ONLY the frozen requirement ->
   |        drafts the deliverable spec for B (the PlanDraft side: what to build)
   |
   +--> [3] Acceptance Agent   reads ONLY the frozen requirement ->
            drafts the acceptance spec for B (the ClaimGraph / GatePlan side:
            how completion is judged)
   |
   v  the two specs combine into a RequestDraft -> RequestDraft admission
   |
   v  [HUMAN GATE 2 - heavy]  human approves the acceptance criteria and the
   |                          capability boundary -> freeze into an immutable
   |                          GoalExecutionRequest
   |
   v  seamless handoff
[Workflow B] goal start -> schedule -> capability admission -> command-gate
             verification -> EvidenceGate completion
```

## Why [2] and [3] must not see each other's output

The implementation spec and the acceptance spec are produced **in parallel and
independently, each reading only the frozen requirement**. If the acceptance
Agent reads the implementation spec, acceptance degenerates into "prove the
chosen implementation is correct" instead of "prove the user's requirement is
met." Independence at the source is what prevents collusion and rule capture.

# The two human gates

Workflow A has exactly two human interventions. The Agents do all drafting and
dialogue; the human only nods at two anchors.

| Gate | Weight | Who decides | What it locks |
|---|---|---|---|
| Gate 1: requirement freeze | light | Alignment Agent proposes, user confirms | what to do, and the output boundary |
| Gate 2: contract authorization | heavy | human approval actor (not the producer) | what will be produced; the capability boundary; freezes the immutable GoalExecutionRequest |

After Gate 2 the user already knows, in broad strokes, what the final output will
look like. Workflow B should produce no surprises — surprises must be aligned away
in Workflow A. This is a direct consequence of front-loading the boundary.

Gate 2 is non-negotiable governance. Per the master plan, a top-level scope
change without human approval is a non-goal, and no Agent may self-declare
completion. The acceptance criteria drafted by Agent [3] are **untrusted** until
a human authorization actor freezes them.

# The alignment output contract checklist

The alignment Agent does not chat aimlessly. It is guided by a fixed set of
dimensions it must drive to closure before proposing requirement freeze:

1. **Output form** — document, table, code, dataset, report?
2. **Must-haves** — what must be present in the result?
3. **Must-nots** — what must explicitly be absent? (frequently forgotten, highly
   valuable for shrinking subjectivity)
4. **Completion signal** — what objectively counts as "done"?
5. **Allowed free zones** — which parts may the executing Agent decide on its
   own? (everything outside these is, by default, expected to be objective)

The last dimension turns residual subjectivity from an accidental gap into a
knowing, user-approved region.

# Verification: validate the product, not the process

Workflow A's own development tasks are verified by validating their **products**,
not by replaying the non-deterministic dialogue. The alignment dialogue is
Agent-driven and non-deterministic by design; that is acceptable. What is
checked at Workflow A's exit is deterministic and command-gate decidable:

| Exit gate | What is checked | How it is judged |
|---|---|---|
| Structure gate | the RequestDraft is a well-formed GoalExecutionRequest suite | schema validation, exit 0 |
| Admission gate | digests resolve, capabilities are within the allowed set, the ClaimGraph is acyclic and valid | `RequestDraftAdmission` accepts |
| Consumability gate | the frozen request is actually runnable by Workflow B | `goal validate` / `goal plan` exit 0 on the frozen request |

The content quality of the dialogue is not graded by these gates. The Agent may
converse in any way and for any number of turns; success is defined solely by the
frozen RequestDraft passing the three exit gates and being consumable by B.

# Relationship to existing components

- **AgentDriver Port** (`src/ahra/ports.py`) and `AgentDriverRegistry` already
  exist. The three alignment Agents are AgentDriver clients, exactly as the
  Mode C Planner is. Workflow A reuses this proven "Agent produces an untrusted
  draft, admission validates it" pattern, moved one step earlier in the chain.
- **RequestDraft / RequestDraftAdmission / ApprovalService** already exist from
  Phase 1 tasks (TASK-0062..0065). The admission and freeze layer is largely
  correct and is retained. What changes is the **entry** (natural language, not a
  structured IntentDraft) and the **middle** (real Agents, not a template).
- **Experimental `alignment_session` checkpoint** (`src/ahra/alignment_session.py`,
  TASK-0077) is the first AgentDriver-backed Workflow A implementation slice.
  It can drive dialogue, preserve immutable snapshots, reject profile/runtime
  digest mismatches before Agent invocation, and emit an untrusted
  `RequestDraft`. It remains non-default until Requirement/Acceptance Agent
  outputs are explicit and fail-closed, and both ADR-0009 human gates are wired.
- **The deterministic template `alignment_engine`** is reclassified as
  experimental and removed from default exposure. It survives only as a
  deterministic test stub and is not invoked unless explicitly requested.

# Non-goals

- This workflow does not let any Agent freeze its own request; Gate 2 always
  requires a separate human authorization actor.
- This workflow does not let Agents modify the foundation's own policy, validator,
  EvidenceGate, capability definitions, or top-level acceptance contracts.
- This document fixes design intent only. It does not define new schemas or code;
  those follow the contract-change order when implementation is scheduled.
