# AHRA Dynamic Kernel Operator

Use this skill when the user asks to inspect, validate, or exercise the current
AHRA dynamic-kernel path.

## Read First

1. `AGENTS.md`
2. `docs/architecture/authority-map.md`
3. `docs/architecture/framework-entrypoints.md`
4. `docs/architecture/component-inventory.json`
5. The current task under `work/tasks/<TASK-ID>/`

## Current Runtime Boundary

The current default executable dynamic-kernel path is the Mode C local M1
bounded path with a real Planner and real bounded Executor:

```bash
python -B scripts/run_real_agent_pilot.py --output-dir <out> --allow-model-cost
python -m ahra.cli goal validate examples/m1/goal-run-request.yaml
python -m ahra.cli goal plan examples/m1/goal-run-request.yaml
python -m ahra.cli goal start examples/m1/goal-run-request.yaml
```

That path is intentionally local and bounded. It validates one
`GoalExecutionRequest`, admits a real Planner's PlanDraft, starts durable
SQLite-backed GoalExecution state, executes through the shared Scheduler and
Capability Admission path, and supports inspect, resume, and cancel. It does
not claim to be a production orchestrator for arbitrary projects.

## Default Commands

Use these commands for current local operation and verification:

- `python -B scripts/run_real_agent_pilot.py --output-dir <out> --allow-model-cost`
- `python -m ahra.cli goal validate examples/m1/goal-run-request.yaml`
- `python -m ahra.cli goal plan examples/m1/goal-run-request.yaml`
- `python -m ahra.cli goal start examples/m1/goal-run-request.yaml`
- `python -m ahra.cli goal inspect <GEXEC-ID> --db <goal-control.sqlite3>`
- `python -m ahra.cli goal resume <GEXEC-ID> --request examples/m1/goal-run-request.yaml`
- `python -m ahra.cli goal cancel <GEXEC-ID> --db <goal-control.sqlite3> --reason <reason>`
- `python -m ahra.cli goal bridge-awkp-task <GEXEC-ID> --task <TASK-ID> --db <goal-control.sqlite3> --artifact-dir <artifact-dir> --expected-task-version <N> --producer-actor <producer> --verifier-actor <verifier> --fencing-token <token> --report <report.json>`
- `python -m ahra.cli task create <TASK-ID> --title ... --description ... --context-id ... --acceptance ...`
- `python -m ahra.cli task claim <TASK-ID> --expected-version <N> --actor <producer>`
- `python -m ahra.cli task orchestrate-review <TASK-ID> --expected-version <N> --producer-actor <producer> --verifier-actor <verifier> --fencing-token <token> --report <report.json>`
- `python -m ahra.cli task inspect <TASK-ID>`
- `python -m ahra.cli evidence-gate evaluate <TASK-ID> --expected-version <N> --report <report.json> --actor <verifier>`
- `python -m ahra.cli doctor`
- `python -B scripts/check.py`
- `python -B scripts/check.py --lint`
- `python -B scripts/check.py --test`
- `git diff --check`

On the maintainer workstation, use `.venv\Scripts\python.exe` or `uv run python`
when the bare `python` launcher is affected by host encryption tooling.

## Regression Fixture

Use this only when checking the historical fixture loop:

- `python -m ahra.cli fixture dynamic-repair --fixture tests/fixtures/dynamic-goal-project --report <report.json>`

## Rules

- Do not declare an AWKP Task completed. Completion is decided by EvidenceGate.
- Do not run or document local MCP as an operation path; the implementation was removed.
- Do not use `standard-harness`, `loop-engineering`, or `fake-reference` unless
  the user explicitly asks for the legacy compatibility workflow route.
- Treat `fixture dynamic-repair` as regression-only, not the default Goal path.
- Report the exact command, report path, and pass/fail status.
