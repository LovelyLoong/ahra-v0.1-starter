---
type: WorkItem
id: TASK-0079
schema_version: awkp/0.1
title: "Add independent Workflow B semantic code-review gate"
description: "Strengthen Workflow B framework-code production so a development-bounded run is not accepted from file existence and test command evidence alone."
context_id: "CTX-workflow-b-review-gate"
priority: "P0"
risk_level: "R2"
requester: "human:maintainer"
reviewer: "agent:independent-verifier"
created_at: 2026-07-01T11:01:45.247656Z
depends_on: ["TASK-0071"]
input_refs: ["docs/architecture/gate-execution-pipeline.md", "docs/architecture/evidence-gate.md"]
output_contract:
  - kind: "ahra/artifact/code-change/0.1"
  - kind: "ahra/evidence/test-report/0.1"
---

# Goal

Strengthen Workflow B framework-code production so a development-bounded run is not accepted from file existence and test command evidence alone.

# Acceptance criteria

- [ ] A development-bounded framework-code output requires an independent semantic/code-review evidence record mapped to changed files and task criteria.
- [ ] The gate fails closed when semantic review evidence is missing, stale, produced by the same producer actor, or not mapped in evidence-manifest.json.
- [ ] Tests demonstrate that file existence plus passing commands alone is insufficient for acceptance.
