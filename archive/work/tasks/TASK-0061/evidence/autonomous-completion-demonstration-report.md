---
type: Evidence
id: EVD-TASK-0061-0001
schema_version: awkp/0.1
title: Autonomous end-to-end task completion demonstration
description: Shows one simple task moving ready to completed through create, claim, GoalExecution, Goal-AWKP bridge, orchestrator, and EvidenceGate without manual state edits.
status: current
owner: agent:codex-implementation
source_refs:
  - ../../../../tests/test_goal_operations.py
  - ../../../../src/ahra/cli.py
  - ../../../../src/ahra/goal_operations.py
  - ../../../../src/ahra/awkp_task_creator.py
  - ../../../../src/ahra/awkp_state_writer.py
  - ../../../../src/ahra/orchestrator.py
  - ../../../../src/ahra/evidence_gate.py
evidence_refs: []
confidence: high
last_verified_at: 2026-06-30T02:03:47Z
review_after: 2026-07-30T00:00:00Z
tags: [task-0061, autonomy, goal-awkp-bridge, evidencegate]
---

# Summary

TASK-0061 is implemented as a non-skipped automated test:
`tests.test_goal_operations.GoalOperationCliTests.test_autonomous_task_completion_starts_from_created_ready_task`.

The test drives one temporary AWKP task named `TASK-AUTO-E2E` from `ready` to
`completed` through the existing governed path:

1. `ahra task create` creates a lint-clean task skeleton in `ready`.
2. `ahra task claim` uses the governed CAS writer to acquire `working` with a
   fencing token.
3. `ahra goal start` runs the command-backed GoalExecution request with
   `inputs/command-gate.txt` set to `fixed`, causing `GATE-command-sentinel` to
   produce real command-backed EvidenceV2 and GateRun records.
4. The verifier report references that kernel EvidenceV2 record.
5. `ahra goal bridge-awkp-task` associates the succeeded GoalExecution with the
   AWKP task, materializes kernel EvidenceV2/GateRun records into the task
   manifests, requests review through the orchestrator, and invokes EvidenceGate
   under a distinct verifier identity.

# Demonstrated Sequence

The test asserts this exact append-only event sequence for the demonstrated
task:

| Step | Event | State change | Governed writer or authority |
|---|---|---|---|
| 1 | `task_created` | null -> ready | `AwkpTaskCreator` via `ahra task create` |
| 2 | `lease_acquired` | ready -> working | `AwkpTaskStateWriter.acquire_working`, `expected_version=0` |
| 3 | `goal_awkp_associated` | working -> working | `GoalAwkpBridge` plus `AwkpTaskStateWriter.record_goal_association`, `expected_version=1` |
| 4 | `review_requested` | working -> review | `AwkpTaskReviewOrchestrator` plus `AwkpTaskStateWriter.request_review`, `expected_version=2` |
| 5 | `evidence_gate_approved` | review -> completed | `EvidenceGate`, verifier actor `agent:autonomous-verifier` |

The asserted final temporary task state is `completed`, `state_version=4`, no
active lease, and includes the command-backed kernel evidence reference.

# Boundary Proof

- No test helper writes the demonstrated task's `state.json` or `events.jsonl`
  directly. Task state transitions are produced by CLI/service calls to the
  governed components.
- The only direct test writes are input artifacts outside task state authority:
  the copied GoalExecution request, the command sentinel input file, and the
  structured verifier report consumed by EvidenceGate.
- The producer identity is `agent:autonomous-producer`; the final verifier
  identity is `agent:autonomous-verifier`. The test asserts these identities
  differ.
- Completion is not performed by the bridge. The bridge delegates to the
  orchestrator and EvidenceGate; the final event is `evidence_gate_approved`.
- The EvidenceGate approval references real kernel EvidenceV2 with GateRun
  lineage produced by `GATE-command-sentinel`, not a hollow gate record.

# Acceptance Mapping

| Criterion | Implementation evidence |
|---|---|
| ready -> working -> review -> completed autonomously | The new test starts from `ahra task create` and asserts all five events through `evidence_gate_approved`. |
| Governed state transitions | The test asserts expected versions for claim, association, and review, and relies on the creator, CAS writer, bridge, orchestrator, and EvidenceGate. |
| Distinct verifier | The final EvidenceGate actor is asserted to differ from the producer actor. |
| Real gate evidence | The test runs the command-backed GoalExecution and asserts `kernel_evidence_v2` and `kernel_gate_run_v2` records are materialized. |
| Non-skipped automated test | The test is part of `tests.test_goal_operations` and ran in the targeted and full suites. |

# Verification

- `.\\.venv\\Scripts\\python.exe -B -m unittest tests.test_cli tests.test_goal_operations tests.test_evidence_gate -v` passed with 42 tests.
- `.\\.venv\\Scripts\\python.exe -B scripts\\check.py` passed with 238 tests, 1 environment skip, AWKP lint 0 errors, 0 warnings, and AHRA lint 0 failures.
- `.\\.venv\\Scripts\\python.exe -B scripts\\check.py --lint` passed after manifest updates.
- `git diff --check` passed, with Git reporting only CRLF/LF normalization warnings for TASK-0061 state/events.

One intermediate full-check rerun after manifest updates failed once in
`test_validate_plan_start_resume_inspect_and_terminal_cancel` with
`goalStatus=failed`. The failing test passed when rerun alone, the full
`tests.test_goal_operations` module passed, and the final full `scripts/check.py`
rerun passed without code changes.

The producer moved TASK-0061 itself only from `working` to `review` through
`AwkpTaskStateWriter.request_review` at state version 2. TASK-0061 is not marked
completed by the implementation side.
