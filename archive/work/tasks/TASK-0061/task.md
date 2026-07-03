---
type: WorkItem
id: TASK-0061
schema_version: awkp/0.1
title: Demonstrate autonomous end-to-end task completion
description: Using the CAS writer, create/claim commands, orchestrator, and Goal-AWKP bridge, drive one simple real task from ready to completed autonomously with producer not equal to verifier, with no human opening multiple Agents mid-flow.
context_id: CTX-workflow-autonomy
priority: P0
risk_level: R2
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-29T11:00:00Z
depends_on: [TASK-0060]
input_refs:
  - ../../../src/ahra/cli.py
  - ../../../src/ahra/goal_operations.py
  - ../../../src/ahra/evidence_gate.py
  - ../../../scripts/run_real_agent_pilot.py
output_contract:
  - kind: autonomous_completion_demonstration_report
  - kind: verification_summary
  - kind: handoff
---

# Goal

Prove the stall is gone. With the governed CAS writer (TASK-0057), create/claim
commands (TASK-0058), producer-to-verifier orchestrator (TASK-0059), and the
Goal-AWKP bridge (TASK-0060) in place, drive one simple real task from ready to
completed autonomously - through working, review, and an EvidenceGate decision
under a distinct verifier identity - without a human opening multiple Agents
between steps.

# Scope

- Pick one simple, objectively verifiable real task (for example a small,
  self-contained framework chore) and run it end-to-end through the new
  autonomous path.
- Demonstrate the full sequence: create -> claim -> execute -> publish evidence
  -> request review -> EvidenceGate decision under a distinct verifier identity
  -> completed, with the kernel GateRun evidence feeding the AWKP gate.
- Capture the run so it is reproducible and encoded as a non-skipped test.
- Confirm no manual hand-edit of state.json/events.jsonl occurred during the
  run; all transitions went through governed writers.

# Non-goals

- Do not weaken any capability / gate / verification / EvidenceGate boundary to
  make the run succeed.
- Do not require the task to involve network access or subjective judgment
  (those are governed gates deferred to Phase 1).
- Do not collapse producer != verifier.
- Do not self-complete this task; EvidenceGate decides completion.

# Acceptance criteria

- [ ] One simple real task is driven ready -> working -> review -> completed
  autonomously, with no manual CLI invocation or file hand-edit between steps,
  captured as evidence.
- [ ] Every state transition in the run was performed by a governed writer
  (TASK-0057) and the orchestrator (TASK-0059), verifiable from the task's
  append-only events (no hand-authored state).
- [ ] The EvidenceGate decision was made under a verifier identity distinct from
  every producer identity in the run.
- [ ] The completion rested on real gate evidence (TASK-0053..0056 / TASK-0060
  bridge), not a hollow gate.
- [ ] The end-to-end path is encoded as a non-skipped automated test.
- [ ] `.\.venv\Scripts\python.exe -B scripts\check.py` (full lint + test) passes.
- [ ] Producer moves TASK-0061 only to review; EvidenceGate decides completion.

# Verification method

- .\.venv\Scripts\python.exe -B -m unittest tests.test_cli tests.test_goal_operations tests.test_evidence_gate -v
- .\.venv\Scripts\python.exe -B scripts\check.py
- git diff --check

# Required evidence and handoff

- Publish `evidence/autonomous-completion-demonstration-report.md` showing the
  full ready-to-completed sequence, proof that every transition was governed,
  and the distinct-verifier decision.
- Publish `evidence/verification-summary.json`.
- Publish `handoffs/HANDOFF-0001.md` with one exact next action (toward Phase 1).
