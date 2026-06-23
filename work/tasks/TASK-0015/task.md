---
type: WorkItem
id: TASK-0015
schema_version: awkp/0.1
title: Add workflow max-attempt failure policy
description: Stop repeated workflow failures deterministically and preserve enough failure evidence for user or verifier judgment.
context_id: CTX-ahra-workflow-max-attempts
priority: P0
risk_level: R1
requester: human:maintainer
reviewer: agent:verifier
created_at: 2026-06-24T00:17:00+08:00
depends_on: [TASK-0014]
input_refs:
  - ../../../docs/architecture/workflow-modules.md
  - ../../../docs/architecture/reference-runtime-adapters-and-mcp.md
  - ../../../skills/ahra-workflow-runner/SKILL.md
  - ../../../contracts/schemas/workflow-run-request.schema.json
  - ../../../src/ahra/reference_runner/invocation.py
  - ../../../src/ahra/reference_runner/standard_harness.py
  - ../../../src/ahra/ports.py
output_contract:
  - kind: retry_policy
  - kind: terminal_failure_evidence
  - kind: cli_failure_semantics
  - kind: verification_report
---

# Goal

Add a generic workflow failure policy so a run stops after a bounded number of
attempts, preserves failure evidence, and hands control back to the user or an
independent verifier.

# Scope

- Define the smallest generic `max_attempts` policy needed by workflow modules.
- Apply the policy to Agent execution and reviewer output retries without
  making it Codex-specific.
- Make exhausted attempts a terminal workflow failure, not a successful command
  result.
- Preserve a failure summary, attempt count, last error, relevant command
  results, reviewer or contract errors, and any available diff/worktree
  reference.
- For formal AWKP task runs, publish failure evidence and a handoff without
  marking the task completed.
- Document the policy and update the local Skill operation notes.

# Non-goals

- Do not implement durable distributed retries, queue scheduling, or dashboard
  UI.
- Do not hide failed runs by silently resetting task state.
- Do not let an Agent self-approve completion after exhausting attempts.
- Do not add provider-specific retry logic for one Agent SDK.

# Acceptance criteria

- [ ] `max_attempts` is configurable through a generic workflow/module request
      surface with a documented default.
- [ ] Invalid retry policy values fail closed before Agent execution starts.
- [ ] Runs stop after the configured attempt limit and return a terminal failed
      result through CLI/API surfaces.
- [ ] Exhausted formal AWKP task runs publish task-local failure evidence and a
      handoff for user or verifier judgment without moving the task to
      `completed`.
- [ ] Tests cover a retryable Agent failure, exhausted attempts, and a
      non-retryable preflight or contract failure.
- [ ] `python scripts\check.py`, `python scripts\lint_awkp.py`, and
      `git diff --check` pass.
- [ ] AWKP task state, events, artifact manifest, evidence manifest, and
      handoff exist.

# Verification method

- `python scripts\check.py`
- `python scripts\lint_awkp.py`
- `git diff --check`
- A failing workflow fixture that reaches the configured attempt limit.

# Risk and approvals

R1. This changes failure semantics but should not perform external side
effects. Any cleanup of failed execution resources remains out of scope.
