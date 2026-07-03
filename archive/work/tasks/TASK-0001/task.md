---
type: WorkItem
id: TASK-0001
schema_version: awkp/0.1
title: Validate the AWKP starter repository
description: Run the linter and publish a verification report for the starter repository.
context_id: CTX-awkp-bootstrap
priority: P1
risk_level: R0
requester: human:maintainer
reviewer: agent:verifier
created_at: 2026-06-21T00:00:00Z
depends_on: []
input_refs:
  - ../../../SPEC.md
  - ../../../docs/policies/document-governance.md
output_contract:
  - kind: verification_report
---

# Goal

Demonstrate that the starter repository is internally consistent and can be validated without model-specific tooling.

# Scope

Run `python3 scripts/lint_awkp.py`, correct profile-template defects, and publish a report as an Artifact.

# Non-goals

Do not redesign the profile or weaken linter rules merely to pass.

# Constraints

Do not modify existing event rows. Use an isolated branch/worktree when performing real work.

# Acceptance criteria

- [ ] The linter exits with status 0.
- [ ] The report records command, environment, timestamp, and result.
- [ ] The report is referenced by `artifact-manifest.json` with a SHA-256 hash.

# Verification method

A verifier reruns the linter from a clean checkout and compares the report hash.

# Risk and approvals

R0; automatic execution and independent verification are sufficient.
