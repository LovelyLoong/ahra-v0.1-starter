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

The current executable dynamic-kernel path is the deterministic local fixture:

```bash
python -m ahra.cli fixture dynamic-repair --fixture tests/fixtures/dynamic-goal-project --report <report.json>
```

That path is intentionally fixture-scoped. It proves the wired Goal to Claims to
PlanIR to Scheduler to Capability to Artifact/Evidence to Completion flow. It
does not claim to be a general production orchestrator for arbitrary projects.

## Default Commands

Use these commands for current local operation and verification:

- `python -m ahra.cli fixture dynamic-repair --fixture tests/fixtures/dynamic-goal-project --report <report.json>`
- `python -m ahra.cli task inspect <TASK-ID>`
- `python -m ahra.cli evidence-gate evaluate <TASK-ID> --expected-version <N> --report <report.json> --actor <verifier>`
- `python -m ahra.cli doctor`
- `python -B scripts/check.py`
- `python -B scripts/check.py --lint`
- `python -B scripts/check.py --test`
- `git diff --check`

On the maintainer workstation, use `.venv\Scripts\python.exe` or `uv run python`
when the bare `python` launcher is affected by host encryption tooling.

## Rules

- Do not declare an AWKP Task completed. Completion is decided by EvidenceGate.
- Do not run or document MCP as a default operation path.
- Do not use `standard-harness`, `loop-engineering`, or `fake-reference` unless
  the user explicitly asks for the legacy compatibility workflow route.
- Treat the dynamic fixture report as evidence, not as a producer summary.
- Report the exact command, report path, and pass/fail status.
