---
type: WorkItem
id: TASK-0053
schema_version: awkp/0.1
title: Implement CommandGateRunner kernel verification engine
description: Add a GateRunnerPort implementation that runs a gate's command through the RuntimeProvider under process.exec capability and maps the real result to gate status, keeping DeterministicGateRunner as the fixture baseline.
context_id: CTX-verification-teeth
priority: P0
risk_level: R2
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-29T10:00:00Z
depends_on: [TASK-0052]
input_refs:
  - ../../../src/ahra/verification.py
  - ../../../src/ahra/ports.py
  - ../../../src/ahra/capabilities.py
  - ../../../src/ahra/reference_runner/runtime.py
  - ../../../src/ahra/goal_operations.py
output_contract:
  - kind: command_gate_runner_report
  - kind: verification_summary
  - kind: handoff
---

# Goal

Install the verification engine. Today `DeterministicGateRunner.run()` always
returns PASSED, so a gate proves nothing. Add a `CommandGateRunner` that
actually executes the gate's command via the `RuntimeProvider` and maps the
real outcome to a `GateExecutionResult` status, while preserving the
deterministic runner as a fixture/CI baseline.

# Scope

- Add a `CommandGateRunner` implementing `GateRunnerPort`
  (`gate_kind` / `release_ref` / async `run`) next to the existing runners.
- Execute the gate command only through `RuntimeProvider.exec` (no direct
  `subprocess` in domain code) under a `process.exec` capability grant
  (default-deny; resources must be granted).
- Map results: exit 0 -> PASSED; nonzero -> FAILED with a `failure_class`;
  timeout -> TIMED_OUT; missing executable -> ERROR or BLOCKED. Judge against
  the GateDefinition `expectation` added in TASK-0052.
- Capture command output as an artifact and populate `raw_output_ref`.
- Keep the existing post-run workspace-mutation detection effective for command
  gates run with `mutation_allowed=False`.

# Non-goals

- Do not change completion derivation here (that is TASK-0054).
- Do not change the AWKP EvidenceGate here (that is TASK-0055).
- Do not remove or alter `DeterministicGateRunner` behavior.
- Do not weaken capability admission, timeout, or mutation boundaries.
- Do not self-complete this task; EvidenceGate decides completion.

# Acceptance criteria

- [ ] `CommandGateRunner` satisfies `GateRunnerPort` (`gate_kind`,
  `release_ref`, async `run`) and is registrable in `GateRunnerRegistry`.
- [ ] Exit 0 maps to PASSED; nonzero maps to FAILED with a populated
  `failure_class`; timeout maps to TIMED_OUT; missing executable maps to ERROR
  or BLOCKED. Each of the four cases has a dedicated unit test.
- [ ] The command is executed only via `RuntimeProvider.exec`; there is no
  direct `subprocess` call in the runner, and execution is gated by a
  `process.exec` capability grant that is default-deny without an explicit
  resource grant.
- [ ] Command output is written as an artifact and `raw_output_ref` is set on
  the `GateExecutionResult`.
- [ ] A command gate that mutates the workspace with `mutation_allowed=False`
  triggers the existing `unexpected_workspace_mutation` failure path.
- [ ] `DeterministicGateRunner` behavior is unchanged and its existing tests
  still pass.
- [ ] `src/ahra/verification.py` imports no adapter/model/cloud dependency.
- [ ] Targeted tests, lint, and diff checks pass, or any failure is recorded as
  a blocker with exact command output.
- [ ] Producer moves TASK-0053 only to review; EvidenceGate decides completion.

# Verification method

- .\.venv\Scripts\python.exe -B -m unittest tests.test_verification -v
- .\.venv\Scripts\python.exe -B scripts\check.py --test
- .\.venv\Scripts\python.exe -B scripts\check.py --lint
- git diff --check

# Required evidence and handoff

- Publish `evidence/command-gate-runner-report.md` describing the runner, the
  four status mappings, and the capability/mutation boundary behavior.
- Publish `evidence/verification-summary.json`.
- Publish `handoffs/HANDOFF-0001.md` with one exact next action for TASK-0054.
