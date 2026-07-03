# Defect: Workflow A draft stage contract omits nested apiVersion

**Defect ID**: DEF-wf-a-draft-contract-apiversion
**Created**: 2026-07-03
**Severity**: blocker (Workflow A cannot produce a RequestDraft with a real AgentDriver)
**Status**: fixed
**Fixed in**: alignment_session.py:605-656 (2026-07-03)
**Discovered during**: TASK-0090 (first real-driver Workflow A -> B self-hosting run)

## Summary

`ahra workflow-a draft` fails deterministically with a real `codex-python-sdk`
driver: `ClaimGraph apiVersion must be ahra.dev/v1alpha1`. The Acceptance Agent
output contract does not tell the Agent that the nested `claimGraph` object must
carry `apiVersion` / `kind` / `claims`, but the downstream parser requires them.
Workflow A therefore cannot emit a RequestDraft on the real-driver path, so the
TASK-0090 A->B loop is blocked at the A stage.

## Reproduction

1. `ahra workflow-a start examples/intents/task-0090-binding-rule-intent.yaml --session .../session.json ...`
2. `ahra workflow-a advance --session .../session.json --message "<requirement>" --driver-ref codex-python-sdk` -> converged, stage `awaiting_requirement_approval` (works).
3. `ahra workflow-a approve-requirement --session .../session.json --actor human:maintainer` -> stage `frozen` (works).
4. `ahra workflow-a draft --session .../session.json --request-draft .../request-draft.json --approval .../approval.json --driver-ref codex-python-sdk`
   -> `{"ok": false, "error": "ClaimGraph apiVersion must be ahra.dev/v1alpha1"}`

Observed twice, back-to-back, identical result. Not flaky; deterministic.

## Root cause

- `src/ahra/alignment_session.py:614-622` `_output_contract(ACCEPTANCE_DRAFT_OUTPUT)`
  declares `claimGraph` only as `{"type": "object"}`. No `apiVersion`, `kind`,
  or `claims` requirement is communicated to the Agent.
- `src/ahra/acceptance_contracts.py:130` `ClaimGraph.from_mapping` calls
  `_require_api_version` (`:449-451`), hard-requiring
  `apiVersion == "ahra.dev/v1alpha1"`.
- The CodexSDKDriver prompt (`src/ahra/adapters/codex_sdk.py:205-210`) instructs
  the Agent to "return JSON that validates the supplied contract exactly ... do
  not add fields outside the output contract." Since the contract omits
  `apiVersion`, a well-behaved Agent omits it, and parsing throws.
- Contract and parser are inconsistent: the parser demands a field the contract
  never asks for.

### Second, latent instance of the same defect

`_output_contract(REQUIREMENT_DRAFT_OUTPUT)` (`:605-613`) declares `planDraft`
only as `{"type": "object"}`, while `src/ahra/plan_ir.py:283`
`PlanDraft.from_mapping` also calls `_require_api_version`. Parsing order in
`_request_from_agent_outputs` (`:540` claim graph, `:542` plan) hits the
ClaimGraph failure first, so the PlanDraft failure is currently masked. Fixing
only ClaimGraph will surface the identical PlanDraft failure next.

## Why this was not caught earlier

`workflow-a draft` had only ever been exercised with `WorkflowAFixtureDriver`
(`src/ahra/workflow_a_cli.py:29`), a deterministic fixture that hard-codes valid
`apiVersion` values. The fixture masked the contract under-specification. The
real Codex driver on this path appears to be exercised for the first time here,
which is exactly the "non-fixture proof" TASK-0090 was meant to establish.

## Secondary observation (error surfacing)

When the draft parse fails, the raw Agent output is not persisted and the
session stays at stage `frozen` with no `agentError` snapshot (only
`agent_driver_timeout` writes an error snapshot). The failing raw JSON is
therefore lost, which makes contract-mismatch debugging harder than it should
be. Consider persisting the raw Agent output on contract-validation failure too.

## Impact

- Workflow A real-driver path cannot produce a RequestDraft.
- TASK-0090 A->B loop is blocked at the A stage; the milestone cannot complete
  until the contract is corrected.
- No data loss; no code was changed while documenting this defect.

## Boundary note

Per the maintainer's explicit instruction not to intervene in the workflow, no
Workflow A / kernel code and no Agent output were modified. This record is
diagnosis only. Remediation (correcting `_output_contract` to require the nested
`apiVersion`/`kind`/`claims` for both `claimGraph` and `planDraft`, plus a
regression test that runs `draft` against a contract-faithful stub Agent) awaits
maintainer authorization.

## References

- Session: work/tasks/TASK-0090/runs/loop-001/session.json (stage `frozen`)
- Intent: examples/intents/task-0090-binding-rule-intent.yaml
- Contract: src/ahra/alignment_session.py:591-625
- Parser: src/ahra/acceptance_contracts.py:130,449; src/ahra/plan_ir.py:283
- Fixture that masked it: src/ahra/workflow_a_cli.py:29
- Related: DEF-manual-bypass-awkp, TASK-0086/0087/0088 (WF-A-FORMAL-001..003)
