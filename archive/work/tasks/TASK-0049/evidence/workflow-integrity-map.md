---
type: EvidenceReport
id: ART-TASK-0049-0001
schema_version: awkp/0.1
title: TASK-0049 workflow integrity map
description: Maps the current default M1 Goal path, explicit Mode C pilot path, and AWKP EvidenceGate path before wider Mode C work.
status: review
owner: agent:codex-dynamic-kernel-operator
task_id: TASK-0049
created_at: 2026-06-28T14:04:34.285055Z
created_by: agent:codex-dynamic-kernel-operator
---

# TASK-0049 Workflow Integrity Map

## Conclusion

The current AHRA workflow is not one undifferentiated path. It has three
separate chains that must stay separated during routing:

1. Default M1 Goal operation path: deterministic, local, and currently the
   default safe path.
2. Explicit Mode C real-Agent pilot path: experimental, opt-in, and not
   default-path approved.
3. AWKP task completion path: task-state and evidence governance, completed
   only by independent EvidenceGate.

The fresh default M1 smoke in `verification-summary.json` succeeded. No current
evidence shows a broken default M1 path. The Mode C failures from TASK-0045 to
TASK-0048 exposed defects in the real-Agent pilot connection layer and bounded
Executor adapter path, not a need to replace the whole workflow.

## Default M1 Goal Operation Path

Authority:

- `docs/architecture/framework-entrypoints.md` names the default foundation
  entrypoint as generic Goal CLI plus the dynamic-kernel Skill and repository
  docs.
- `README.md` states that the current Goal operation path is an M1
  deterministic profile, not a production distributed orchestrator.
- `skills/ahra-dynamic-kernel/SKILL.md` lists the default local commands:
  `goal validate`, `goal plan`, `goal start`, `goal inspect`, `goal resume`,
  and `goal cancel`.

Execution chain:

```text
GoalExecutionRequest
  -> profile / adapter / runtime / store admission
  -> PlanDraft loaded from request
  -> compile_plan_draft() into admitted PlanIR
  -> GoalExecution and PlanExecution records in SQLite
  -> StaticPlanScheduler
  -> CapabilityAdmission before side effects
  -> deterministic NodeExecutor for bounded_task / repair
  -> deterministic GateRunner and GoalVerificationService
  -> GoalExecution inspect / complete / resume / cancel
```

Code evidence:

- `src/ahra/goal_operations.py::GoalOperationService.start()` validates the
  admitted plan, creates durable GoalExecution and PlanExecution records,
  attaches the active plan, then runs the scheduler.
- `src/ahra/goal_operations.py::_scheduler()` registers deterministic
  executors by default. It only registers `BoundedTaskExecutor` when the
  request explicitly selects the real bounded Executor adapter.
- `src/ahra/plan_execution.py::StaticPlanScheduler._run_node()` acquires node
  lease, performs capability admission, invokes the registered executor, then
  records budget and gate results.

Fresh smoke evidence:

- `goal validate`, `goal plan`, and `goal start` were run against a copied
  request in a temporary directory.
- Result: `goalStatus=succeeded`, `planStatus=succeeded`, `nodeRunCount=2`,
  `missingArtifactCount=0`.

Boundary:

- This path is intact for the current local deterministic M1 profile.
- This does not prove production-grade orchestration or real-Agent Mode C
  stability.

## Explicit Mode C Real-Agent Pilot Path

Authority:

- `work/index.md` records that TASK-0045, TASK-0047, and TASK-0048 all preserve
  Mode C no-go / non-default boundaries.
- `scripts/run_real_agent_pilot.py` requires explicit `--allow-combined` for
  Mode C and explicit `--allow-model-cost` before the Codex SDK driver is used.

Execution chain:

```text
run_real_agent_pilot.py --mode mode_c_combined --allow-combined
  -> create isolated per-repetition request
  -> real Planner adapter proposes PlanDraft
  -> PlannerOutputValidator validates real Planner output
  -> real Executor budget normalization for real bounded nodes
  -> request PlanDraft is overwritten with admitted draft
  -> GoalOperationService.validate/start
  -> StaticPlanScheduler
  -> real BoundedTaskExecutor for bounded_task nodes
  -> TaskHarness invokes Codex AgentDriver under bounded ExecutionPolicy
  -> deterministic/internal artifact checks and node gates
  -> scorecard with planner, executor, hard-metric, and failure-class summary
```

Code evidence:

- `src/ahra/real_agent_pilot.py::_run_repetition()` blocks Mode C unless
  `allow_combined` is set, invokes the real Planner when required, then calls
  `GoalOperationService.validate()` and `start()`.
- `src/ahra/real_agent_pilot.py::_run_planner()` validates real Planner output
  and writes it back to the request before execution.
- `src/ahra/real_agent_pilot.py::_normalize_real_executor_plan_draft()` now
  applies real Executor bounded wall-time normalization after real Planner
  output.
- `src/ahra/reference_runner/bounded_task.py::BoundedTaskExecutor.execute_task()`
  builds the bounded `TaskSpec`, invokes `TaskHarness`, and maps the task result
  into `NodeExecutionResult`.

Boundary:

- Mode C is a pilot harness over the same dynamic-kernel execution service, not
  the default CLI workflow.
- TASK-0048 proves one bounded Mode C rerun for the bounded-write repair only.
  It does not prove broad stability.

## AWKP Task And EvidenceGate Path

Authority:

- `SPEC.md` and `WORKFLOW.md` separate task contract, state, event ledger,
  artifacts, evidence, and handoffs.
- `src/ahra/evidence_gate.py::evaluate_task_gate()` requires state `review`,
  expected `state_version`, independent verifier identity, parseable acceptance
  criteria, manifest hash validation, command result validation, and evidence
  refs for every passed criterion before setting `completed`.

Execution chain:

```text
task.md
  -> state.json + events.jsonl
  -> producer lease and work
  -> artifact-manifest.json + evidence-manifest.json
  -> review_requested
  -> independent EvidenceGate evaluate with expected_version
  -> evidence-gate report artifact/evidence
  -> state completed or changes_requested
  -> work/index.md generated-style sync
```

Boundary:

- Producer moves tasks to `review`, not `completed`.
- EvidenceGate completion approves only the task's stated scope. TASK-0048
  completion approves the bounded-write repair, not Mode C defaultization.

## Current Integrity Observations

1. The default M1 path is operational in a fresh temporary smoke. Current
   evidence does not support calling the whole workflow broken.
2. The Mode C failures did reveal workflow-adjacent defects: process-boundary
   cancellation, PlanIR-to-TaskSpec contract loss, budget normalization, and
   usage/capability accounting.
3. The largest remaining structural risk is lifecycle alignment: the
   default-visible `BoundedTaskExecutor` still imports `TaskHarness` from
   `standard_harness`, while component inventory classifies standard-harness as
   legacy and non-default.
4. The pilot scorecard hard metrics are useful containment summaries, but they
   are too coarse to be the only evidence for broad Mode C stability.
5. The bounded-write repair handles literal `filesystem.write` artifact paths.
   Wider Mode C work should audit non-literal globs and richer expected output
   contracts before larger live pilots.

## Routing Decision

Do not open a broad Mode C pilot yet. The correct next task is a narrow
workflow-hardening task that aligns the real bounded Executor dependency chain
and pilot invariants before any wider Mode C quality run.
