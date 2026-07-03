# ADR-0010: Boundary contract and acceptance-first drafting for Workflow A

- Status: accepted
- Date: 2026-07-03
- Decision owner: human:maintainer
- Amends: ADR-0009 (decisions 2 and 4 are revised; all other ADR-0009 decisions stand)

## Context

ADR-0009 defined Workflow A with three separated agents. Its decision 2 required
the Requirement Agent and the Acceptance Agent to run **in parallel and
independently, each reading only the frozen requirement, never each other's
output**, to prevent implementation-authors-the-gate collusion.

Real-driver testing (TASK-0086..0090 era) showed a structural failure mode: the
frozen requirement is natural language, so the two agents each "compile" the
same ambiguous prose independently. Their decompositions drift in granularity,
terminology, and coverage. The only coordination between them is a claim-ID
prefix string convention injected into both prompts, which aligns identifiers
but not semantics. The resulting `PlanDraft` and `ClaimGraph` chronically
misalign: plan nodes reference claims that do not exist, required claims have no
producing node, and boundary items silently drop out of both sides. This is a
consequence of the parallel-independent topology, not of prompt quality.

A second failure mode: when the human genuinely does not yet know their own
requirement, forcing full solidification through dialogue alone converges
slowly, and unstated topics remain as gray zones where drift concentrates.

## Decision

### 1. Human Gate 1 freezes a typed, ID'd boundary contract, not prose

The Gate 1 product is a **boundary contract**: a short list of entries, each
with a stable ID and one of five kinds:

- `must` — must be present in the result
- `must_not` — must be explicitly absent
- `completion_signal` — what objectively counts as done
- `free_zone` — explicitly delegated to the executing agent's discretion;
  acceptance has no authority there
- `open_question` — unresolved topic; **blocks freeze** until the human resolves
  it into one of the other kinds or removes it

The IDs do not enumerate requirement detail; they name the boundary itself. The
entry count stays at ADR-0009 checklist granularity (typically 5–15 entries).
The five kinds subsume the ADR-0009 elicitation checklist (output form is
expressed through `must` entries).

**No-gray-zone rule:** every topic surfaced in the alignment dialogue must land
in exactly one entry before freeze. Nothing may be "neither frozen nor declared
free". Free zones are an explicitly granted right, not an omission.

### 2. Acceptance-first serial drafting replaces parallel-independent drafting

This revises ADR-0009 decision 2. The drafting order becomes:

1. **Acceptance Agent runs first.** It reads only the frozen boundary contract
   and produces the `ClaimGraph`. Every Claim's `criterionRefs` must reference
   boundary entry IDs. The ClaimGraph is then digest-frozen.
2. **Requirement Agent runs second.** It reads the boundary contract **plus the
   frozen ClaimGraph** and produces the `PlanDraft`. Its nodes' `claimRefs` may
   only reference claim IDs that already exist in the frozen ClaimGraph.

Only one natural-language-to-structure translation remains (the acceptance
side); the planner performs structure-to-structure derivation.

The producer/verifier power separation is preserved and clarified: what is
forbidden is the producer **authoring or altering** the acceptance, not the
producer **seeing** it. Acceptance criteria are visible to implementers by
design, exactly as a test suite is visible to developers. The ClaimGraph digest
is captured before the Requirement Agent runs, so any tampering is detectable
and the planner has no write path into the acceptance.

### 3. A deterministic cross-alignment admission gate runs before Gate 2

Before the RequestDraft may be submitted for Gate 2 authorization, a
deterministic (non-LLM) validator checks referential integrity across the three
levels, failing closed with a structured mismatch report:

- every `PlanNode.claimRefs` entry resolves in the frozen ClaimGraph;
- every `required` Claim is covered by at least one plan node;
- every `must`, `must_not`, and `completion_signal` boundary entry is referenced
  by at least one Claim's `criterionRefs`;
- no Claim references a `free_zone` entry (acceptance has no authority there);
- no `open_question` entries exist in the frozen boundary contract.

On mismatch, the drafting agents get a bounded number of redraft attempts fed by
the mismatch report; exhaustion fails the session. This extends the existing
"untrusted draft, deterministic admission" pattern one level up: alignment is
enforced by admission, not by agent diligence.

### 4. Spike-before-freeze is an allowed alignment path

This extends ADR-0009 decision 4. When the human cannot state the boundary,
Workflow A may route a **low-cost exploratory spike** (a small bounded B run or
a manually supplied artifact) whose product serves purely as alignment material
for the dialogue. Spike output is untrusted input: it never becomes acceptance
content automatically, and the boundary contract is still frozen only by Human
Gate 1. Freezing is incremental in effect: unclear areas either block freeze as
`open_question` or are consciously granted as `free_zone`.

## Consequences

- `docs/architecture/intent-alignment-workflow.md` (the active owner) is
  rewritten to this design.
- `src/ahra/alignment_session.py` requires implementation changes:
  `draft_request` becomes serial (acceptance first, digest capture, then
  requirement), the frozen requirement snapshot becomes the boundary-contract
  structure, and the cross-alignment validator gates RequestDraft emission.
  These land through the standard contract-change order via Workflow-B-executed
  tasks; this ADR records direction only.
- A boundary-contract schema is added under `contracts/schemas/` when
  implementation is scheduled; `Claim.criterionRefs` gains the boundary-entry ID
  referent without schema change (it is already an opaque ref list).
- TASK-0090 (first self-hosted A-to-B loop) depends on the current
  alignment-session behavior and will need partial revision after the v2
  implementation lands; it is deliberately not modified by this ADR.
- Gate 2, `RequestDraftAdmission`, `ApprovalService.freeze`, and all Workflow B
  semantics are unchanged. ADR-0009 decisions 1, 3, 5, 6, 7 stand.

## Rejected alternatives

### Keep parallel-independent drafting and improve coordination prompts

Rejected. Two independent interpretations of the same ambiguous prose diverge
structurally; string-level ID conventions align identifiers, not semantics. The
observed misalignment is topology-caused and prompt tuning does not remove it.

### Plan-first ordering (planner drafts, acceptance judges the plan)

Rejected. If acceptance is derived after and from the plan, acceptance
degenerates into "prove the chosen implementation is correct" — precisely the
collusion ADR-0009 forbids. Acceptance must derive from the boundary contract
alone; the plan then targets the frozen acceptance.

### Freeze a fully enumerated requirement specification at Gate 1

Rejected. It conflicts with the reality that humans often discover their
requirement incrementally, inflates Gate 1 into a heavyweight spec review, and
reintroduces slow convergence. Only the boundary is frozen; detail inside the
boundary is the executing agent's free zone or the plan's concern.

### Let an LLM judge check plan/acceptance alignment instead of a validator

Rejected as the primary mechanism. Referential integrity across
boundary-entry/Claim/PlanNode IDs is mechanically decidable; using an LLM there
adds nondeterminism to a gate that can be exact. Semantic review remains
available as a declared Gate policy downstream, per ADR-0008.
