# Workflow A Optimization Plan For Workflow B

Status: Workflow B entry request plus manual planning package  
Reason: Workflow A completed once, but the run exposed human-gate and drafting
defects that should become their own optimization increment before broader use.

Canonical Workflow B entry:

- `artifacts/workflow-a-optimization-plan/20260708T000000-0700/goal-execution-request.yaml`

Validated entry command:

```powershell
uv run python -B -m ahra.cli goal validate artifacts\workflow-a-optimization-plan\20260708T000000-0700\goal-execution-request.yaml
```

Validation result recorded during manual preparation:

- `valid: true`
- `goalExecutionId: GEXEC-e42d83a629efc4e8`
- `planNodeCount: 2`
- `executableNodeCount: 1`

This document is explanatory input for that request. It is not a Workflow B
execution result and does not claim completion.

## Goal

Improve Workflow A so a human can safely approve Gate 1 and Gate 2 without
reading machine-only JSON, and so Workflow A can recover from common
AgentDriver drafting mistakes before asking for Gate 2 authorization.

## Triggering Evidence From The Recent Run

Artifacts:

- `artifacts/workflow-a-adoption-plan/20260708T000000-0700/session.json`
- `artifacts/workflow-a-adoption-plan/20260708T000000-0700/request-draft.json`
- `artifacts/workflow-a-adoption-plan/20260708T000000-0700/approval.json`
- `artifacts/workflow-a-adoption-plan/20260708T000000-0700/goal-execution-request.yaml`
- `artifacts/workflow-a-adoption-plan/20260708T000000-0700/human-gate-2-brief.md`

Observed issues:

- Human Gate 2 initially exposed only `request-draft.json` and `approval.json`,
  which are machine contracts and too costly for human review.
- One `workflow-a advance` attempt failed because the real driver returned
  malformed JSON.
- The first `workflow-a draft` attempt passed cross-alignment after one redraft
  but failed `RequestDraftAdmission` because the agents invented unregistered
  node types, invented `HumanGate-1` / `HumanGate-2`, and emitted invalid
  budgets.
- A narrow hotfix added `admissionContract` payload guidance and prompt wording,
  proving the root cause was missing pre-admission constraints rather than the
  adoption requirement itself.
- Gate 2 human readability was solved manually with a Markdown brief, but the
  desired product direction is an HTML approval page instead of Markdown.

## Non-Goals

- Do not promote Workflow A to the default route.
- Do not change Workflow B execution semantics.
- Do not replace `RequestDraft`, `ApprovalRecord`, or `GoalExecutionRequest` as
  machine authorities.
- Do not treat HTML as the approval record. The HTML page is a human briefing
  artifact; `approval.json` remains the durable machine approval record.
- Do not run target project business tests from Workflow A.
- Do not implement AHRA project adoption itself in this increment.

## Required Product Behavior

### 1. Human Gate 2 HTML Briefing

Workflow A must produce a self-contained HTML page before Gate 2 authorization.
The page must summarize the current `RequestDraft` and `ApprovalRecord` in
human terms.

Required content:

- request id, approval id, intent id, plan digest, and generated-at timestamp;
- current status and next legal action;
- what the human is being asked to authorize;
- files and path scopes that may be written;
- files and path scopes that are explicitly not authorized;
- plan node table with node id, objective, write capability, gates, risk, and
  expected outputs;
- claim coverage summary grouped by risk;
- non-goals and default-route safety notes;
- exact command that would authorize Gate 2;
- warning that Workflow B has not started yet;
- a visible checklist of human review items.

The HTML must be static and self-contained. No external scripts, remote assets,
or cloud dependencies are allowed.

### 2. HTML-Digest Binding

The HTML briefing must bind to the exact machine artifacts it summarizes.

Minimum fields:

- `requestId`;
- `approvalId`;
- `requestDraftDigest`;
- `planDigest`;
- `briefingDigest` or equivalent content fingerprint;
- source paths used to render the briefing.

Gate 2 authorization should reject, or at minimum fail closed in strict mode, if
the human tries to authorize a `RequestDraft` whose digest no longer matches the
briefing.

### 3. Explicit Workflow A Status

Add a human-readable status command or report shape for Workflow A.

It must distinguish at least:

- `dialogue`;
- `awaiting_requirement_approval`;
- `frozen`;
- `request_drafted`;
- `ready_for_gate2_briefing`;
- `waiting_auth`;
- `gate2_approved`;
- `goal_execution_request_frozen`;
- `ready_for_workflow_b`;
- terminal failure states.

The status output must show the next safe command and must explicitly say when
Workflow B has not started.

### 4. Gate 1 Human Decision Table

When alignment is not yet converged, Workflow A should return a structured
decision table, not only free-text `missingDimensions`.

Each decision should include:

- `decisionId`;
- question;
- recommended answer if available;
- alternatives;
- consequence of each choice;
- whether it blocks Gate 1;
- final human answer once supplied.

The Gate 1 freeze product remains `BoundaryContract`. The decision table is a
human review aid and trace input.

### 5. Admission-Aware Drafting As A Contract

The current `admissionContract` hotfix should be formalized. Acceptance and
Requirement agents must receive the actual registered node types, gate refs,
runtime refs, allowed capabilities, and budget rules before drafting.

Hard requirements:

- agents must not invent node types;
- agents must not invent gate refs;
- human approval is represented as `approvalRequired: true`, not as synthetic
  gate refs;
- budget minimums must be enforced by the output schema;
- free-zone boundary entries must not be used as Claim `criterionRefs`.

### 6. RequestDraftAdmission Bounded Redraft

After cross-alignment passes, Workflow A must run `RequestDraftAdmission`
before Gate 2 and feed structured admission rejections back into a bounded
redraft loop.

Expected loop:

```text
AcceptanceDraft + RequirementDraft
  -> cross-alignment gate
  -> RequestDraftAdmission
  -> if rejected and attempts remain:
       feed rejection report to Acceptance/Requirement agents
       redraft
  -> if still rejected:
       persist failure report and do not create waiting_auth approval
  -> if accepted:
       create Gate 2 briefing and waiting_auth approval
```

Admission redraft must be bounded and deterministic in state reporting.

### 7. Gate 2 Authorization Must Require Briefing

`workflow-a authorize` should require an HTML briefing path in strict mode.
The command should verify that the briefing references the same `requestId`,
`approvalId`, and request digest.

Recommended CLI shape:

```powershell
uv run python -B -m ahra.cli workflow-a brief `
  --request-draft <request-draft.json> `
  --approval <approval.json> `
  --output-html <human-gate-2.html>

uv run python -B -m ahra.cli workflow-a authorize `
  --request-draft <request-draft.json> `
  --approval <approval.json> `
  --brief-html <human-gate-2.html> `
  --output <goal-execution-request.yaml> `
  --actor human:maintainer `
  --reason "<human reason>"
```

## Proposed Implementation Nodes

### NODE-001: HTML Gate Brief Model And Renderer

Objective:

Create a small internal model and renderer for Gate 2 briefing HTML.

Candidate files:

- `src/ahra/workflow_a_briefing.py` or equivalent;
- `tests/test_workflow_a_briefing.py`;
- `src/ahra/workflow_a_cli.py`;
- `src/ahra/cli.py`.

Expected behavior:

- load `RequestDraft` and `ApprovalRecord`;
- compute stable digests;
- render self-contained HTML;
- escape all dynamic text;
- include no external resources;
- return structured metadata for CLI output.

Acceptance:

- generated HTML includes request id, approval id, plan digest, allowed writes,
  denied writes, plan nodes, and human checklist;
- generated HTML contains no raw unescaped JSON dump as the primary content;
- generated HTML does not rely on network resources;
- unit tests prove digest binding and HTML escaping.

### NODE-002: Workflow A Status Surface

Objective:

Add a human-readable `workflow-a status` command or equivalent status report.

Candidate files:

- `src/ahra/workflow_a_cli.py`;
- `src/ahra/cli.py`;
- `tests/test_workflow_a_cli.py`;
- `tests/test_cli.py`.

Acceptance:

- status reports current stage, request id, approval id when present, brief
  path when present, goal request path when present, and next safe command;
- status says explicitly when Workflow B has not started;
- status handles failed admission snapshots without crashing.

### NODE-003: Admission-Aware Drafting Contract

Objective:

Turn the current `admissionContract` hotfix into an explicit contract and test
surface.

Candidate files:

- `src/ahra/alignment_session.py`;
- `src/ahra/adapters/codex_sdk.py`;
- `tests/test_alignment_session.py`;
- `tests/test_codex_driver.py`.

Acceptance:

- AcceptanceDraft payload contains registered gate refs and explicit rule that
  human approval uses `approvalRequired`;
- RequirementDraft payload contains registered node types, gate refs, runtime
  refs, allowed capabilities, and budget rules;
- output schema rejects zero or negative `maxToolCalls` and `maxModelCalls`;
- tests prevent accidental removal of the contract payload.

### NODE-004: RequestDraftAdmission Bounded Redraft

Objective:

Add an admission-redraft loop after cross-alignment and before approval
creation.

Candidate files:

- `src/ahra/alignment_session.py`;
- `src/ahra/workflow_a_cli.py`;
- `tests/test_alignment_session.py`;
- `tests/test_workflow_a_cli.py`.

Acceptance:

- if admission rejects and redraft attempts remain, rejections are fed back to
  agents;
- if admission still rejects, session records a terminal or resumable structured
  failure and no `approval.json` is written;
- if redraft succeeds, `approval.json` and HTML briefing can be created;
- redraft count is persisted in snapshot.

### NODE-005: Gate 1 Decision Table

Objective:

Make unresolved human choices visible as structured decision records rather
than only text in `missingDimensions`.

Candidate files:

- `src/ahra/alignment_session.py`;
- `src/ahra/adapters/codex_sdk.py`;
- `tests/test_alignment_session.py`;
- `docs/architecture/intent-alignment-workflow.md`.

Acceptance:

- AlignmentTurnDecision may include decision records;
- snapshot persists decision records;
- Gate 1 cannot freeze while blocking decisions remain unanswered;
- the human-facing view groups decisions by blocking/non-blocking status.

### NODE-006: Documentation And Lifecycle Updates

Objective:

Document the new Gate 2 briefing and keep Workflow A experimental.

Candidate files:

- `docs/architecture/intent-alignment-workflow.md`;
- `docs/architecture/framework-entrypoints.md`;
- `docs/architecture/component-inventory.json`;
- `docs/policies/component-lifecycle.md` if lifecycle wording needs updates.

Acceptance:

- docs say Workflow A remains explicit experimental/non-default;
- docs say Gate 2 human approval must be based on a human-readable briefing
  package, not raw JSON;
- docs distinguish briefing artifacts from machine authority artifacts.

## Suggested Write Scope For Workflow B

Allow writes only to:

- `src/ahra/workflow_a_cli.py`;
- `src/ahra/cli.py`;
- `src/ahra/alignment_session.py`;
- `src/ahra/adapters/codex_sdk.py`;
- `src/ahra/workflow_a_briefing.py` if a new module is used;
- `tests/test_workflow_a_cli.py`;
- `tests/test_cli.py`;
- `tests/test_alignment_session.py`;
- `tests/test_codex_driver.py`;
- `tests/test_workflow_a_briefing.py` if a new test module is used;
- `docs/architecture/intent-alignment-workflow.md`;
- `docs/architecture/framework-entrypoints.md`;
- `docs/architecture/component-inventory.json`;
- `docs/policies/component-lifecycle.md` only if needed for lifecycle wording.

Do not write:

- `work/tasks/*/state.json`;
- `work/tasks/*/events.jsonl`;
- unrelated archive artifacts;
- provider SDK abstractions in `src/ahra/ports.py` unless a separate human
  approval explicitly changes the port;
- files outside the repository.

## Verification Commands

Minimum focused verification:

```powershell
uv run python -B -m unittest tests.test_alignment_session tests.test_workflow_a_cli tests.test_cli tests.test_codex_driver -v
git diff --check
```

Broader verification if implementation touches documentation or component
inventory:

```powershell
uv run python -B scripts/check.py --lint
uv run python -B scripts/check.py --test
git diff --check
```

## Human Approval Checklist

Use the HTML page in this folder:

- `artifacts/workflow-a-optimization-plan/20260708T000000-0700/human-approval-checklist.html`

The Workflow B entry request in this folder is:

- `artifacts/workflow-a-optimization-plan/20260708T000000-0700/goal-execution-request.yaml`

The HTML page is the human-readable checklist for approving this already
materialized Workflow B request. Starting the request remains a separate human
decision.

## Completion Definition

The optimization increment is complete only when:

- Gate 2 HTML briefing is generated automatically and bound to the machine
  request artifacts;
- Gate 2 authorization cannot silently rely on raw JSON review;
- Workflow A status shows the current human/action state clearly;
- admission failures can redraft or fail closed without producing an approval;
- Gate 1 missing decisions are represented as structured human choices;
- focused tests pass;
- docs preserve Workflow A as explicit experimental/non-default.
