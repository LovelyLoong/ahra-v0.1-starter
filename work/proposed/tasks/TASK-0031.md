---
type: WorkItem
id: TASK-0031
schema_version: awkp/0.1
title: Demonstrate the end-to-end dynamic defect-repair loop on a fixture project
description: Prove Goal-to-Claims-to-Plan-to-Execution-to-Defect-to-selective-reverification without AHRA modifying itself.
context_id: CTX-ahra-dynamic-kernel
priority: P0
risk_level: R2
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-25T00:00:00Z
depends_on: [TASK-0030]
input_refs:
  - all prior dynamic-kernel services
  - tests/fixtures/dynamic-goal-project
output_contract:
  - kind: end_to_end_fixture
  - kind: goal_run_artifacts
  - kind: defect_and_repair_records
  - kind: selective_verification_report
  - kind: security_report
  - kind: performance_report
---

# Goal

Validate the complete first-stage product behavior and quantify that selective verification avoids unnecessary full reruns.

# Scope

- Create an isolated fixture project and Goal Contract with functional, structural, security, operational and governance Claims.
- Generate/validate ClaimGraph and PlanDraft, compile/admit PlanIR, execute 2–4 nodes, and run L0/L1/L2 Gates.
- Inject or expose one deterministic failure at L1/L2.
- Create DefectRecord and a bounded Repair Plan that changes only the affected component.
- Invalidate only dependent Evidence and run the selected Gate set plus required safety baseline.
- Complete Goal only after all Claims have current Evidence.
- Attempt at least one unauthorized write/tool request and prove it is denied/audited.
- Record Gate count, model/tool calls, tokens where available, durations and reused Evidence.

# Non-goals

- Do not run the system against the AHRA repository as a self-modifying target.
- Do not use production credentials or external irreversible effects.
- Do not hide failures by changing Claims.

# Acceptance criteria

- [ ] The user input is a Goal Contract, not a fixed task list.
- [ ] Acceptance Claims exist before execution PlanIR.
- [ ] The Planner output is never executed before compilation and admission.
- [ ] The initial failure creates a Defect with exact reproduction and repair boundary.
- [ ] The repair changes only allowed affected paths.
- [ ] The second verification executes fewer Gates than the full declared Gate set and documents every reused Evidence record.
- [ ] L2 Completion evaluates all Claims and rejects any stale Evidence.
- [ ] Unauthorized action is denied before side effect and appears in audit evidence.
- [ ] Crash/resume or cancellation is exercised at least once.
- [ ] An independent final Verifier approves the fixture based on artifacts, not the producer summary.

# Verification method

- python scripts/check.py
- dynamic fixture end-to-end command
- selective-vs-full gate assertion
- security denial assertion
- resume/cancel assertion
- EvidenceGate final report
- git diff --check

# Required evidence and handoff

- Publish an implementation/change report with exact files, contracts, migrations, known limitations, and unresolved items.
- Preserve deterministic command outputs or structured summaries with content digests.
- Map every acceptance criterion to one or more Evidence IDs.
- Record the producer Agent Release, Context Manifest, workspace/branch, base commit, and final commit or rejected patch.
- Create an immutable Handoff with one exact next action when blocked, failed, paused, or returned for changes.
- The producer must not mark this task completed; an independent verifier and EvidenceGate decide completion.

# Rollback and compatibility

- Do not silently overwrite released contracts or historical events.
- Use a new schema version when field meaning changes or compatibility is broken.
- Keep compatibility adapters until the task explicitly authorizes their removal.
- Any rollback must preserve Artifact/Evidence references and explain state projection changes.

# Risk and approvals

Risk level: **R2**. Passing this task completes SG-3 and authorizes legacy cleanup, not framework self-iteration.
