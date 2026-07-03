---
type: WorkItem
id: TASK-0091
schema_version: awkp/0.1
title: "Garbage-collect run byproducts and define the task data lifecycle"
description: "Dynamic effective-data management: isolated execution worktrees and run byproducts must not accumulate in completed task directories. Add worktree GC to finalize_execution_workspace, a repository-hygiene test that enforces the retention rule, and a data-lifecycle policy defining four retention tiers (contract, authority, evidence, run byproducts) plus the completion-distillation rule. Executed by Workflow B alone through examples/goals/task-0091-run-byproduct-gc.yaml."
context_id: "CTX-self-hosting-loop"
priority: "P1"
risk_level: "R1"
requester: "human:maintainer"
reviewer: "agent:independent-verifier"
created_at: 2026-07-03T01:44:32.527669Z
depends_on: ["TASK-0085"]
input_refs: ["src/ahra/reference_runner/git_ops.py", "tests/test_git_ops.py", "docs/policies/index.md", "examples/goals/task-0091-run-byproduct-gc.yaml"]
output_contract:
  - kind: "ahra/artifact/code-change/0.1"
  - kind: "ahra/evidence/test-report/0.1"
---

# Goal

Dynamic effective-data management: isolated execution worktrees and run byproducts must not accumulate in completed task directories. Add worktree GC to finalize_execution_workspace, a repository-hygiene test that enforces the retention rule, and a data-lifecycle policy defining four retention tiers (contract, authority, evidence, run byproducts) plus the completion-distillation rule. Executed by Workflow B alone through examples/goals/task-0091-run-byproduct-gc.yaml.

# Acceptance criteria

- [ ] IsolatedGitWorkspaceProvider.finalize_execution_workspace removes the isolated worktree directory and prunes its git worktree registration after successful propagation, and retains the worktree when propagation fails, covered by tests in tests/test_git_ops.py.
- [ ] A repository-hygiene test in tests/ fails when any completed task directory under work/tasks contains development-worktrees residue, and passes against the current tree.
- [ ] docs/policies/data-lifecycle.md defines the four task-data retention tiers (contract, authority, evidence, run byproducts) with their lifecycles and the completion-distillation rule (facts land in docs/, process lands in archive/), and is linked from docs/policies/index.md.
- [ ] The change is produced by a Workflow B development-bounded GoalExecution with kernel-derived completion, then approved through the AWKP EvidenceGate by an independent verifier.
