---
type: Architecture
id: ARCH-framework-entrypoints
schema_version: awkp/0.1
title: Framework entrypoints
description: Defines the current default way humans and agents operate this Agent workflow foundation.
status: active
owner: team:platform
source_refs:
  - ../../AGENTS.md
  - ../../README.md
  - component-inventory.json
evidence_refs: [EVD-TASK-0051-0003]
confidence: reviewed
last_verified_at: 2026-06-29T07:25:35Z
review_after: 2026-09-25T00:00:00Z
tags: [architecture, entrypoint, cli, skill, dynamic-kernel]
---

# Summary

The default foundation entrypoint is **Mode C real-Agent pilot runner plus the
generic Goal CLI and repository documentation**.

No project-local Skill is currently active. The previous local Skill entrypoints
were retired during the Evolver-backed Skill replacement transition. A new
project-local Skill becomes part of the default operation surface only after it
is produced, reviewed, and registered in `AGENTS.md` and the component
inventory.

The current default real-Agent path is local and bounded. It runs Mode C through
one generic M1 `GoalExecutionRequest` with a real Planner and real bounded
Executor:

```text
GoalExecutionRequest
  -> profile, adapter, runtime and store admission
  -> real Planner returns untrusted PlanDraft
  -> admitted PlanIR
  -> durable GoalExecution in SQLite
  -> StaticPlanIRScheduler, PlanExecution and NodeRun leases
  -> CapabilityAdmission before executor side effects
  -> real bounded Executor produces Artifact and Evidence v2 records
  -> deterministic GateRun-backed verification
  -> GoalExecution completion, resume or cancel
  -> AWKP EvidenceGate for task completion
```

This is the default local M1 bounded path after `TASK-0051`. It is not a claim
that AHRA already provides a production-grade distributed orchestrator for
arbitrary projects.

# Current Operation Surface

The default local operation surface is:

- `python -B scripts/run_real_agent_pilot.py --output-dir <out> --allow-model-cost`
- `python -m ahra.cli goal validate examples/m1/goal-run-request.yaml`
- `python -m ahra.cli goal plan examples/m1/goal-run-request.yaml`
- `python -m ahra.cli goal start examples/m1/goal-run-request.yaml`
- `python -m ahra.cli goal start <development-request.yaml> --allow-development-agent`
- `python -m ahra.cli goal inspect <GEXEC-ID> --db <goal-control.sqlite3>`
- `python -m ahra.cli goal resume <GEXEC-ID> --request examples/m1/goal-run-request.yaml`
- `python -m ahra.cli goal cancel <GEXEC-ID> --db <goal-control.sqlite3> --reason <reason>`
- `python -m ahra.cli goal bridge-awkp-task <GEXEC-ID> --task <TASK-ID> --db <goal-control.sqlite3> --artifact-dir <artifact-dir> --expected-task-version <N> --producer-actor <producer> --verifier-actor <verifier> --fencing-token <token> --report <report.json>`
- `python -m ahra.cli workflow-sequence run examples/workflows/phase1-sequence.yaml`
- `python -m ahra.cli task create <TASK-ID> --title ... --description ... --context-id ... --acceptance ...`
- `python -m ahra.cli task claim <TASK-ID> --expected-version <N> --actor <producer>`
- `python -m ahra.cli task orchestrate-review <TASK-ID> --expected-version <N> --producer-actor <producer> --verifier-actor <verifier> --fencing-token <token> --report <report.json>`
- `python -m ahra.cli task inspect <TASK-ID>`
- `python -m ahra.cli evidence-gate evaluate <TASK-ID> --expected-version <N> --report <report.json> --actor <verifier>`
- `python -m ahra.cli doctor`
- `python -B scripts/check.py`
- `python -B scripts/check.py --lint`
- `python -B scripts/check.py --test`
- `python -B scripts/lint_awkp.py`
- `git diff --check`

On the maintainer workstation, `.venv\Scripts\python.exe` or `uv run python`
may be used for the same commands when the bare Python launcher is affected by
host encryption tooling.

# Mode C Default Surface

`TASK-0051` promoted Mode C to the default live local path for the tested M1
bounded profile. The command runs a real Planner plus real bounded Executor:

- `python -B scripts/run_real_agent_pilot.py ... --allow-model-cost`

The legacy `--allow-combined` flag is accepted for compatibility but is no
longer the gate that decides whether Mode C may run. Real model spending still
requires explicit `--allow-model-cost`. The TASK-0051 approval covers the fresh
three-repetition local M1 bounded evidence set only; it does not prove
production-grade orchestration for arbitrary projects.

# CLI Boundary

The CLI wrapper is intentionally narrow and must not invent runtime logic. It
exposes existing Python services:

- `goal validate`
- `goal plan`
- `goal start`
- `goal inspect`
- `goal resume`
- `goal cancel`
- `goal bridge-awkp-task`
- `workflow-sequence run`
- `task create`
- `task claim`
- `task orchestrate-review`
- `task inspect`
- `evidence-gate evaluate`
- `doctor`

The default CLI help must expose `workflow-sequence run` as the governed
multi-task operation surface. It must not expose demo commands,
`fake-reference`, or deprecated workflow modules. Historical workflow
compatibility remains reachable only when explicitly requested by a caller that
already knows that compatibility route. The local MCP server implementation has
been removed.

# Experimental Workflow A Lifecycle

`ahra workflow-a ...` is an explicit experimental lifecycle for ADR-0009 intent alignment sessions only. It exposes `start`, `advance`, `snapshot`, `approve-requirement`, `draft`, `admit`, and `authorize` so local operators can exercise Workflow A products without placing `component:alignment-session-manager` on the default execution path.

Default routing must not call `workflow-a` implicitly. Explicit `workflow-a` use under the TASK-0090 Workflow A plus B procedure is a governed work-selection path and does not make `workflow-a` an implicit CLI default route. `workflow-a draft` requires Human Gate 1 before RequestDraft creation, and `workflow-a authorize` uses ApprovalService Gate 2 to freeze a GoalExecutionRequest only for a human approval actor. Promotion to default-visible requires EvidenceGate-completed prerequisite tasks for the independent semantic/code-review gate, task-scoped dogfood paths, and Workflow A CLI lifecycle, plus EvidenceGate-approved non-fixture proof that an authorized Workflow A request is consumed by Workflow B through `goal validate`, `goal plan`, and `goal start`. TASK-0090 proves that explicit A+B work route separately from component promotion; until a component-lifecycle promotion task approves default visibility, `workflow-a` remains explicit experimental surface only.

# Regression Dynamic Fixture

The dynamic repair fixture is now a regression-only profile. It must continue to
demonstrate:

- Goal input before task decomposition.
- Claims and Gates before PlanIR.
- Planner output compiled and admitted before execution.
- Capability denial before side effect.
- Artifact and Evidence records for every accepted node result.
- Defect creation with reproduction and repair boundary.
- Selective reverification with documented Evidence reuse.
- Completion that rejects stale, uncovered, or open-defect evidence.

It is not the default operation entrypoint for new Goal runs.

# Legacy Compatibility

`standard-harness`, `loop-engineering`, old workflow request schemas, the
reference runner compatibility path, and `fake-reference` are deprecated legacy
assets. They are retained for regression tests and migration trace. They are
frozen for default-route purposes and must not receive new default-path
features.

The local MCP server and `src/ahra/demo.py` have been deleted from the current
implementation. Historical references remain trace-only.

# Archive Boundary

Completed task directories remain traceable audit records. They are excluded
from normal Context Builder read order unless the current task, event, evidence
record, or user request explicitly references them.
