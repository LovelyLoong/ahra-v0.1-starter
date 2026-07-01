# Workflow A Supervision Report

Run id: 20260701T214613+0800
Mode: supervision only; no task was created; no source, task state, or events files were edited by this supervision run.
Input intent: examples/intents/phase1-example-intent.yaml
Profile: profile/m1-deterministic@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
Driver: workflow-a-fixture, for local smoke supervision only.

## Summary

Workflow A completed the bounded fixture lifecycle through RequestDraft admission, Gate 2 authorization stdout, GoalExecutionRequest generation, goal validate, and goal plan.

The run did not start goal execution. The observed result is a local fixture smoke result, not proof of production-grade Agent orchestration.

## Command Results

1. workflow-a start: ok=true; sessionId=ASESS-6e0160eb0940ded0; stage=dialogue.
2. workflow-a advance: ok=true; stage=awaiting_requirement_approval; frozenRequirement="Write one governed deterministic summary artifact in the local workspace."
3. workflow-a draft before Gate 1: exitCode=2; error=requirement_not_approved.
4. workflow-a approve-requirement with agent actor: exitCode=2; error=requirement_approval_requires_human.
5. workflow-a approve-requirement with human: ok=true; stage=frozen; requirementApprovedBy=human:maintainer.
6. workflow-a draft after Gate 1: ok=true; requestId=REQ-363af306e2089062; approval status=waiting_auth.
7. workflow-a admit: ok=true; accepted=true; planDigest=sha256:a123c82c696fb1cfab191de6b821616abd0841ae8498d1a9ba13266ad3c119be; rejections=[].
8. workflow-a authorize with producer actor: exitCode=2; error="producer cannot self-authorize a RequestDraft".
9. workflow-a authorize with non-human non-producer actor: exitCode=2; error="RequestDraft freeze requires an explicit human approval actor".
10. workflow-a authorize with human: ok=true; stdout approval status=approved; GoalExecutionRequest was written.
11. goal validate: ok=true; valid=true; PlanValidationReport result=passed.
12. goal plan: ok=true; planId=PLAN-7f3912e0b58a9411; executedNodeCount=0.
13. workflow-a snapshot: ok=true; final session stage=request_drafted.

## Produced Files

Primary run files:

- artifacts/workflow-a-supervision/20260701T214613+0800/session.json
- artifacts/workflow-a-supervision/20260701T214613+0800/request-draft.json
- artifacts/workflow-a-supervision/20260701T214613+0800/approval.json
- artifacts/workflow-a-supervision/20260701T214613+0800/goal-execution-request.yaml
- artifacts/workflow-a-supervision/20260701T214613+0800/logs/*.out

Plan files were produced, but under a duplicated nested path:

- artifacts/workflow-a-supervision/20260701T214613+0800/artifacts/workflow-a-supervision/20260701T214613+0800/artifacts/goal-execution-request.json
- artifacts/workflow-a-supervision/20260701T214613+0800/artifacts/workflow-a-supervision/20260701T214613+0800/artifacts/plan-draft.json
- artifacts/workflow-a-supervision/20260701T214613+0800/artifacts/workflow-a-supervision/20260701T214613+0800/artifacts/plan-ir.json
- artifacts/workflow-a-supervision/20260701T214613+0800/artifacts/workflow-a-supervision/20260701T214613+0800/artifacts/plan-validation-report.json

## Positive Observations

- Gate 1 blocks RequestDraft creation before explicit human requirement approval.
- Gate 1 rejects a non-human approving actor.
- Gate 2 rejects producer self-authorization.
- Gate 2 rejects a non-human non-producer actor.
- RequestDraftAdmission accepted the generated draft with no rejections.
- Goal validation accepted the generated GoalExecutionRequest and compiled a passing PlanValidationReport.
- Negative Gate checks did not leave partial request or authorization output files.

## Deficiencies

WF-A-SUP-001, severity P1: Gate 2 approval is not durably persisted to the approval file.

Evidence: logs/09-authorize.out reports approval status=approved with decisionBy=human:maintainer, but approval.json remains status=waiting_auth with decisionBy=null and decidedAt=null. The code path in src/ahra/workflow_a_cli.py authorize_request loads the approval file, reconstructs ApprovalService, approves in memory, writes the GoalExecutionRequest, and returns the approved record, but does not write the approved record back to approval_path. This creates an audit-chain inconsistency between stdout and the durable approval artifact.

WF-A-SUP-002, severity P1: Relative artifactDir is double-resolved by the downstream goal plan path.

Evidence: goal-execution-request.yaml stores artifactDir as artifacts\workflow-a-supervision\20260701T214613+0800\artifacts. goal plan resolves request-relative paths from the request file parent, so the actual artifactDir became D:\Work\ahra-v0.1-starter\artifacts\workflow-a-supervision\20260701T214613+0800\artifacts\workflow-a-supervision\20260701T214613+0800\artifacts. This can hide plan artifacts from operators expecting them directly under the run artifact directory.

WF-A-SUP-003, severity P2: work/index.md is stale for recent completed workflow-A-related tasks.

Evidence: work/index.md source_refs and task table include through TASK-0077, but not TASK-0078, TASK-0079, TASK-0080, TASK-0081, or TASK-0082. This can mislead future context loading even though the task directories and EvidenceGate reports exist.

WF-A-SUP-004, severity P3: One example goal still contained stale legacy-converter wording.

Evidence: examples/goals/dogfood-a-alignment-session.yaml contained old wording that framed Workflow A as replacing the prior non-Agent deterministic converter. Architecture docs also used similar wording as historical correction text. That wording can pull agents back toward the old framing if loaded without the ADR-0009 context.

## Non-Claims

- This run did not validate real Codex/OpenAI AgentDriver behavior.
- This run did not execute goal start or mutate the supervised workspace output.
- This run did not repair the deficiencies listed above.
