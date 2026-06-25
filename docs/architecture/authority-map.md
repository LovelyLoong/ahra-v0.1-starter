---
type: Architecture
id: ARCH-authority-map
schema_version: awkp/0.1
title: Architecture authority map
description: Names the single active authority for each live dynamic-kernel concept and records traceable compatibility documents.
status: active
owner: team:platform
source_refs:
  - ../../AHRA_dynamic_kernel_master_plan_2026-06-25.md
  - component-inventory.json
evidence_refs: []
confidence: reviewed
last_verified_at: 2026-06-25T16:05:13Z
review_after: 2026-09-25T00:00:00Z
tags: [architecture, authority, dynamic-kernel]
---

# Authority Map

This map is the default routing table for architecture reads. An active owner
is the only document allowed to define the concept. Trace refs may explain
history or compatibility, but they do not override the active owner.

| Authority ID | Concept | Active owner | Lifecycle | Trace refs |
|---|---|---|---|---|
| AUTH-master-plan | Dynamic-kernel migration plan | [AHRA dynamic kernel master plan](../../AHRA_dynamic_kernel_master_plan_2026-06-25.md) | active | [source-pack duplicate](../../AHRA-DYNAMIC-KERNEL-MASTER-PLAN.md), [task sequence](../../TASK-SEQUENCE.md) |
| AUTH-current-entrypoints | Current implemented local operation path | [Framework entrypoints](framework-entrypoints.md) | active-current | [Component inventory](component-inventory.json) |
| AUTH-component-inventory | Component lifecycle and default exposure inventory | [Component inventory](component-inventory.json) | active-current | [TASK-0021 provisional inventory](../../work/tasks/TASK-0021/evidence/component-inventory.json) |
| AUTH-dynamic-execution-architecture | Governed dynamic execution architecture | [Governed dynamic Agent kernel](dynamic-agent-kernel.md) | active-current-fixture-scope | [Agent workflow foundation](agent-workflow-foundation.md), [Workflow modules](workflow-modules.md) |
| AUTH-verification-model | Claim, Gate, Evidence validity, Defect, selective reverification | [Verification system v2](verification-system.md) | active-current-fixture-scope | [EvidenceGate](evidence-gate.md) remains current task-level gate |
| AUTH-plan-ir | PlanDraft, PlanIR, compiler and validator semantics | [PlanDraft and PlanIR](plan-ir.md) | active-current-fixture-scope | none |
| AUTH-agent-authority-boundaries | Planner, Executor, Verifier, Harness authority split | [Agent authority boundaries](../policies/agent-authority-boundaries.md) | active-policy | root [AGENTS.md](../../AGENTS.md) remains the operational entry map |
| AUTH-component-lifecycle | Component lifecycle classes and default exposure rules | [Component lifecycle policy](../policies/component-lifecycle.md) | active-policy | [Repository consolidation](repository-consolidation.md) gives disposition guidance |
| AUTH-repository-consolidation | Repository cleanup and legacy disposition | [Repository consolidation](repository-consolidation.md) | active-current | [Framework completion roadmap](framework-completion-roadmap.md) is superseded |
| AUTH-dynamic-roadmap | Stage gates and task order after TASK-0021 | [Dynamic Agent kernel roadmap](../roadmaps/dynamic-kernel-roadmap.md) | active-current | [Work index](../../work/index.md), [proposed task sequence](../../work/proposed/TASK-SEQUENCE.md) |

# Read Rules

- Use `AUTH-current-entrypoints` for what works now.
- Use `AUTH-component-inventory` to decide whether a component is core,
  adapter, legacy, experimental, or archived.
- Use `AUTH-dynamic-execution-architecture`, `AUTH-verification-model`, and
  `AUTH-plan-ir` for the current dynamic-kernel concepts that have passed
  EvidenceGate, while preserving the fixture-scope limitation described in
  [Framework entrypoints](framework-entrypoints.md).
- Do not treat fixture-scoped dynamic execution as a production-grade general
  orchestrator.
- Superseded, archived, and legacy documents remain traceable inputs, but they
  are not in the default read order.
