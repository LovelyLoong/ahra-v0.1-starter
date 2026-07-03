---
type: WorkItem
id: TASK-0019
schema_version: awkp/0.1
title: Strengthen workflow lease and CAS boundary
description: Define and implement the next durable lease, fencing, and expected-version boundary only after the local workflow loop is stable.
context_id: CTX-ahra-workflow-lease-cas-boundary
priority: P2
risk_level: R2
requester: human:maintainer
reviewer: agent:verifier
created_at: 2026-06-24T00:17:00+08:00
depends_on: [TASK-0018]
input_refs:
  - ../../../architecture/SPEC.md
  - ../../../SPEC.md
  - ../../../WORKFLOW.md
  - ../../../docs/architecture/framework-completion-roadmap.md
  - ../../../src/ahra/reference_runner/awkp_task.py
  - ../../../src/ahra/reference_runner/git_ops.py
output_contract:
  - kind: concurrency_boundary
  - kind: lease_fencing_contract
  - kind: implementation_or_defer_decision
  - kind: verification_report
---

# Goal

Convert the known local-only workflow concurrency limitation into a precise
lease, fencing, and expected-version boundary without blocking the first local
workflow self-iteration loop.

# Scope

- Identify the exact race windows left by preflight, isolated worktree
  execution, and source workspace fast-forward.
- Decide the first unique durable boundary for source task state update
  protection, or explicitly defer implementation with the missing trigger named.
- If implementation is selected, add the smallest expected-version or fencing
  check needed for formal AWKP task projection.
- Keep state authority and audit-chain rules aligned with `SPEC.md` and
  `WORKFLOW.md`.

# Non-goals

- Do not implement a general database, dashboard, distributed queue, or
  reconciler unless this task selects one concrete and unique boundary.
- Do not weaken append-only event history.
- Do not bypass EvidenceGate.
- Do not rewrite unrelated task state files.

# Acceptance criteria

- [ ] The remaining workflow race windows are documented with concrete source
      and target state examples.
- [ ] The first CAS/lease/fencing boundary is either implemented or explicitly
      deferred with the missing operational trigger named.
- [ ] Formal AWKP task projection cannot silently overwrite a newer source task
      state.
- [ ] Tests cover stale source state or conflicting projection when implemented;
      if deferred, the test gap is named in evidence.
- [ ] `python scripts\check.py`, `python scripts\lint_awkp.py`, and
      `git diff --check` pass.
- [ ] AWKP task state, events, artifact manifest, evidence manifest, and
      handoff exist.

# Verification method

- `python scripts\check.py`
- `python scripts\lint_awkp.py`
- `git diff --check`
- Conflict or stale-state fixture if an implementation boundary is selected.

# Risk and approvals

R2. This touches state authority boundaries. Keep the change narrow and require
independent verifier review before completion.
