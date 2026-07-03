---
type: WorkItem
id: TASK-0077
schema_version: awkp/0.1
title: "Workflow A dogfood first real alignment session checkpoint"
description: "Register the successful Workflow B development-bounded dogfood run that produced the first AgentDriver-backed Workflow A AlignmentSessionManager slice, plus immediate workflow hardening for future dogfood validation."
context_id: "CTX-workflow-a-agent-driven-alignment"
priority: "P1"
risk_level: "R2"
requester: "human:maintainer"
reviewer: "agent:independent-verifier"
created_at: 2026-07-01T10:27:41.448109Z
depends_on: ["TASK-0076"]
input_refs: ["examples/goals/dogfood-a-alignment-session.yaml", "examples/goals/.ahra/artifacts/dogfood-a-003/goal-start-report.json", "src/ahra/alignment_session.py", "tests/test_alignment_session.py"]
output_contract:
  - kind: "goal_awkp_bridge_evidence"
  - kind: "alignment_session_checkpoint"
  - kind: "workflow_hardening"
---

# Goal

Register the successful Workflow B development-bounded dogfood run that produced the first AgentDriver-backed Workflow A AlignmentSessionManager slice, plus immediate workflow hardening for future dogfood validation.

# Acceptance criteria

- [ ] GoalExecution GEXEC-b4a41e0e3a22e6fb is associated with this task through GoalAwkpBridge and manifest-backed kernel EvidenceV2/GateRun records.
- [ ] src/ahra/alignment_session.py and tests/test_alignment_session.py are present, importable, and verified by tests.test_alignment_session.
- [ ] The generated AlignmentSessionManager emits an untrusted RequestDraft that passes RequestDraftAdmission in deterministic tests.
- [ ] examples/goals/dogfood-a-alignment-session.yaml is advanced to a fresh dogfood-a-004 idempotency/artifact/store target and requires process.exec validation for future runs.
- [ ] uv run python -B scripts/check.py passes after the checkpoint and workflow hardening changes.
