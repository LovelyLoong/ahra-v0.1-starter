---
type: WorkItem
id: TASK-0038
schema_version: awkp/0.1
title: Expose a generic Goal operation CLI and adapter profile
description: Create a non-fixture-specific CLI and service entrypoint that validates, plans, starts, inspects, resumes and cancels durable GoalExecutions.
context_id: CTX-ahra-dynamic-kernel
priority: P1
risk_level: R2
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-26T00:00:00Z
depends_on: [TASK-0037]
input_refs:
  - ../../../docs/architecture/framework-entrypoints.md
  - ../../../docs/architecture/goal-execution-lifecycle.md
  - ../../../src/ahra/cli.py
  - ../../../src/ahra/planning.py
  - ../../../src/ahra/plan_execution.py
  - ../../../skills/ahra-dynamic-kernel/SKILL.md
output_contract:
  - kind: goal_execution_request_contract
  - kind: goal_operation_service
  - kind: goal_cli_commands
  - kind: adapter_profile_registry
  - kind: generic_run_artifacts
  - kind: skill_and_docs_update
  - kind: cli_smoke_report
---

# Goal

Make the dynamic kernel operable for an arbitrary small local project through one generic Goal request instead of a hard-coded dynamic-repair fixture command.

# Why now

M1 cannot be tested as a product path while the CLI imports a scenario-specific function. The CLI must expose stable services without owning orchestration logic.

# Scope

- Define GoalExecutionRequest and optional resume/cancel request schemas.
- Add a GoalOperationService that wires accepted adapters and stores through registries.
- Add CLI commands: goal validate, plan, start, inspect, resume and cancel.
- Support a deterministic M1 profile using generic adapters and project configuration.
- Keep provider/model selection explicit; do not make one vendor part of core.
- Write standard Artifact, Event, GateRun, Evidence and scorecard locations.
- Update README, framework entrypoints, dynamic-kernel Skill and component inventory.
- Keep the old fixture command as an explicit regression profile until migration tests pass.

# Non-goals

- Do not implement workflow logic inside argparse handlers.
- Do not make the real Agent adapter the default.
- Do not remove legacy workflow compatibility in this Task.
- Do not add a dashboard.
- Do not add distributed scheduling.

# Architectural invariants

- CLI wraps the same Python services used by tests.
- Goal request is validated before any planner or side effect.
- Operation profiles are immutable/versioned and explicitly selected.
- Unknown adapter/store/runtime refs fail closed.
- Resume uses durable GoalExecution identity, not chat history.
- CLI cannot mark an AWKP Task completed.

# Implementation slices

1. Define request/config contracts.
2. Build GoalOperationService and registries.
3. Implement validate and plan commands.
4. Implement start, inspect, resume and cancel.
5. Create generic deterministic example/profile.
6. Update docs, Skill, inventory and migration tests.

# Acceptance criteria

- [ ] A project-specific GoalExecutionRequest validates without importing dynamic_fixture.py.
- [ ] goal plan produces acceptance artifacts, PlanDraft validation and admitted PlanIR without executing Nodes.
- [ ] goal start creates a durable GoalExecution and begins the same service path used by tests.
- [ ] goal inspect reports Goal/Plan/Node/Gate/Evidence/Defect/capability state and metrics.
- [ ] goal resume continues from SQLite in a new process.
- [ ] goal cancel propagates through GoalExecution, PlanExecution and active NodeRuns.
- [ ] Unknown profiles, adapters, drivers, stores and runtime refs fail closed with structured errors.
- [ ] The CLI contains no direct NodeExecutor or GateRunner orchestration.
- [ ] Default docs and Skill identify the generic Goal path while retaining the old fixture as regression-only.
- [ ] SG-8 generic durable operation smoke passes.

# Required negative and adversarial cases

- invalid Goal digest
- unknown profile
- unknown Planner/Executor/GateRunner
- missing SQLite database on resume
- duplicate start idempotency key
- cancel terminal Goal
- inspect missing Artifact
- attempt to select a legacy path as default

# Verification method

- python scripts/check.py
- python scripts/lint_awkp.py
- git diff --check
- CLI parser and service tests
- generic deterministic Goal smoke
- new-process resume smoke
- package install/entrypoint smoke
- SG-8 operation review

# Required metrics

- CLI command success/failure by group
- operation service coverage
- fixture-specific imports in generic path
- time from goal start to first Node
- structured error classification

# Stop conditions

- Stop if CLI handlers must contain planning, scheduling or verification logic.
- Stop if the generic path still depends on fixture node IDs or hard-coded Evidence.
- Stop if resume requires reconstructing state from a report instead of SQLite.

# Required evidence and handoff

- Publish an implementation/change report with exact files, contracts, schema
  versions, migrations, known limitations and unresolved items.
- Preserve deterministic command outputs or structured summaries with content
  digests.
- Map every acceptance criterion to one or more Evidence IDs.
- Record producer Agent Release, Context Manifest, workspace/branch, base
  commit, final commit or rejected patch.
- Publish the required metrics for this Task.
- Create an immutable Handoff with one exact next action when blocked, failed,
  paused or returned for changes.
- The producer must not mark this Task completed; an independent verifier and
  EvidenceGate decide completion.

# Rollback and compatibility

- Do not silently overwrite released contracts or historical events.
- Use a new schema version when field meaning changes or compatibility breaks.
- Keep legacy adapters explicit and outside the default path.
- A rollback must preserve Artifact/Evidence references and explain state
  projection changes.

# Risk and approvals

Risk level: **R2**. This creates the default operation surface. Review must verify that CLI remains a narrow adapter and that no provider is privileged in core.
