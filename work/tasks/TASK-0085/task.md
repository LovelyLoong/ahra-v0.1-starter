---
type: WorkItem
id: TASK-0085
schema_version: awkp/0.1
title: "Bootstrap request-scoped write admission for the development-bounded profile"
description: "Derive the development-bounded effective filesystem write scope from each GoalExecutionRequest planDraft capability request, admit it against a hardened kernel write blacklist, and propagate deletions and renames from isolated worktrees, so every later self-hosting loop task is executable by Workflow B alone. This is the single bootstrap exception of the self-hosting loop: Workflow B is structurally forbidden from editing its own kernel boundary, so this task runs on the manual path and must be recorded as a loop defect per the Increment F rule in the development program overview."
context_id: "CTX-self-hosting-loop"
priority: "P1"
risk_level: "R2"
requester: "human:maintainer"
reviewer: "agent:independent-verifier"
created_at: 2026-07-02T04:06:11.198896Z
depends_on: []
input_refs: ["src/ahra/goal_operations.py", "src/ahra/reference_runner/git_ops.py", "src/ahra/capabilities.py", "docs/roadmaps/development-program-overview.md", "examples/goals/dogfood-a-alignment-session.yaml"]
output_contract:
  - kind: "ahra/artifact/code-change/0.1"
  - kind: "ahra/evidence/test-report/0.1"
---

# Goal

Derive the development-bounded effective filesystem write scope from each GoalExecutionRequest planDraft capability request, admit it against a hardened kernel write blacklist, and propagate deletions and renames from isolated worktrees, so every later self-hosting loop task is executable by Workflow B alone. This is the single bootstrap exception of the self-hosting loop: Workflow B is structurally forbidden from editing its own kernel boundary, so this task runs on the manual path and must be recorded as a loop defect per the Increment F rule in the development program overview.

# Acceptance criteria

- [ ] For profile/development-bounded, the effective filesystem.write allowlist used by capability admission and by IsolatedGitWorkspaceProvider is derived from the union of planDraft filesystem.write capability resources instead of the fixed profile allowlist, covered by a test.
- [ ] Any requested write resource matching the hardened kernel blacklist (existing kernel modules plus scripts/**, pyproject.toml, uv.lock, Makefile, .github/**) is rejected at capability admission before any side effect, covered by a hostile test.
- [ ] IsolatedGitWorkspaceProvider propagates file deletions and renames from the worktree back to the source repository only for paths inside the request-scoped allowlist and never for blacklisted paths, covered by a test.
- [ ] examples/goals/task-0086 through task-0089 GoalExecutionRequests pass ahra goal validate.
- [ ] uv run python -B scripts/check.py passes, and the manual-path bootstrap is recorded as a loop defect in this task evidence.
