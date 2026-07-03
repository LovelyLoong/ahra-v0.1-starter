---
type: WorkItem
id: TASK-0092
schema_version: awkp/0.1
title: "Boundary contract schema and Gate 1 freeze semantics for Workflow A v2"
description: "Per ADR-0010, Human Gate 1 freezes a typed boundary contract (must / must_not / completion_signal / free_zone / open_question entries with unique IDs) instead of prose. Add the contract schema, domain objects, and freeze validation, and make the alignment session Gate 1 path freeze the boundary contract with a digest. Executed by Workflow B alone through examples/goals/task-0092-boundary-contract.yaml."
context_id: "CTX-self-hosting-loop"
priority: "P1"
risk_level: "R1"
requester: "human:maintainer"
reviewer: "agent:independent-verifier"
created_at: 2026-07-03T07:30:38.649328Z
depends_on: []
input_refs: ["architecture/decisions/ADR-0010-boundary-contract-acceptance-first-alignment.md", "docs/architecture/intent-alignment-workflow.md", "src/ahra/alignment_session.py", "examples/goals/task-0092-boundary-contract.yaml"]
output_contract:
  - kind: "ahra/artifact/code-change/0.1"
  - kind: "ahra/evidence/test-report/0.1"
---

# Goal

Per ADR-0010, Human Gate 1 freezes a typed boundary contract (must / must_not / completion_signal / free_zone / open_question entries with unique IDs) instead of prose. Add the contract schema, domain objects, and freeze validation, and make the alignment session Gate 1 path freeze the boundary contract with a digest. Executed by Workflow B alone through examples/goals/task-0092-boundary-contract.yaml.

# Acceptance criteria

- [ ] A boundary-contract schema under contracts/schemas/ defines the five typed entry kinds (must, must_not, completion_signal, free_zone, open_question) with required unique entry IDs, and scripts/lint_contracts.py accepts it.
- [ ] Domain objects in src/ahra parse and validate a boundary contract; freeze validation rejects contracts containing open_question entries, duplicate entry IDs, or unknown kinds, covered by unit tests.
- [ ] The alignment session Human Gate 1 freeze path records the typed boundary contract and its digest in the immutable session snapshot; the prose requirement remains only as trace, covered by tests.
- [ ] The change is produced by a Workflow B development-bounded GoalExecution with kernel-derived completion, then approved through the AWKP EvidenceGate by an independent verifier.
