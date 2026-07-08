---
type: Runbook
id: RUNBOOK-task-0015-workflow-failure-hardening-plan
schema_version: awkp/0.1
title: TASK-0015 workflow failure hardening plan
description: Implementation plan for the first three TASK-0015 workflow failure modes observed during scheduled runs.
status: draft
owner: team:platform
source_refs:
  - ../../work/tasks/TASK-0015/task.md
  - ../../.runtime/TASK-0015-supervision-summary-20260624T1735.md
  - ../architecture/agent-drivers-and-workflow-invocation.md
  - ../architecture/reference-runtime-adapters-and-mcp.md
evidence_refs: []
confidence: reviewed
last_verified_at: 2026-06-24T00:00:00Z
review_after: 2026-07-24T00:00:00Z
tags: [runbook, workflow, task-0015, failure-policy]
---

# Summary

This document records the proposed fixes for the first three TASK-0015 workflow
failure modes observed during scheduled workflow supervision. It does not claim
TASK-0015 is complete, and it does not change the EvidenceGate completion
boundary.

The fourth observed issue, long reviewer phases and richer heartbeat or
stop-and-harvest support, is intentionally out of scope for this plan.

The earlier local workflow-runner Skill referenced by this draft has been
retired during the project-local Skill replacement transition. This runbook is
trace material unless a replacement Skill is produced, reviewed, and registered.

# Goals

1. Execute only explicit verification commands, never natural-language
   acceptance notes.
2. Define one contract for how executor-published task-local evidence interacts
   with harness finalization.
3. Always write a durable workflow result after accepted work reaches
   finalization, even when source integration fails.

# Non-Goals

- Do not implement durable distributed retries, queue scheduling, dashboard UI,
  richer reviewer heartbeat, or stop-and-harvest.
- Do not mark TASK-0015 `completed` from producer evidence or workflow output.
- Do not turn the workstation-specific `uv run python -B` workaround into a
  framework-wide command requirement.
- Do not add provider-specific retry behavior for one Agent SDK.

# Problem 1: Verification Command Parsing

## Observed Failure

The first scheduled run treated a natural-language verification item as a shell
command and failed deterministic verification. The same run also executed bare
`python scripts\check.py`, which did not use the expected project environment
on the maintainer workstation.

## Required Behavior

Verification parsing must be conservative:

- Only backtick-wrapped commands are executable, for example
  `` `python scripts\check.py` ``.
- Only shell-prompt lines are executable, for example
  `$ python scripts\check.py`.
- Natural-language verification notes are retained as task text but skipped by
  deterministic command execution.

Local command adaptation must be explicit:

- Keep the declared command from `task.md`.
- Record the actual executed argv in deterministic evidence.
- On this workstation, map known bare Python verification commands to the local
  trusted path when needed:
  - `python scripts\check.py` -> `uv run python -B scripts/check.py`
  - `python scripts\lint_awkp.py` -> `uv run python -B scripts/lint_awkp.py`
- Label that mapping as local-only in evidence and docs.

## Acceptance Checks

- A natural-language verification item does not create a `CheckSpec`.
- Backtick-wrapped and `$ ...` commands still create `CheckSpec` records.
- Deterministic evidence distinguishes the declared command from executed argv.
- The local Python adaptation does not alter the framework-neutral task
  contract.

# Problem 2: AWKP State Ownership During Finalization

## Observed Failure

The second scheduled run reached an accepted isolated-workspace state. The
executor had already published task-local implementation evidence and moved the
isolated task state to `review`, but harness finalization still expected a
publishable `working` state. Source integration did not complete.

## Required Behavior

Use one explicit state publication contract:

- The executor may publish task-local implementation evidence, a handoff, and a
  `review` state inside the isolated workspace.
- The harness finalizer remains the only component that integrates the
  workflow result back into the source workspace.
- The harness finalizer may publish workflow review or failure records when the
  isolated task state is:
  - `working`; or
  - `review` with no active lease.
- The harness finalizer must reject:
  - `review` with an active lease;
  - `completed`;
  - `ready`;
  - unrelated or unknown states.

## Acceptance Checks

- An accepted formal AWKP run still publishes workflow evidence when the
  executor prepublished review-state task-local evidence.
- A prepublished `review` state with an active lease fails closed.
- The final source task state is `review`, not `completed`.
- Events preserve both producer evidence publication and finalizer publication.

# Problem 3: Durable Result For Post-Acceptance Failures

## Observed Failure

The second scheduled run emitted `task_accepted` and committed the isolated
workspace, but it did not write `workflow-run-result.json` and did not emit a
source integration event. The run therefore became ambiguous for supervision:
accepted internally, not integrated externally, and missing a durable terminal
result.

## Required Behavior

Finalization must always write a terminal or recoverable result record:

- The workflow handler may return `accepted`, `rejected`, `error`, or
  `blocked`.
- After handler return, finalization enters an explicit finalization phase.
- Any finalization exception must still write `workflow-run-result.json`.
- If accepted work cannot be integrated into the source workspace, the final
  workflow result must not remain `accepted`. It should become:
  - `status: error`
  - `phase: finalization`
  - `accepted_commit: <isolated-workspace commit>`
  - `source_integrated: false`
  - `integration_error: <structured error summary>`
  - `recoverable: true`
  - `next_action: <single recovery action>`

CLI behavior must stay fail-closed:

- `workflow start` and `workflow resume` return non-zero for `error`,
  `rejected`, or `blocked`.
- The structured CLI output includes the artifact directory and result summary
  so a user or verifier can locate the durable evidence immediately.

## Acceptance Checks

- A simulated source-integration failure after an accepted isolated commit
  writes `workflow-run-result.json`.
- The result records the accepted isolated commit and the integration error.
- The CLI returns non-zero while preserving artifact/result location data.
- No source task state is promoted to `completed`.

# Recommended Implementation Order

1. Implement conservative verification command parsing and local-only command
   adaptation.
2. Implement the `working` or `review` without lease finalizer contract.
3. Implement finalization error capture and durable result writing.
4. Add focused regression tests for each behavior before rerunning TASK-0015.

# Verification Commands

Use the maintainer workstation path for local verification:

```bash
uv run python -B scripts/check.py
uv run python -B scripts/lint_awkp.py
git diff --check
```

Framework-neutral commands remain documented elsewhere and must not be replaced
by the workstation-specific workaround in product-facing contracts.

# Completion Boundary

Even if all fixes in this plan pass, TASK-0015 should only move to `review`
with artifacts, evidence, and handoff. Completion remains an independent
EvidenceGate decision.
