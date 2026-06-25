---
type: Handoff
id: HANDOFF-TASK-0030-0001
schema_version: awkp/0.1
title: TASK-0030 planner adapters ready for review
description: Producer handoff for provider-neutral planner ports, bounded planner validation, content-addressed planner artifacts, AgentDriver adapter failure handling, and repair patch Evidence reuse.
status: active
owner: agent:codex-dynamic-kernel-operator
source_refs: [../task.md, ../state.json, ../artifact-manifest.json, ../evidence-manifest.json]
evidence_refs: [EVD-TASK-0030-0001, EVD-TASK-0030-0002, EVD-TASK-0030-0003]
confidence: reviewed
last_verified_at: 2026-06-25T14:34:31Z
review_after: 2026-09-25T00:00:00Z
tags: [handoff, task-0030, planner, plan-ir, repair]
---

# TASK-0030 Handoff 0001

## State

- Task: TASK-0030, Add acceptance and execution Planner adapters with bounded replan protocol.
- Branch: `task-0030-planner-adapters`.
- Producer: `agent:codex-dynamic-kernel-operator`.
- Current state intended after this handoff: review, pending independent EvidenceGate.

## Completed

- Added provider-neutral `AcceptancePlanner`, `ExecutionPlanner`, and `RepairPlanner` ports.
- Added deterministic planner context/artifact contracts with release and Context Manifest digests.
- Added read-only Planner runtime profile enforcement.
- Added fixture execution/repair planners and AgentDriver planner adapters.
- Added Planner output validation before execution through existing PlanIR compiler plus total node, depth, model call, tool call, spawned node, wall, cost, fan-out, approval, and repair-cycle limits.
- Extended `PlanPatchDraft` with `reusedEvidenceRefs` so unchanged nodes can keep explicit Evidence references.
- Added CodexSDKDriver structured passthrough for `PlanDraft`, `PlanPatchDraft`, and `AcceptanceDraft` when an explicit output contract has validated the response.

## Evidence

- `work/tasks/TASK-0030/evidence/planner-contract-report.json`
- `work/tasks/TASK-0030/evidence/verification-report.json`
- `work/tasks/TASK-0030/evidence/implementation-report.json`

## Verification

- `.venv/Scripts/python.exe -B -m unittest tests.test_planning tests.test_plan_ir tests.test_codex_driver -v`: 20 tests OK.
- `.venv/Scripts/python.exe -B scripts/check.py`: 143 tests OK, skipped=2.
- `.venv/Scripts/python.exe -B scripts/check.py --lint`: AWKP lint 0/0, AHRA lint 0.
- `git diff --check`: exit 0; no whitespace errors reported.

## Next Action

Run independent EvidenceGate review for TASK-0030 against `task.md`, `artifact-manifest.json`, `evidence-manifest.json`, and the current diff. The producing agent must not mark the task completed.

## Known Limits

- Planner output is still untrusted until `PlannerOutputValidator` accepts it and returns trusted `PlanIR`.
- This is a local reference-core slice, not a distributed planner service.
- `uv` is not available in this terminal PATH; checks used `.venv/Scripts/python.exe`.
