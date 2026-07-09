---
type: historical-task-experience-candidates
id: ahra-task-experience-candidates-2026-07-08
source_scope: E:/ahra-v0.1-starter
created_at: 2026-07-08
status: draft
promotion: none
---

# AHRA Historical Task Experience Candidates

This is a read-only distillation pass over AHRA task history. It is not a
Gene/Capsule/Skill store update. Treat every entry below as a candidate that
needs human review before promotion.

## Source Inventory

- Scanned task records: 94.
- Final states: completed=85, canceled=9.
- Live task records: `work/tasks/TASK-0081` through `work/tasks/TASK-0094`.
- Archived task records: `archive/work/tasks/TASK-0001` through `TASK-0080`.
- Default-context rule: archived tasks are trace-only unless a current task,
  event, or evidence record explicitly references them.
- Evolver state observed before this distillation: no AHRA-specific Gene,
  Capsule, or Skill matched `TASK-*`, `AHRA`, `EvidenceGate`, `ClaimGraph`,
  or `PlanIR`.

## Theme Counts

These are heuristic tags from task titles, descriptions, input refs, and
acceptance criteria.

| Theme | Count | Signal |
|---|---:|---|
| evidence-review | 64 | EvidenceGate, verifier, review, evidence lineage |
| artifact-state-hygiene | 51 | artifact, manifest, archive, workspace, task-scoped paths |
| timeout-boundedness | 35 | timeout, lease, retry, node budget, bounded execution |
| workflow-b-execution | 30 | real AgentDriver, development-bounded execution, worktree isolation |
| workflow-a-alignment | 24 | alignment session, RequestDraft, Human Gate, ClaimGraph |
| dynamic-kernel-core | 21 | GoalContract, PlanIR, scheduler, capability gateway |
| control-plane-authority | 17 | CAS, leases, state transitions, authoritative state |
| human-auth-capability | 9 | ApprovalService, human authorization, network access |
| component-lifecycle | 6 | promotion readiness, authority map, component inventory |

## Candidate 1: Evidence Lineage Before Completion

**Asset shape:** Gene candidate.

**Apply when:** A task asks whether a producer run, workflow run, or code change
is complete.

**Do not apply when:** The user explicitly asks for an exploratory status
summary rather than a completion decision.

**Source tasks:** `TASK-0007`, `TASK-0024`, `TASK-0025`, `TASK-0052` through
`TASK-0056`, `TASK-0093`, `TASK-0094`.

**Reusable rule:** Completion must be derived from real evidence lineage, not
from producer self-reporting or "the command probably passed." For command
criteria, the trusted shape is command-gate evidence with valid gate-run
lineage and fingerprint, then AWKP EvidenceGate review. The agent may summarize
progress, but cannot self-declare task completion.

**Why it matters:** This is the strongest repeated AHRA invariant. It prevents
model optimism from converting partial work into accepted work.

**Promotion test:** A future Workflow B review should cite exact
`evidence-manifest.json`, verifier report, and `state.json` state before
calling a task complete.

## Candidate 2: Workflow B Must Treat Real Agents As Hostile Inputs

**Asset shape:** Gene candidate.

**Apply when:** A Workflow B or development-bounded execution uses a real agent,
real filesystem writes, real subprocesses, or a real worktree.

**Do not apply when:** The task is deterministic fixture-only and cannot touch a
real workspace.

**Source tasks:** `TASK-0072`, `TASK-0073`, `TASK-0074`, `TASK-0075`,
`TASK-0076`, `TASK-0088`.

**Reusable rule:** Before trusting a real Agent run, enforce one authoritative
node budget, a lease TTL that cannot be shorter than the agent timeout, terminal
structured failure on expiry, isolated throwaway worktree execution, out-of-
allowlist write blocking, bounded retry count, and encoding-safe subprocess
handling. Convert every paid real-agent failure into a free replay regression
when possible.

**Why it matters:** The task sequence shows that real agents fail in operational
ways before they fail in domain logic: destructive git commands, timeout budget
drift, retry overshoot, bad stderr encoding, and gate-selection crashes.

**Promotion test:** A Workflow B executor change should be able to answer:
"Which hostile scenario would catch this before a paid dogfood run?"

## Candidate 3: Acceptance-First Workflow A Is A Freeze Pipeline

**Asset shape:** Capsule candidate.

**Apply when:** Workflow A is converting human intent into a RequestDraft,
PlanDraft, or GoalExecutionRequest.

**Do not apply when:** The task is purely post-admission execution or evidence
review.

**Source tasks:** `TASK-0092`, `TASK-0093`, `TASK-0094`.

**Reusable rule:** Human Gate 1 freezes a typed boundary contract, not prose.
The Acceptance Agent runs first and produces a ClaimGraph with a digest. The
Requirement Agent can read that ClaimGraph but cannot rewrite it. Before Human
Gate 2 and RequestDraft admission, a deterministic cross-alignment gate checks
boundary entries, Claims, PlanNodes, open questions, and unresolved claim refs.
Failures fail closed with structured reports and bounded redrafts.

**Why it matters:** This turns "alignment" from a natural-language agreement
into a digest-backed handoff pipeline. It is highly reusable for future
Workflow A/B split tasks.

**Promotion test:** A future Workflow A task should reject any plan where the
planner can silently rewrite acceptance criteria.

## Candidate 4: Archive Reduces Context Entropy, It Does Not Delete Memory

**Asset shape:** Skill candidate or project-memory rule.

**Apply when:** The agent needs historical task knowledge or is tempted to load
all previous tasks into context.

**Do not apply when:** A current task, event, or evidence record names an
archived task directly; then read that exact archive record.

**Source tasks:** `TASK-0089`, `TASK-0091`; source file `work/index.md`.

**Reusable rule:** Completed old tasks are historical trace. They should be
retrieved through a small distilled index or exact references, not bulk-loaded
into the normal prompt. Durable facts should land in docs or accepted project
memory; run byproducts and execution scratch must not accumulate in active task
directories.

**Why it matters:** This explains why Evolver should not ingest all 94 tasks as
raw memory. The useful unit is a reviewed pattern with source task IDs.

**Promotion test:** A history recall step should return at most a few relevant
candidate cards plus exact task IDs, not a raw directory dump.

## Candidate 5: Dynamic Kernel Progression Should Stay Layered

**Asset shape:** Capsule candidate.

**Apply when:** Adding or reviewing dynamic-kernel capability, scheduler,
planner, or execution paths.

**Do not apply when:** The change is a repo-local utility with no execution or
verification authority impact.

**Source tasks:** `TASK-0023` through `TASK-0032`, plus `TASK-0033` through
`TASK-0045` for execution hardening.

**Reusable rule:** The safe build order is contracts first, then evidence
validity, verification/defects, PlanIR compilation, capability admission,
executor registry, scheduler/state wiring, model planner adapters, fixture
repair loop, and finally quarantine of legacy paths. Do not introduce model-
driven planning before the static execution and evidence path is stable.

**Why it matters:** This is the historical spine of AHRA. It prevents future
workflow changes from jumping straight to model autonomy before deterministic
contracts and gates exist.

**Promotion test:** A proposal for a new workflow capability should identify
which layer it touches and which lower layers are already verified.

## Candidate 6: Task-Scoped Runtime State Beats Example-Local Runtime State

**Asset shape:** Gene candidate.

**Apply when:** Creating workspaces, artifact dirs, stores, run records, or
execution byproducts for Workflow A/B dogfood.

**Do not apply when:** A disposable fixture intentionally owns its own local
runtime state and is not part of task evidence.

**Source tasks:** `TASK-0080`, `TASK-0086`, `TASK-0089`, `TASK-0091`.

**Reusable rule:** Runtime paths must derive from task/run identity and be
recorded as evidence or run records. Example-local `.ahra` state, ad hoc
scratch directories, and lingering development worktrees are not acceptable
default destinations for dogfood execution.

**Why it matters:** It creates inspectable, resumable, garbage-collectable
workflow state instead of hidden state attached to examples.

**Promotion test:** A new dogfood route should prove where artifactDir,
storePath, worktree, and evidence records live.

## Candidate 7: Canceled Tasks Are Negative Evidence, Not Failed Features

**Asset shape:** Memory rule.

**Apply when:** Mining archived tasks for reusable work.

**Do not apply when:** A canceled task was later superseded by a completed task
with a clear evidence trail.

**Source tasks:** `TASK-0011` through `TASK-0020`.

**Reusable rule:** Canceled task records should not become Genes by themselves.
They are useful as negative signals about premature infrastructure boundaries,
optional wrappers, and governance surfaces that were intentionally not taken at
that point in the roadmap.

**Why it matters:** It avoids overfitting on old abandoned directions.

**Promotion test:** Any candidate derived from a canceled task must name the
later completed task or authority doc that revived the idea.

## Candidate 8: Promotion Is A Separate Decision From Discovery

**Asset shape:** Skill candidate.

**Apply when:** A Workflow A/B run produces a promising process improvement,
new project memory, or reusable workflow instruction.

**Do not apply when:** The task is still in execution or review, or evidence is
only in temporary run notes.

**Source tasks:** `TASK-0082`, `TASK-0083`, `TASK-0084`, `TASK-0091`.

**Reusable rule:** Discovery can happen during execution, but durable assets
should be promoted only after acceptance. Good promotion targets are project
docs, project-local skills, or reviewed Evolver Gene/Capsule entries. Temporary
run notes and scratch files are not promotion authorities.

**Why it matters:** It gives Evolver a safe path: generate candidates often,
promote rarely, and only with source evidence.

**Promotion test:** A candidate asset should include source tasks, apply/avoid
conditions, verification evidence, and explicit non-authority caveats.

## First-Pass Recommendation

Promote nothing automatically. The best next step is to choose two candidates
for a trial recall flow:

1. `Workflow B Must Treat Real Agents As Hostile Inputs`
2. `Acceptance-First Workflow A Is A Freeze Pipeline`

These two are likely to improve future Workflow A/B work immediately because
they map to concrete recurring failures and current active architecture.

Suggested trial format:

```text
Before executing a Workflow A/B task, retrieve matching candidate cards by
task title and input_refs. Inject only the card's reusable rule, apply/avoid
conditions, and source task IDs. Do not inject raw historical task bodies unless
the current task explicitly references them.
```

