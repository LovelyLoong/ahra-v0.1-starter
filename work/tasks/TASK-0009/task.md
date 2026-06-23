---
type: WorkItem
id: TASK-0009
schema_version: awkp/0.1
title: Align default local runtime sandbox profile
description: Choose or explicitly defer the default local runtime sandbox profile before implementing any sandbox provider.
context_id: CTX-ahra-runtime-sandbox-alignment
priority: P1
risk_level: R1
requester: human:maintainer
reviewer: agent:verifier
created_at: 2026-06-23T10:32:07+08:00
depends_on: [TASK-0008]
input_refs:
  - ../../../docs/architecture/framework-completion-roadmap.md
  - ../../../docs/architecture/framework-entrypoints.md
  - ../../../docs/architecture/reference-runtime-adapters-and-mcp.md
  - ../../../architecture/SPEC.md
  - ../../../examples/runtimes/local-worktree.yaml
  - ../../../src/ahra/ports.py
output_contract:
  - kind: architecture_decision
  - kind: runtime_profile_update
  - kind: verification_report
---

# Goal

Resolve the roadmap item that is still pending alignment: the default local
runtime sandbox profile.

# Scope

- Compare the current Git worktree isolation boundary with practical local
  sandbox options such as OCI container, devcontainer, remote sandbox, or
  explicit defer.
- Choose one default local sandbox profile or record a concrete defer decision
  with the missing input named.
- Update the relevant architecture doc, ADR, or runtime example so the selected
  boundary is discoverable by future agents.
- Define the next implementation task only if a concrete default profile is
  selected.
- Keep the decision focused on process, filesystem, network, and secret
  isolation boundaries.

# Non-goals

- Do not implement a sandbox provider in this task.
- Do not introduce vendor SDKs into domain code.
- Do not change EvidenceGate behavior.
- Do not implement durable control plane, scaffold, CI, or ApprovalService.

# Acceptance criteria

- [x] A single default local sandbox direction is selected, or defer is recorded
      with the exact missing decision input.
- [x] The selected or deferred boundary distinguishes source worktree isolation
      from process, network, and secret isolation.
- [x] Architecture docs or ADRs are updated with compatibility notes.
- [x] Runtime profile examples remain valid and do not imply stronger isolation
      than they provide.
- [x] `python scripts\check.py`, `python scripts\lint_awkp.py`, and
      `git diff --check` pass.
- [x] AWKP task state, events, artifact manifest, evidence manifest, and
      handoff exist.

# Verification method

- `python scripts\check.py`
- `python scripts\lint_awkp.py`
- `git diff --check`

# Risk and approvals

R1. This is an architecture alignment task. Any future sandbox implementation
must remain a separate task with its own acceptance criteria.
