# ADR-0009: Agent-driven intent alignment front workflow

- Status: accepted
- Date: 2026-06-30
- Decision owner: human:maintainer

## Context

AHRA's governed dynamic Agent kernel (the "execution workflow", Workflow B)
turns a frozen `GoalExecutionRequest` into governed execution and verification:
admission, scheduler, capability reference monitor, command-gate verification,
Defect-driven selective reverification, and AWKP EvidenceGate completion. After
TASK-0052..0070 this execution workflow exists and is exercised by tests.

The original master plan (`AHRA_dynamic_kernel_master_plan_2026-06-25.md`)
starts from "a human submits a GoalContract". It never specified how a human's
*vague* natural-language intent becomes that contract. Phase 1 (TASK-0062..0069)
attempted to close this front edge with an "alignment workflow", but the
delivered `AlignmentWorkflowEngine` is a **deterministic template transformer**,
not an Agent. Its `advance(message)` stores the dialogue turn and never reads
it; `draft_request` fills a fixed two-node template from structured
`IntentDraft` fields. The natural-language `abstractGoal` only flows into a
`statement` string and a digest; it is never understood.

This happened because the Phase 1 roadmap imposed a hard rule that *every Phase 1
task must be command-gate decidable (exit 0)*. Genuine Agent-driven dialogue is
non-deterministic, which conflicts with verifying the *dialogue process*. To
pass that gate, TASK-0063 removed the dialogue's effect entirely, producing an
idempotent template stub. The rule, not the goal, forced the workflow into a
shell.

The maintainer's actual intent: build a reusable **Loop Engineering + custom**
Agent project foundation where a human gives only vague natural language, and
Agents drive the work of turning that into a deliverable contract for Workflow B.

## Decision

### 1. The intent alignment workflow (Workflow A) is Agent-driven, not template-driven

Workflow A accepts **natural language** from the human and uses real
`AgentDriver`-backed agents (the same provider-neutral Port already used by the
Mode C planner) to produce an untrusted `RequestDraft`. It is the front
workflow; Workflow B (the execution kernel) is unchanged downstream.

### 2. Three separated agent roles, mirroring kernel power separation

- **Alignment Agent** — multi-turn dialogue with the human. Its job is not only
  to ask what is wanted, but to *drive the human to constrain the output shape*:
  format (document/table/code/data), must-haves, must-nots, completion signal,
  and the explicitly allowed free-form region. It maximizes how much of the
  acceptance becomes objectively decidable.
- **Requirement Agent** — after requirement freeze, drafts the Workflow-B
  deliverable requirement (the plan/`PlanDraft` side).
- **Acceptance Agent** — after requirement freeze, drafts the Workflow-B
  acceptance contract (the `ClaimGraph`/`GatePlan` side).

The Requirement Agent and Acceptance Agent run **independently from the same
frozen requirement and must not read each other's output**. This prevents the
"author of the implementation also authors the gate that judges it" collusion,
extending the master plan's Planner/Verifier power separation to the contract
generation stage.

### 3. Requirement is the single anchor: requirement *is* acceptance

The essence is implementing the user's requirement. Verification is, by
definition, checking against that same requirement. Implementation and
acceptance are not two independent standards; they are two derivations of one
frozen requirement.

### 4. Boundary is pushed forward; subjectivity is consumed at alignment time

Subjectivity is resolved as early as possible, in the alignment dialogue, not
deferred to verification. A vague "analyze the market" cannot be verified
objectively; an aligned "produce a table with columns X/Y/Z plus three
conclusions, excluding investment advice" largely can. The Alignment Agent uses
a fixed elicitation checklist (output form, must-have, must-not, completion
signal, allowed free-form region) so the boundary is captured structurally, not
by luck. Residual subjectivity is allowed only as a region the human explicitly
consented to, and is the minimal possible.

### 5. Two human gates, both required

- **Light gate (requirement freeze):** the Alignment Agent *proposes* that the
  requirement is complete; the human confirms. Only the human knows whether
  anything is unsaid.
- **Heavy gate (contract authorization):** after the Requirement and Acceptance
  Agents produce the contract, the human approves the acceptance criteria and
  capability boundary, freezing an immutable `GoalExecutionRequest`. This is the
  existing `ApprovalService` freeze step and the master plan's non-negotiable
  "no scope change without human approval".

After the heavy gate the human already knows roughly what the final output will
be. Workflow B must produce no surprises; surprises are to be aligned away in
Workflow A.

### 6. Verify the product, not the process

The Phase 1 rule changes from "the alignment task must be deterministic" to:
**the alignment dialogue may be non-deterministic, but its *outputs* are
verified by deterministic exit gates** — schema validity, `RequestDraft`
admission acceptance, freeze into a valid `GoalExecutionRequest`, and a
`goal validate` / `goal plan` smoke proving Workflow B can consume it. We never
verify *how the agents talked*; only that what they emitted is a legal,
B-consumable contract.

### 7. The deterministic template alignment engine is deprecated

The current `alignment_engine` (and the structured `IntentDraft` entry surface
that assumes the human already did the agent's job) is reclassified as
`experimental`/deprecated. It is removed from the default operation surface and
the package's default exports; the code is retained only as a deterministic test
stub and is not used unless a caller invokes it explicitly. It must be
registered in `component-inventory.json` with that lifecycle class and a removal
trigger.

## Consequences

- A new Agent-driven Workflow A must be specified and (later) built on the
  existing `AgentDriver`, `AcceptancePlanner`, and `ExecutionPlanner` Ports; it
  is the "intent -> GoalContract/GoalExecutionRequest" segment that the master
  plan left to the human.
- The Phase 1 roadmap is rewritten under the "verify the product, not the
  process" rule. Tasks that build subjective machinery are themselves verified
  objectively (fixtures asserting correct accept/reject and B-consumability),
  not by judging dialogue content.
- `RequestDraftAdmission` and `ApprovalService.freeze` are kept: they already
  produce a legal `GoalExecutionRequest` and are the correct deterministic exit
  gates for Workflow A.
- This ADR does not add or change any schema, domain object, or code in this
  step. It records direction only. Schema/contract/code changes follow the
  standard order (schemas -> SPEC/ADR -> domain/ports -> adapters -> tests) when
  Workflow A is actually implemented.
- The framework-self-iteration prohibition from the master plan still holds: a
  run may not modify its own policy, validators, EvidenceGate, capability
  definitions, or top-level acceptance contract. Workflow A agents draft; only a
  human gate freezes.

## Rejected alternatives

### Keep the deterministic template alignment engine as Workflow A

Rejected. It does not understand natural language and requires the human to
pre-structure an `IntentDraft`, which means the human does the agent's job. It
delivers the low-value "fill a template" shell while skipping the valuable
"understand vague intent and self-drive contract generation" core.

### One agent does alignment, requirement, and acceptance

Rejected. A single agent authoring both the implementation requirement and the
acceptance contract reintroduces the self-judging collusion the master plan's
power separation forbids.

### Make the alignment dialogue itself command-gate decidable

Rejected. That is the original mistake. Forcing the non-deterministic dialogue
to be deterministically verifiable is exactly what reduced TASK-0063 to a
template stub. The dialogue is non-deterministic by nature; only its emitted
product is gated.

### Allow the Acceptance Agent to emit freely subjective criteria

Rejected as the default. Subjectivity must first be minimized in alignment by
constraining output shape. Residual subjective criteria are permitted only for
the human-consented free-form region and routed to the subjective gate; they are
not the normal path.
