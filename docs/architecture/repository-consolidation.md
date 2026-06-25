---
type: Architecture
id: ARCH-repository-consolidation
schema_version: awkp/0.1
title: Repository consolidation and component disposition
description: Defines how AHRA keeps only wired, owned, tested, and documented components in its default core path.
status: active
owner: team:platform
source_refs:
  - ../../AHRA_dynamic_kernel_master_plan_2026-06-25.md
  - ../../work/index.md
evidence_refs: []
confidence: reviewed
last_verified_at: 2026-06-25T00:00:00Z
review_after: 2026-09-25T00:00:00Z
tags: [repository, cleanup, lifecycle, migration]
---

# Goal

AHRA must not accumulate capabilities that exist only in prose, demo code, obsolete adapters or unreferenced contracts. Every component must have a declared lifecycle and a real relationship to the authoritative execution path.

# Component classes

| Class | Meaning | Default exposure |
|---|---|---|
| `core` | Required by the authoritative local execution path | Installed, documented, tested |
| `adapter` | Replaceable implementation of a Core port | Optional or selected explicitly |
| `experimental` | Incomplete research path with no compatibility promise | Not default |
| `legacy` | Temporarily supported old path with removal date | Compatibility only |
| `removal_candidate` | No justified consumer or replacement exists | Not default; delete after review |
| `archived` | Historical records or superseded docs | Read-only, excluded from context |

# Core admission rule

A component may be `core` only when all are true:

- has an owner;
- serves at least one named Core Object or service;
- is reachable from an authoritative CLI/API path;
- has contract and behavior tests;
- has failure and recovery semantics;
- has security boundary documentation;
- emits required events/artifacts/evidence;
- is named in the current architecture index;
- has no contradictory duplicate authority.

# Inventory record

`component-inventory.yaml` should include:

```yaml
components:
  - id: component.evidence-gate
    paths: [src/ahra/evidence_gate.py, docs/architecture/evidence-gate.md]
    class: core
    owner: team:quality
    serves: [Claim, Evidence, CompletionDecision]
    entrypoints: [ahra evidence-gate evaluate]
    consumers: [GoalCompletionService]
    tests: [tests/test_evidence_gate.py]
    replacement: null
    removeAfter: null
```

A linter should reject an unclassified default entrypoint or a `core` component lacking owner/tests/consumer.

# Proposed disposition

| Area | Initial disposition | Migration action |
|---|---|---|
| AWKP task/state/event/artifact/evidence | Core | Preserve and adapt to Goal/Claim objects |
| EvidenceGate | Core, refactor | Add Claim coverage and Evidence validity |
| standard-harness | Core primitive, refactor | Rename/repackage as bounded_task executor |
| loop-engineering | Legacy | Freeze; no features; remove after replacement |
| WorkflowModuleRegistry | Legacy/refactor candidate | Replace with Node/Gate/Planner registries |
| reference_runner invocation | Transitional | Split into Goal/Plan services and compatibility CLI |
| RunService/CAS/Lease | Core candidate | Wire to real execution path or remove duplicate store |
| ContextBuilder | Core candidate | Require in Planner/Executor/Verifier request building |
| MemoryService | Experimental | Move out of default path until a concrete Goal use exists |
| ReferencePolicyEngine | Core candidate | Connect to capability admission and runtime gateway |
| MCP server | Legacy/removal candidate | Remove default script; optional package only if demanded |
| demo.py | Example | Move to examples; must not imply production wiring |
| duplicate architecture docs | Archived/superseded | One active authority per concept |
| completed work tasks | Archived | Exclude from normal Agent context, preserve events |

# Removal procedure

1. Identify consumers and entrypoints.
2. Provide replacement or prove no consumer.
3. Add deprecation note and migration path.
4. Remove from default docs, Skill and packaging.
5. Run contract, import, CLI and fixture scans.
6. Delete code only after a release/stage boundary.
7. Preserve ADR and audit records.
8. Update component inventory and authority index.

# Documentation consolidation

- `README.md` states current reality, not future architecture.
- `AGENTS.md` remains short and points to authoritative policies.
- `SPEC.md` owns AWKP governance semantics.
- `docs/architecture/dynamic-agent-kernel.md` owns current runtime architecture.
- ADRs explain why, not restate the entire live specification.
- Future ideas live under `docs/future/` and are not treated as implemented.
- Superseded docs remain accessible but are excluded from default read order.

# Task backlog reconciliation

Existing queued/ready tasks must not silently continue under obsolete assumptions. `TASK-0021` must inspect each active task and choose one evented outcome:

- retain unchanged;
- rewrite as a new task and cancel the old one;
- defer with an explicit trigger;
- cancel because the new architecture supersedes it;
- reconcile because the implementation already partially exists.

Historical events are append-only. No task state or acceptance history is rewritten.
