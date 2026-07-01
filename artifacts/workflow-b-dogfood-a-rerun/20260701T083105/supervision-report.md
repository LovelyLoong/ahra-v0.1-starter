# Workflow B Dogfood A Supervision Report

Run directory: `artifacts/workflow-b-dogfood-a-rerun/20260701T083105`

## Scope

Route under supervision:

- `docs/architecture/agent-drivers-and-workflow-invocation.md`
- Workflow B command: `uv run python -B -m ahra.cli goal start <goal-execution-request.yaml> --allow-development-agent`
- Dogfood request source: `examples/goals/dogfood-a-alignment-session.yaml`

## Fixes Applied Before Final Run

- Development-bounded process commands were normalized to `uv run ...`.
- Local UV lookup now includes the project `.venv/Scripts` path before failing closed.
- External check evidence now records `status` and `failure_class`.
- Failed development execution worktrees are preserved and surfaced in the goal start report.
- Node execution failures for bounded security/preflight rejection now create structured defects.
- `rejected` and security/preflight classes now finalize the goal as failed instead of opening a repair loop.
- Development-bounded scheduler now uses a 300 second terminal/check grace window so deterministic checks can finish before capability grants and node lease expire.

## Local Verification

- `uv run python -B -m unittest ...` targeted TTL/security tests: passed.
- `uv run python -B scripts/check.py --lint`: passed.
- `uv run python -B scripts/check.py --test`: 315 tests passed, 1 skipped.

## Dogfood Run 1

Run directory: `artifacts/workflow-b-dogfood-a-rerun/20260701T080401`

Result:

- CLI ended with `ok=false`, `error=lease expired`.
- Internal bounded-task artifacts showed the task had reached `rejected`, but the outer SQLite goal store stayed `running`.
- Required checks passed, but policy failed because filesystem write grants became stale before final policy verification.

Evidence:

- `goal-inspect-after-run.json`
- `events-tail-after-run.jsonl`
- `artifacts/bounded-task-executor/tasks/alignment-session/attempt-1/deterministic-evidence.json`
- `artifacts/bounded-task-executor/tasks/alignment-session/attempt-1/review.json`

Finding:

- P1 fixed in this turn: development-bounded node lease/grant TTL did not cover agent execution plus deterministic check duration.

## Dogfood Run 2

Run directory: `artifacts/workflow-b-dogfood-a-rerun/20260701T083105`

Result:

- CLI returned `ok=true`.
- `goalStatus=failed`, `planStatus=failed`.
- `failure_class=rejected`.
- Defect persisted: `DEF-f6761e512f9f93d0`.
- Execution worktree was preserved:
  `artifacts/workflow-b-dogfood-a-rerun/20260701T083105/artifacts/development-worktrees/GEXEC-e52bed96d9d177b7/development-bounded-c93f4291`
- No patch was integrated into main.

Primary failure:

- Deterministic policy rejected the Agent patch:
  `task policy deleted-line limit exceeded: 864 > 800`.
- The rejected patch rewrote most of `src/ahra/alignment_session.py` and `tests/test_alignment_session.py`.

Evidence:

- `goal-start-output.json`
- `goal-inspect-after-run.json`
- `events-tail-after-run.jsonl`
- `artifact-file-index.json`
- `artifacts/bounded-task-executor/tasks/alignment-session/rejected.patch`
- `artifacts/bounded-task-executor/tasks/alignment-session/terminal-failure.json`
- `artifacts/bounded-task-executor/tasks/alignment-session/attempt-1/work-report.json`
- `artifacts/bounded-task-executor/tasks/alignment-session/attempt-1/review.json`
- `artifacts/bounded-task-executor/tasks/alignment-session/attempt-1/deterministic-evidence.json`

## Remaining Workflow Issues

1. The real AgentDriver may produce very large rewrites even when the task should be a narrow edit. The policy gate correctly rejected this run.
2. The WorkReport claimed the test command ran and failed, but deterministic evidence had no check records because policy failed first. The gate did not trust the WorkReport, but the reporting surface can confuse operators.
3. Agent first-file latency is high: run 1 first changed files around 603 seconds; run 2 around 421 seconds.
4. The dogfood execution worktree is based on Git HEAD and does not include unrelated dirty main-workspace changes. This is safe for isolation, but supervision must account for it when comparing test counts and source state.

