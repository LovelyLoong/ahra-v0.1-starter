# Workflow B Dogfood A Continuation Handoff

Date: 2026-07-01

## Current Main Commits

- `730da88` `Finalize workflow A dogfood repairs`
- `bd774c4` `Clarify skipped deterministic checks in work reports`

## Current Route

The intended dogfood route is:

1. Use Workflow B `profile/development-bounded`.
2. Use a real AgentDriver through `--allow-development-agent`.
3. Execute `examples/goals/dogfood-a-alignment-session.yaml`.
4. Improve Workflow A's experimental `alignment_session` / `workflow-a` path.

The active Workflow A authority is `docs/architecture/intent-alignment-workflow.md`.
`docs/architecture/agent-drivers-and-workflow-invocation.md` is legacy workflow
compatibility context, not the Workflow A authority.

## Last Formal Dogfood Result

Latest formal run directory:

`artifacts/workflow-b-dogfood-a-rerun/20260701T083105`

Result:

- CLI returned `ok=true`.
- `goalStatus=failed`.
- `planStatus=failed`.
- `failure_class=rejected`.
- Defect persisted: `DEF-f6761e512f9f93d0`.
- No Agent patch was integrated into `main`.

Primary failure:

- Deterministic policy rejected the real-Agent patch:
  `task policy deleted-line limit exceeded: 864 > 800`.
- The rejected patch rewrote most of `src/ahra/alignment_session.py` and
  `tests/test_alignment_session.py`.

Committed evidence includes:

- `artifacts/workflow-b-dogfood-a-rerun/20260701T083105/goal-start-output.json`
- `artifacts/workflow-b-dogfood-a-rerun/20260701T083105/goal-inspect-after-run.json`
- `artifacts/workflow-b-dogfood-a-rerun/20260701T083105/events-tail-after-run.jsonl`
- `artifacts/workflow-b-dogfood-a-rerun/20260701T083105/artifact-file-index.json`
- `artifacts/workflow-b-dogfood-a-rerun/20260701T083105/artifacts/bounded-task-executor/tasks/alignment-session/rejected.patch`
- `artifacts/workflow-b-dogfood-a-rerun/20260701T083105/artifacts/bounded-task-executor/tasks/alignment-session/terminal-failure.json`

Local-only preserved execution worktree:

`artifacts/workflow-b-dogfood-a-rerun/20260701T083105/artifacts/development-worktrees/GEXEC-e52bed96d9d177b7/development-bounded-c93f4291`

The preserved worktree is intentionally ignored by Git because it is a full
workspace copy and contains `.venv`. Use the committed `rejected.patch` for
portable review.

## Fixes Already Applied After Dogfood

- Development-bounded command entry normalized to `uv run ...`.
- Project `.venv/Scripts` is searched for local UV execution.
- Check evidence records `status` and `failure_class`.
- Failed development worktrees are preserved and surfaced.
- Rejected/security/preflight failure classes now produce structured defects and
  finalize failed goals instead of opening an inappropriate repair loop.
- Development-bounded terminal write grace increased to cover long finalization.
- WorkReport self-reported verification commands are no longer presented as
  deterministic check facts when policy fails first. Deterministic evidence now
  records `check_execution_status`, `check_skip_reason`, and
  `agent_reported_verification_commands`.

Validation after the WorkReport display fix:

```powershell
.venv\Scripts\uv.exe run python -B -m unittest tests.test_reference_runner.StandardHarnessTests.test_policy_failure_marks_agent_reported_verification_as_unverified
.venv\Scripts\uv.exe run python -B scripts/check.py --lint
.venv\Scripts\uv.exe run python -B scripts/check.py --test
```

Observed result:

- Targeted regression passed.
- Lint passed.
- Full test suite passed: `316 tests`, `1 skipped`.

## Next Context Continuation

Start with:

```powershell
cd D:\Work\ahra-v0.1-starter
git status --short
git log --oneline -3
.venv\Scripts\uv.exe run python -B scripts/check.py --lint
.venv\Scripts\uv.exe run python -B scripts/check.py --test
```

Do not reuse the old request id, idempotency key, artifact dir, or sqlite store.
Create a fresh copy of `examples/goals/dogfood-a-alignment-session.yaml` with
new values for:

- `metadata.requestId`
- `metadata.idempotencyKey`
- `spec.artifactDir`
- `spec.store.path`

Then run:

```powershell
.venv\Scripts\uv.exe run python -B -m ahra.cli goal validate <new-goal-request.yaml>
.venv\Scripts\uv.exe run python -B -m ahra.cli goal start <new-goal-request.yaml> --allow-development-agent
```

Supervise these points in the next run:

- Whether the real Agent still attempts a broad rewrite.
- Whether policy rejection is correctly classified as `rejected`.
- Whether `deterministic-evidence.json` includes the new check execution fields.
- Whether `node-gates.json` distinguishes skipped deterministic checks from
  executed checks.
- Whether a structured defect is created.
- Whether the execution worktree is preserved without integrating failed changes
  into `main`.

