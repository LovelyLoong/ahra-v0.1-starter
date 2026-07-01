# Workflow B Dogfood A Supervision Report

Run scope: execute the Workflow B development-bounded dogfood request that optimizes Workflow A alignment-session design/implementation.

## Intended Route

- Planning/document route checked:
  - `docs/architecture/agent-drivers-and-workflow-invocation.md`
  - `docs/architecture/framework-entrypoints.md`
  - `examples/goals/dogfood-a-alignment-session.yaml`
- Concrete request executed:
  - `examples/goals/dogfood-a-alignment-session.yaml`
  - `profileRef: profile/development-bounded`
  - Objective: build or improve `src/ahra/alignment_session.py` and `tests/test_alignment_session.py`.

## Commands

- `.venv\Scripts\python.exe -B -m ahra.cli goal validate examples\goals\dogfood-a-alignment-session.yaml`
- `.venv\Scripts\python.exe -B -m ahra.cli goal start examples\goals\dogfood-a-alignment-session.yaml --allow-development-agent`
- `.venv\Scripts\python.exe -B -m ahra.cli goal inspect GEXEC-c9e26a1e588ede10 --db work\tasks\TASK-0080\runs\dogfood-a-004\goal-control.sqlite3`
- `git apply --check work\tasks\TASK-0080\runs\dogfood-a-004\artifacts\bounded-task-executor\tasks\alignment-session\attempt-1\patch.diff`
- `Get-Command uv`

## Result

- `goalExecutionId`: `GEXEC-c9e26a1e588ede10`
- `planExecutionId`: `PEXEC-9d219994a4b34e81`
- `goalStatus`: `failed`
- `planStatus`: `failed`
- Failed node: `NODE-alignment-session`
- Skipped node: `NODE-goal-verification` remained `pending`
- Completion:
  - `complete`: `false`
  - missing claims: `CLM-ALIGNMENT-SESSION`, `CLM-GOAL-COMPLETE`
  - current claim coverage: `0.0`

## Produced Data

- Control store:
  - `work/tasks/TASK-0080/runs/dogfood-a-004/goal-control.sqlite3`
- Saved supervision outputs:
  - `artifacts/workflow-b-dogfood-a-supervision/20260701T222925+0800/goal-validate-output.json`
  - `artifacts/workflow-b-dogfood-a-supervision/20260701T222925+0800/goal-inspect-after-run.json`
  - `artifacts/workflow-b-dogfood-a-supervision/20260701T222925+0800/events-tail.jsonl`
- Bounded executor artifacts:
  - `work/tasks/TASK-0080/runs/dogfood-a-004/artifacts/bounded-task-executor/tasks/alignment-session/attempt-1/work-report.json`
  - `work/tasks/TASK-0080/runs/dogfood-a-004/artifacts/bounded-task-executor/tasks/alignment-session/attempt-1/patch.diff`
  - `work/tasks/TASK-0080/runs/dogfood-a-004/artifacts/bounded-task-executor/tasks/alignment-session/attempt-1/deterministic-evidence.json`
  - `work/tasks/TASK-0080/runs/dogfood-a-004/artifacts/bounded-task-executor/tasks/alignment-session/attempt-1/review.json`
  - `work/tasks/TASK-0080/runs/dogfood-a-004/artifacts/bounded-task-executor/tasks/alignment-session/terminal-failure.json`
  - `work/tasks/TASK-0080/runs/dogfood-a-004/artifacts/bounded-task-executor/tasks/alignment-session/rejected.patch`

## Observations

- The agent produced a real patch and work report.
- The patch changed only the allowed files:
  - `src/ahra/alignment_session.py`
  - `tests/test_alignment_session.py`
- Policy passed with no sensitive file violations.
- Required artifact existence checks passed.
- `git apply --check` passed for `patch.diff`, so the rejected patch is at least applicable to the current checkout.
- The workflow rolled the development worktree back and removed it after rejection. The patch is preserved as `patch.diff` and `rejected.patch`.

## Blocking Failure

The deterministic gate failed because the required process check could not start:

```text
uv run python -B scripts/check.py --test
[WinError 2] system cannot find the file specified
```

`Get-Command uv` also failed in the current shell. The request hard-codes `uv run ...`, while this maintainer workstation route commonly uses `.venv\Scripts\python.exe` when `uv` or bare `python` is not available.

## Workflow Issues

1. P1: The dogfood request uses `uv run python -B scripts/check.py --test` as a required check without a resolver/fallback to the active workstation Python entrypoint. This makes the Workflow B run fail for environment wiring rather than implementation quality.
2. P1: `goal start` stdout stays silent until the final JSON, even though executor heartbeats are written to `events.jsonl`. For long real-Agent runs, the caller cannot see progress without inspecting internal artifacts.
3. P2: Runtime heartbeats are recorded in `bounded-task-executor/events.jsonl`, but mid-run `goal inspect` showed NodeRun lease `heartbeat_at` still at startup time. Event heartbeat and durable NodeRun lease heartbeat are not visibly synchronized during execution.
4. P2: Rejected development worktree is deleted after rollback. The patch is preserved, but the exact runnable mutated workspace is not available for post-failure test reproduction.
5. P2: Terminal failure has `defects: []` in top-level `goal start` output. A failed dogfood optimization produces evidence and terminal failure records, but no defect object for follow-up workflow repair.
6. P3: The executor work report claims the required verification command was run, while also noting it could not complete because `uv` is unavailable. The report format should distinguish "attempted but failed to start" from "verification command completed and failed".

## Immediate Follow-up Candidate

Make development-bounded required process checks resolve through the same workstation-safe Python entrypoint policy documented in `AGENTS.md` and `docs/architecture/framework-entrypoints.md`, or update this dogfood request to use the active entrypoint explicitly.
