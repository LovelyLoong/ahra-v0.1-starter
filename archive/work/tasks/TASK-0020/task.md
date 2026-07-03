---
type: WorkItem
id: TASK-0020
schema_version: awkp/0.1
title: Define workflow retention and cleanup policy
description: Separate audit evidence from diagnostic artifacts and ephemeral execution resources, then add a safe cleanup path.
context_id: CTX-ahra-workflow-retention-cleanup
priority: P2
risk_level: R1
requester: human:maintainer
reviewer: agent:verifier
created_at: 2026-06-24T00:17:00+08:00
depends_on: [TASK-0019]
input_refs:
  - ../../../docs/architecture/workflow-modules.md
  - ../../../docs/architecture/observability-and-evaluation.md
  - ../../../src/ahra/reference_runner/invocation.py
  - ../../../src/ahra/reference_runner/git_ops.py
output_contract:
  - kind: retention_policy
  - kind: cleanup_command_or_defer_decision
  - kind: documentation_update
  - kind: verification_report
---

# Goal

Create a conservative retention policy so AHRA keeps audit evidence, preserves
useful failure diagnostics, and can safely clean ephemeral workflow resources.

# Scope

- Classify workflow outputs as audit evidence, diagnostic artifacts, or
  ephemeral execution resources.
- Define default retention expectations for successful and failed runs.
- Add a dry-run-first cleanup path only if it can avoid deleting referenced
  evidence and user work.
- Document which files, branches, worktrees, and artifacts are never removed
  automatically.
- Keep cleanup separate from EvidenceGate completion.

# Non-goals

- Do not delete artifacts automatically without a dry-run-first policy.
- Do not remove files referenced by task artifact or evidence manifests.
- Do not hide failed run evidence before the user or verifier can inspect it.
- Do not implement remote object storage lifecycle management.

# Acceptance criteria

- [ ] Retention policy distinguishes audit evidence, diagnostic artifacts, and
      ephemeral execution resources.
- [ ] Default retention periods or keep policies are documented for accepted
      and failed runs.
- [ ] Cleanup is dry-run-first and refuses to remove referenced evidence.
- [ ] Tests cover cleanup candidate selection and evidence-protection refusal
      if cleanup is implemented.
- [ ] Docs explain how users can inspect what will be removed before removal.
- [ ] `python scripts\check.py`, `python scripts\lint_awkp.py`, and
      `git diff --check` pass.
- [ ] AWKP task state, events, artifact manifest, evidence manifest, and
      handoff exist.

# Verification method

- `python scripts\check.py`
- `python scripts\lint_awkp.py`
- `git diff --check`
- Cleanup dry-run fixture if an implementation boundary is selected.

# Risk and approvals

R1. Cleanup must fail closed. The first implementation should prefer listing
candidates over deleting resources.
