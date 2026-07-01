# Workflow A Formal Supervision Report

Run id: 20260701T222019+0800
Mode: supervisor only; no source code changes were made by this run.
Input intent: examples/intents/phase1-example-intent.yaml

## Scope

This run checked two surfaces:

1. Real Workflow A driver probe: default `codex-python-sdk`, no fixture driver.
2. Current locally executable end-to-end path: Workflow A fixture lifecycle produces a contract, then Workflow B executes that contract through `goal start`.

The second path verifies contract generation, gates, admission, validation, plan compilation, scheduler execution, capability audit, kernel evidence, and completion. It does not prove real Agent-driven Workflow A dialogue, because that path is blocked by findings below.

## Real Driver Probe

Commands:

- `workflow-a start`
- `workflow-a advance` with default `codex-python-sdk`
- retry `workflow-a advance` after manually creating the recorded workspace directory

Observed results:

- `workflow-a start`: ok=true; sessionId=ASESS-aadb3a70e29955af; stage=dialogue.
- First `workflow-a advance`: exitCode=2; error=`[WinError 267] ...`
- Retry after creating workspace directory: exitCode=2; error=`unsupported reference runner expected output: AlignmentTurnDecision`

Findings:

- WF-A-FORMAL-001, severity P1: `workflow-a start` records `workspaceRef` but does not create it. The default Codex driver uses `workspaceRef` as cwd, so formal `advance` can fail before the Agent output contract is even reached.
- WF-A-FORMAL-002, severity P1: `CodexSDKDriver` cannot parse Workflow A output type `AlignmentTurnDecision`. This blocks real AgentDriver-backed Workflow A at the first alignment turn.
- WF-A-FORMAL-003, severity P2: default-driver `workflow-a advance` has no obvious operator-facing timeout knob. The retry took over 60 seconds before returning the structured unsupported-output error.

## Executable E2E

Commands:

- `workflow-a start`
- `workflow-a advance --driver-ref workflow-a-fixture --enable-fixture-driver`
- `workflow-a approve-requirement`
- `workflow-a draft --driver-ref workflow-a-fixture --enable-fixture-driver`
- `workflow-a admit`
- `workflow-a authorize`
- `goal validate`
- `goal plan`
- `goal start`

Observed results:

- Gate 1 requirement approval persisted as `requirementApprovedBy=human:maintainer`.
- RequestDraft admission accepted: `accepted=true`.
- Gate 2 approval persisted to `approval.json`: `status=approved`, `decisionBy=human:maintainer`.
- `goal validate`: valid=true.
- `goal plan`: artifactDir=`D:\Work\ahra-v0.1-starter\artifacts\workflow-a-formal\20260701T222019+0800\supervised-e2e\artifacts`.
- `goal start`: goalStatus=succeeded; planStatus=succeeded; defects=[].
- Completion: complete=true; currentClaimCoverage=1.0; missingClaimRefs=[]; openDefectRefs=[].
- Kernel evidence materialized two evidence records and two gate runs.
- Output artifact exists: `workspace/outputs/summary.txt`.

Output artifact content:

```text
goal=GOAL-PHASE1-EXAMPLE-ALIGNED
plan=PLAN-7f3912e0b58a9411
node=NODE-write-summary
node_run=NRUN-c6533dbb7cf6afc6
```

## Produced Files

- `real-driver-probe/session.json`
- `real-driver-probe/logs/*.out`
- `supervised-e2e/session.json`
- `supervised-e2e/request-draft.json`
- `supervised-e2e/approval.json`
- `supervised-e2e/goal-execution-request.yaml`
- `supervised-e2e/goal-control.sqlite3`
- `supervised-e2e/artifacts/goal-start-report.json`
- `supervised-e2e/artifacts/plan-ir.json`
- `supervised-e2e/artifacts/kernel-evidence/*.json`
- `supervised-e2e/artifacts/kernel-gate-runs/*.json`
- `supervised-e2e/workspace/outputs/summary.txt`

## Conclusion

The current bounded local contract-to-execution path is healthy for this fixture scenario: gates persisted, paths were not double-resolved, Workflow B consumed the request, execution completed, and kernel evidence was materialized.

The real Agent-driven Workflow A path is not yet formally runnable in this environment. It is blocked before product validation by the default driver integration: missing workspace directory creation and unsupported Workflow A output parsing.
