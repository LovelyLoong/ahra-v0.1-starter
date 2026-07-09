---
type: Architecture
id: ARCH-intent-alignment-workflow
schema_version: awkp/0.1
title: Intent alignment front workflow (Workflow A)
description: Defines the Agent-driven intent-to-contract front workflow that turns a human's natural-language request into a frozen GoalExecutionRequest for the execution workflow, using a typed boundary contract, acceptance-first serial drafting, a deterministic cross-alignment admission gate, and two human gates.
status: active
owner: human:maintainer
source_refs:
  - ../../architecture/decisions/ADR-0009-agent-driven-intent-alignment-front-workflow.md
  - ../../architecture/decisions/ADR-0010-boundary-contract-acceptance-first-alignment.md
  - ../../AHRA_dynamic_kernel_master_plan_2026-06-25.md
  - ./dynamic-agent-kernel.md
  - ../policies/agent-authority-boundaries.md
  - ../roadmaps/phase1-minimal-loop-intent-roadmap.md
evidence_refs: [TASK-0077, TASK-0094]
confidence: draft
last_verified_at: 2026-07-06T00:00:00Z
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

This document is the active owner of the Workflow A concept. The decision
records are
[ADR-0009](../../architecture/decisions/ADR-0009-agent-driven-intent-alignment-front-workflow.md)
(agent-driven front workflow) and
[ADR-0010](../../architecture/decisions/ADR-0010-boundary-contract-acceptance-first-alignment.md)
(boundary contract, acceptance-first drafting, cross-alignment admission),
which amends ADR-0009 decisions 2 and 4. Workflow A is **proposed and partially
implemented as an experimental, non-default path**; the implemented
`alignment_session` slice still follows the superseded ADR-0009 parallel
drafting topology and is scheduled for revision. The prior TASK-0063 non-Agent
deterministic transformer has been removed from the active source surface; its
records are historical trace only.

# Core principle: requirement is the acceptance

The single most important rule of this workflow:

> The essence of the foundation is to satisfy the user's requirement.
> Verification is also judged against the user's requirement. When the
> requirement is satisfied, verification passes.

Implementation and acceptance therefore share one anchor: the **frozen boundary
contract**. The acceptance Agent expresses it as "how completion is judged"; the
implementation side then targets that frozen acceptance. Neither invents a
separate standard.

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

# The boundary contract (Gate 1 product)

What Human Gate 1 freezes is not prose but a **boundary contract**: a short list
(typically 5–15 entries) of typed, ID'd boundary entries. The IDs name the
boundary itself, not enumerated requirement detail.

| Kind | Meaning | Acceptance authority |
|---|---|---|
| `must` | must be present in the result | must be covered by at least one Claim |
| `must_not` | must be explicitly absent | must be covered by at least one Claim |
| `completion_signal` | what objectively counts as done | must be covered by at least one Claim |
| `free_zone` | executing Agent's explicit discretion | Claims must NOT reference it |
| `open_question` | unresolved topic | blocks freeze until resolved or removed |

```yaml
frozenBoundary:
  - id: REQ-M1
    kind: must
    text: The output must be command-gate decidable.
  - id: REQ-N1
    kind: must_not
    text: No files outside the workspace may change.
  - id: REQ-C1
    kind: completion_signal
    text: scripts/check.py exits 0.
  - id: REQ-F1
    kind: free_zone
    text: Internal module decomposition is the implementer's choice.
```

**No-gray-zone rule:** every topic surfaced in the alignment dialogue must land
in exactly one entry before freeze. Nothing may remain "neither frozen nor
declared free" — drift concentrates in exactly such gaps. A free zone is an
explicitly granted right with an ID, not an omission.

When the human genuinely cannot state the boundary yet, Workflow A may route a
**low-cost exploratory spike** (a small bounded B run or a manually supplied
artifact) whose product serves purely as alignment material. Spike output is
untrusted input; it never becomes acceptance content automatically, and only
Human Gate 1 freezes the boundary contract.

# Three-Agent role separation, acceptance first

Workflow A uses three distinct Agents. The separation mirrors the
Planner/Executor/Verifier power split in the master plan, applied to the
contract-generation stage so that the author of "what to build" never authors
or alters "how it is judged."

```text
User: natural language ("analyze the XX market", "refactor the login module")
   |
   v
[1] Alignment Agent  -- multi-turn dialogue -->
        drives every surfaced topic into a typed boundary entry
        (must / must_not / completion_signal / free_zone / open_question)
   |
   v  [HUMAN GATE 1 - light]  user confirms the boundary contract is complete
   |                          (no open_question left) -> boundary is frozen
   |
   v
[2] Acceptance Agent   reads ONLY the frozen boundary contract ->
        drafts the ClaimGraph / GatePlan; every Claim's criterionRefs
        reference boundary entry IDs -> ClaimGraph is digest-frozen
   |
   v
[3] Requirement Agent  reads the boundary contract + the FROZEN ClaimGraph ->
        drafts the PlanDraft; node claimRefs may only reference existing
        claim IDs (read-only visibility, no write path into acceptance)
   |
   v  deterministic cross-alignment gate (referential integrity across
   |  boundary entries / Claims / PlanNodes; fail closed, bounded redrafts)
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

## Why acceptance drafts first and the planner may read it

The superseded ADR-0009 topology ran [2] and [3] in parallel, each independently
interpreting the same natural-language requirement, coordinated only by a
claim-ID prefix convention. Two independent compilations of ambiguous prose
diverge structurally — that misalignment was observed in real-driver testing and
is topology-caused, not prompt-caused.

The v2 ordering keeps exactly one natural-language-to-structure translation (the
acceptance side); the planner performs structure-to-structure derivation against
the frozen ClaimGraph. Power separation is preserved because what is forbidden
is the producer **authoring or altering** acceptance, not **seeing** it —
acceptance criteria are visible to implementers by design, exactly as a test
suite is visible to developers. The ClaimGraph digest is captured before the
Requirement Agent runs, so the planner has no write path into the acceptance.
The reverse ordering (plan first, acceptance judges the plan) remains forbidden:
it degenerates acceptance into "prove the chosen implementation is correct."

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

# The alignment elicitation checklist

The alignment Agent does not chat aimlessly. It is guided by a fixed set of
dimensions it must drive to closure before proposing boundary freeze:

1. **Output form** — document, table, code, dataset, report? (captured as
   `must` entries)
2. **Must-haves** — what must be present in the result?
3. **Must-nots** — what must explicitly be absent? (frequently forgotten, highly
   valuable for shrinking subjectivity)
4. **Completion signal** — what objectively counts as "done"?
5. **Allowed free zones** — which parts may the executing Agent decide on its
   own? (everything outside these is, by default, expected to be objective)

Each closed dimension lands as one or more typed boundary entries; anything
still open is an `open_question` entry that blocks Gate 1. The free-zone
dimension turns residual subjectivity from an accidental gap into a knowing,
user-approved, ID'd region.

Unresolved Gate 1 choices must also be represented as structured decision
records, not only as prose. Each record carries `decisionId`, `question`,
`recommendation`, `alternatives`, `consequences`, `blocking`, and
`finalAnswer`. A blocking record without `finalAnswer` prevents Gate 1 freeze
even if the Alignment Agent tries to mark the session converged.

# Verification: validate the product, not the process

Workflow A's own development tasks are verified by validating their **products**,
not by replaying the non-deterministic dialogue. The alignment dialogue is
Agent-driven and non-deterministic by design; that is acceptable. What is
checked at Workflow A's exit is deterministic and command-gate decidable:

| Exit gate | What is checked | How it is judged |
|---|---|---|
| Structure gate | the RequestDraft is a well-formed GoalExecutionRequest suite | schema validation, exit 0 |
| Cross-alignment gate | every PlanNode claimRef resolves in the frozen ClaimGraph; every required Claim is covered by a node; every must/must_not/completion_signal entry is referenced by a Claim's criterionRefs; no Claim references a free_zone; no open_question remains | deterministic validator accepts; fail closed with a structured mismatch report and bounded redrafts |
| Admission gate | digests resolve, capabilities are within the allowed set, the ClaimGraph is acyclic and valid | `RequestDraftAdmission` runs after cross-alignment and before ApprovalService creates Gate 2 approval; rejection feeds a structured report into bounded redraft, and exhausted attempts fail without `approval.json` |
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
  pre-structured IntentDraft) and the **middle** (real Agents, not a fixed
  converter).
- **Experimental `alignment_session` checkpoint** (`src/ahra/alignment_session.py`)
  is the current AgentDriver-backed Workflow A implementation slice. It can
  drive dialogue, preserve immutable snapshots, reject profile/runtime digest
  mismatches before Agent invocation, require explicit Requirement-Agent
  `PlanDraft` and Acceptance-Agent `ClaimGraph`, enforce Human Gate 1, run the
  ADR-0010 boundary-contract and acceptance-first serial drafting order, and
  apply the deterministic cross-alignment gate and RequestDraftAdmission before
  emitting an untrusted `RequestDraft` for Gate 2 authorization.
  Cross-alignment and admission failures are recorded as structured reports on
  the session snapshot and can trigger only bounded redrafts. `workflow-a draft`
  writes a self-contained Gate 2 HTML briefing from the RequestDraft and
  ApprovalRecord, and `workflow-a authorize` verifies the briefing binding in
  strict mode before freezing the GoalExecutionRequest. It remains non-default
  until a separate component-lifecycle promotion approves default visibility.

# Non-goals

- This workflow does not let any Agent freeze its own request; Gate 2 always
  requires a separate human authorization actor.
- This workflow does not let Agents modify the foundation's own policy, validator,
  EvidenceGate, capability definitions, or top-level acceptance contracts.
- This document fixes design intent only. It does not define new schemas or code;
  those follow the contract-change order when implementation is scheduled.
