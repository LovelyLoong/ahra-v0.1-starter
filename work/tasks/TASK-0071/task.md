---
type: WorkItem
id: TASK-0071
schema_version: awkp/0.1
title: Development executor profile with path-guarded real Agent capability
description: Build a new GoalOperationProfile that uses real AgentDriver for bounded development tasks (multi-file edit, process.exec for tests) with relaxed budget, but guards B's trusted kernel files via filesystem.write path whitelist/blacklist to enforce "B modifying A is safe cross-modification, not self-modification."
context_id: CTX-workflow-b-development-capability
priority: P0
risk_level: R3
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-30T12:00:00Z
depends_on: [TASK-0070]
input_refs:
  - ../../../src/ahra/goal_operations.py
  - ../../../src/ahra/capabilities.py
  - ../../../src/ahra/cli.py
  - ../../../architecture/decisions/ADR-0009-agent-driven-intent-alignment-front-workflow.md
  - ../../../docs/architecture/intent-alignment-workflow.md
  - ../../../AHRA_dynamic_kernel_master_plan_2026-06-25.md
output_contract:
  - kind: development_executor_profile_report
  - kind: verification_summary
  - kind: handoff
---

# Goal

Workflow B (the execution kernel, TASK-0052..0070) can govern and verify tasks
autonomously, but currently cannot execute *real development work* — its default
executor writes fixed templates, and the real Agent executor (bounded profile)
is locked to single-file output (`outputs/summary.txt`) with near-zero budget.

This task builds a **development executor profile** that lets Workflow B execute
genuine framework development tasks (write `alignment_*.py`, update schemas, run
tests) using real AgentDriver, while physically enforcing the safety rule: **B
modifying A is safe cross-modification (tool building product), not
self-modification (system loosening its own gate).**

The maintainer's vision: use Workflow B to iterate Workflow A. This task is the
missing capability layer that makes that dogfooding possible.

# Scope

- Add a new `GoalOperationProfile`: `profile/development-bounded` that:
  - Uses `REAL_BOUNDED_EXECUTOR_REF` (real AgentDriver, not deterministic stub).
  - Relaxes budget: `maxModelCalls: 10, maxToolCalls: 50, maxWallSeconds: 300,
    maxCostUsd: 1.0` (enough for multi-file + test runs).
  - Grants `filesystem.write` to **A-workflow paths** (whitelist):
    `alignment_*.py`, `intent_*.py`, `request_*.py`, `contracts/schemas/`,
    `tests/test_alignment_*.py`, `docs/architecture/intent-*`, etc.
  - **BLACKLISTS B's trusted kernel** (enforcement of "B cannot modify B"):
    `evidence_gate.py`, `capabilities.py`, `verification.py`,
    `goal_operations.py`, `sqlite_control_store.py`, `ports.py`,
    `awkp_state_writer.py`.
  - Grants `process.exec` for `scripts/check.py`, `scripts/lint_*.py` (verification).
- Update `GoalOperationService` construction in `cli.py` to allow injecting the
  real driver (currently only `run_real_agent_pilot.py` does this).
- Add `--allow-development-agent` flag to `ahra goal start` that injects
  CodexSDKDriver and uses the development profile.
- The path blacklist is **enforced by the capability gateway** (`capabilities.py`)
  — attempts to write blacklisted files are rejected with audit trail, not silently
  allowed.

# Non-goals

- Do not remove the M1 bounded profile; it stays as a stricter sandbox.
- Do not allow the development profile to modify `architecture/decisions/` or
  `docs/policies/` (governance docs remain human-authored).
- Do not let this profile run on "B modifies B" tasks — that remains
  human-authored and manually reviewed.
- Do not self-complete this task; EvidenceGate decides completion.

# Acceptance criteria

- [ ] A new profile `profile/development-bounded` exists in
  `GoalOperationProfileRegistry` with real AgentDriver + relaxed budget + path
  whitelist (A-workflow files) + path blacklist (B kernel files), registered and
  retrievable.
- [ ] The filesystem.write capability gateway enforces the path blacklist: an
  attempt to write `evidence_gate.py` (a blacklisted B-kernel file) is rejected
  with audit trail, covered by a test.
- [ ] The profile grants process.exec for `scripts/check.py` and successfully
  runs it from a development node, covered by a test.
- [ ] `ahra goal start` accepts `--allow-development-agent`, injects
  CodexSDKDriver, and uses the development profile, covered by a CLI invocation
  test or fixture.
- [ ] A sample GoalExecutionRequest using this profile can write
  `alignment_stub.py` (whitelisted) but is rejected when attempting
  `evidence_gate.py` (blacklisted), end-to-end verified by fixture.
- [ ] The domain module imports no adapter/model/cloud dependency in the profile
  definition (lint passes).
- [ ] Unit tests, lint, and diff checks pass: `.\.venv\Scripts\python.exe -B -m
  unittest tests.test_goal_operations -v` and `.\.venv\Scripts\python.exe -B
  scripts\check.py --lint` green.
- [ ] Producer moves TASK-0071 only to review; EvidenceGate decides completion.

# Verification method

- .\.venv\Scripts\python.exe -B -m unittest tests.test_goal_operations -v
- .\.venv\Scripts\python.exe -B -m unittest tests.test_capabilities -v
- .\.venv\Scripts\python.exe -B scripts\check.py --lint
- git diff --check
- Fixture test: run a sample Goal with development profile that writes an
  A-workflow file and runs check.py; assert success. Run another that attempts
  to write evidence_gate.py; assert rejection with audit.

# Required evidence and handoff

- Publish `evidence/development-executor-profile-report.md` describing the
  profile budget, the A-workflow path whitelist, the B-kernel path blacklist,
  the capability gateway enforcement test, and the CLI injection mechanism.
- Publish `evidence/verification-summary.json`.
- Publish `handoffs/HANDOFF-0001.md` stating: TASK-0071 complete, Workflow B can
  now execute real development tasks within the guarded A-modification boundary,
  ready for dogfooding "use B to iterate A."
