---
type: WorkItem
id: TASK-0063
schema_version: awkp/0.1
title: Alignment workflow engine for multi-turn IntentDraft to RequestDraft
description: Build the Agent-assisted alignment workflow that turns an IntentDraft into an untrusted RequestDraft over multi-turn dialogue, drafting ClaimGraph and acceptance while resolving profiles and digests from the registry without fabrication.
context_id: CTX-phase1-intent-closure
priority: P0
risk_level: R3
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-30T10:00:00Z
depends_on: [TASK-0062]
input_refs:
  - ../../../src/ahra/intent_draft.py
  - ../../../src/ahra/goal_operations.py
  - ../../../src/ahra/acceptance_contracts.py
  - ../../../docs/roadmaps/phase1-minimal-loop-intent-roadmap.md
output_contract:
  - kind: alignment_workflow_engine_report
  - kind: verification_summary
  - kind: handoff
---

# Goal

Build the core alignment engine: a multi-turn workflow that takes an IntentDraft
and, through Agent-human dialogue, progressively drafts the ClaimGraph,
acceptance criteria, capability grants, and PlanDraft. It resolves profile and
digest references from the registry and never fabricates a digest. It emits an
untrusted `RequestDraft`, never a frozen GoalExecutionRequest.

# Scope

- Implement `AlignmentWorkflowEngine` in `src/ahra/alignment_engine.py`.
- Multi-turn dialogue support (state machine: refining scope, drafting claims,
  drafting plan).
- Resolve profiles and digests from the existing registry (no fabrication).
- Emit `RequestDraft` (a new domain object wrapping the drafted content).
- Keep the engine domain-only (no direct model/cloud imports).

# Non-goals

- Do not implement RequestDraft admission here (that is TASK-0064).
- Do not implement the human authorization gate here (that is TASK-0065).
- Do not freeze the RequestDraft into a GoalExecutionRequest here.
- Do not self-complete this task; EvidenceGate decides completion.

# Acceptance criteria

- [ ] `AlignmentWorkflowEngine` exists and implements a multi-turn dialogue flow
  from IntentDraft to RequestDraft, covered by tests.
- [ ] The engine resolves profile/digest references from the registry; a test
  asserts it never fabricates a digest (rejects an unknown reference).
- [ ] The engine emits a `RequestDraft` (untrusted), never a frozen
  GoalExecutionRequest, covered by a test.
- [ ] The domain module imports no adapter/model/cloud dependency (lint passes).
- [ ] Unit tests, lint, and diff checks pass: `.\.venv\Scripts\python.exe -B -m
  unittest tests.test_alignment_engine -v` and `.\.venv\Scripts\python.exe -B
  scripts\check.py --lint` green.
- [ ] Producer moves TASK-0063 only to review; EvidenceGate decides completion.

# Verification method

- .\.venv\Scripts\python.exe -B -m unittest tests.test_alignment_engine -v
- .\.venv\Scripts\python.exe -B scripts\check.py --lint
- git diff --check

# Required evidence and handoff

- Publish `evidence/alignment-workflow-engine-report.md` describing the dialogue
  flow, the RequestDraft structure, and the digest-resolution test.
- Publish `evidence/verification-summary.json`.
- Publish `handoffs/HANDOFF-0001.md` with one exact next action for TASK-0064.
