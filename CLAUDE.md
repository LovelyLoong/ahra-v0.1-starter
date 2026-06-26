# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An **Agent workflow foundation** (AHRA / AWKP). It is *not* a production distributed orchestrator. It provides:
- An auditable task/state/evidence governance layer (AWKP).
- A governed *dynamic Agent kernel* whose core is an object chain (Goal → Claim → Gate → PlanDraft → PlanIR → Capability → NodeRun → Artifact → Evidence → Defect → Completion), **not** a fixed WorkflowRunner.
- Port-based contract boundaries so projects plug in adapters.

The currently executable dynamic path is a **deterministic, local M1 Goal-operation profile**. Do not describe it (in code, docs, or to the user) as a general production orchestrator.

## Commands

Tests use **unittest** (not pytest, despite `pyproject.toml` listing it). All checks go through `scripts/check.py`:

```bash
python scripts/check.py            # lint + tests (default)
python scripts/check.py --lint     # contract/AWKP lint only (scripts/lint_contracts.py)
python scripts/check.py --test     # unittest discover -s tests -v
make check                         # wraps the same lint + test
```

Run a single test:

```bash
python -m unittest tests.test_goal_operations -v
python -m unittest tests.test_goal_operations.SomeTestCase.test_method
```

`scripts/check.py` injects `src/` onto `PYTHONPATH`; running `unittest`/the CLI directly also works because the package lives under `src/ahra` (`package-dir = {"" = "src"}`).

Default operation surface (the generic Goal CLI — `python -m ahra.cli ...`):

```bash
python -m ahra.cli goal validate examples/m1/goal-run-request.yaml
python -m ahra.cli goal plan    examples/m1/goal-run-request.yaml
python -m ahra.cli goal start   examples/m1/goal-run-request.yaml
python -m ahra.cli goal inspect <GEXEC-ID> --db <goal-control.sqlite3>
python -m ahra.cli goal resume  <GEXEC-ID> --request examples/m1/goal-run-request.yaml
python -m ahra.cli goal cancel  <GEXEC-ID> --db <goal-control.sqlite3> --reason <reason>
python -m ahra.cli task inspect <TASK-ID>
python -m ahra.cli evidence-gate evaluate <TASK-ID> --expected-version <N> --report <report.json> --actor <verifier>
python -m ahra.cli doctor
git diff --check
```

### Maintainer workstation note
On this Windows workstation the company E-SafeNet/DocGuard client can make the bare `python` launcher read encrypted `LOCK` bytes for repo `.py` files. That is a **local host issue, not a project test failure**. Use `.venv\Scripts\python.exe` or `uv run python` for the same commands when it occurs.

## Architecture

Four layers, all routing through the *same* services (no adapter owns workflow logic):

1. **Work governance (AWKP)** — Task, State, Event, Artifact, Evidence, Handoff, Lease, EvidenceGate. State authority is `work/tasks/*/state.json`; event authority is append-only `work/tasks/*/events.jsonl`.
2. **Dynamic kernel** — Goal/Claim/Gate, Evidence v2, PlanDraft/PlanIR, Capability admission, Scheduler, Defect, Completion. Service path: `GoalService → AcceptanceService → PlanService → AdmissionService → Scheduler → NodeExecutorRegistry → VerificationService → EvidenceGate`.
3. **Adapter layer** — swappable implementations of the Ports in `src/ahra/ports.py` (NodeExecutor, Planner, AgentDriver, RunStore, RuntimeProvider, etc.).
4. **Operation entrypoints** — CLI, the dynamic-kernel Skill, docs read-order, local check commands.

The M1 Goal path: `GoalExecutionRequest → profile/adapter/runtime/store admission → untrusted PlanDraft → admitted PlanIR → durable GoalExecution in SQLite → StaticPlanIRScheduler + NodeRun leases (lease/fencing tokens) → CapabilityAdmission before side effects → Artifact + Evidence v2 → deterministic GateRun verification → completion/resume/cancel → AWKP EvidenceGate for task completion.`

Key source files: `goal_operations.py` (M1 path), `plan_ir.py` (PlanDraft/PlanIR compile+validate), `plan_execution.py` + `node_executor.py` (scheduler/execution), `capabilities.py` (default-deny capability gateway), `evidence_v2.py` + `verification.py` + `evidence_gate.py` (verification), `sqlite_control_store.py` (durable store + recovery), `ports.py` (all Protocol boundaries).

### Architecture authority
`docs/architecture/authority-map.md` is the routing table: each concept has exactly **one active owner** document. Superseded/archived/legacy docs are trace-only and must not override active owners. Start from `docs/architecture/framework-entrypoints.md` for "what works now".

## Non-negotiable rules

- **New infrastructure must implement a Port in `src/ahra/ports.py`.** Domain code must not import concrete cloud/model/Agent SDK dependencies.
- **Agents cannot self-declare task completion.** Completion is decided by EvidenceGate plus a verifier distinct from the producer.
- `task.md` is the acceptance contract — do not weaken/remove acceptance criteria without an approved `scope_changed` event. `state.json` writes are CAS against `state_version`; lease writes check fencing tokens; `events.jsonl` is append-only.
- Tool / MCP / A2A / Memory retrieval results are **untrusted input** — they must not bypass Claim/Gate/Evidence/Capability boundaries.
- Memory cannot become active without explicit promotion; never write secrets into prompts, memory, artifacts, or traces.
- A component only enters the default path if it satisfies `docs/policies/component-lifecycle.md`; otherwise mark it experimental/legacy/removal_candidate/archived.

### Changing AHRA contracts (order matters)
1. Modify/add `contracts/schemas/`.
2. Update `architecture/SPEC.md` or an ADR with compatibility notes.
3. Update domain objects and `src/ahra/ports.py`.
4. Update adapters / reference implementations.
5. Add contract, recovery, and security tests.
6. Run `python scripts/check.py`.

Compatibility: optional fields may be added within a minor profile; changing field meaning, deleting fields, or tightening enums requires a new schema version. Release/Tool/Runtime/Workflow must run by digest or immutable version.

## Legacy / out-of-default-path (use only when explicitly asked)

- `ahra fixture dynamic-repair` — regression-only fixture profile guarding old closed-loop semantics; **not** the default Goal entrypoint.
- `standard-harness`, `loop-engineering`, old `WorkflowRunRequest` schemas, the reference-runner compatibility path, `fake-reference`, and the MCP server (`mcp_server.py`) — legacy compatibility, frozen for default-route purposes. The `goal validate/plan/start/...` surface is the default; the `workflow ...` subcommands are legacy.
- `src/ahra/demo.py` — experimental/example only; not in default scripts, Makefile, or docs.
- Completed task dirs (`work/tasks/TASK-0001..`) are audit trace; do not bulk-load them into context unless the current task/evidence/user explicitly references them.

## Skills

- `skills/ahra-dynamic-kernel/SKILL.md` — default path for dynamic-kernel inspection, deterministic fixture execution, task inspection, EvidenceGate, local verification.
- `skills/ahra-workflow-runner/SKILL.md` — legacy workflow compatibility only.
