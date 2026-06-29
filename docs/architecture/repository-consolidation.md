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

# Current disposition

| Area | Current disposition | Migration action |
|---|---|---|
| AWKP task/state/event/artifact/evidence | Core | Preserved as task completion and audit authority |
| EvidenceGate | Core | Remains verifier-side AWKP completion gate |
| Goal/Claim/Gate contracts | Core | Current dynamic-kernel acceptance boundary |
| Evidence v2/Defect/selective reverification | Core | Current verification and completion boundary |
| PlanDraft/PlanIR/compiler/validator | Core | Current trusted execution boundary |
| Capability Admission/Gateway | Core | Current default-deny side-effect boundary |
| PlanExecution/NodeRun/Scheduler | Core | Current PlanIR execution path with lease, budget, deadline and checkpoint semantics |
| bounded_task executor | Selected adapter | Implements NodeExecutor behind the dynamic scheduler |
| fixture planner | Selected fixture adapter | Fixture-only planner adapter; still compiled and admitted before execution |
| standard-harness | Deprecated legacy | Frozen compatibility module retained for regression only; not default-visible |
| loop-engineering | Deprecated legacy | Frozen compatibility module retained for regression only; not default-visible |
| WorkflowModuleRegistry | Legacy | Retained for explicit compatibility requests only |
| reference_runner invocation | Legacy | Hidden compatibility CLI path only |
| RunService/CAS/Lease | Core support | Retained for Run and lease semantics; PlanExecutionService owns PlanIR execution state |
| ContextBuilder | Core | Used by planner request construction and fixture runtime |
| MemoryService | Experimental | Not default until a concrete Goal use is admitted |
| ReferencePolicyEngine | Core | Supplies policy decisions used by capability admission |
| MCP server | Removed | Implementation and regression tests deleted; historical references remain trace-only |
| demo.py | Removed | Demo implementation deleted; historical references remain trace-only |
| duplicate architecture docs | Archived/superseded | One active authority per concept through authority map |
| completed work tasks | Archived | Excluded from normal Agent context, preserved for trace |

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
