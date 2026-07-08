---
type: Index
id: DOCS-architecture-index
schema_version: awkp/0.1
title: Architecture
description: System boundaries, components, and invariants.
status: active
owner: team:platform
source_refs: []
evidence_refs: []
confidence: reviewed
last_verified_at: 2026-06-21T00:00:00Z
review_after: 2026-09-21T00:00:00Z
tags: [architecture]
---

# Architecture

## Default Authorities

| Concept | Purpose |
|---|---|
| [Architecture authority map](authority-map.md) | Single active owner for each live dynamic-kernel architecture concept |
| [Framework entrypoints](framework-entrypoints.md) | Current Mode C plus Goal CLI plus repository documentation operation path |
| [Component inventory](component-inventory.json) | Current component lifecycle and default exposure inventory |
| [Governed dynamic Agent kernel](dynamic-agent-kernel.md) | Acceptance-first dynamic execution architecture for the current fixture-scoped path |
| [Verification system v2](verification-system.md) | Claim, Gate, Evidence validity, Defect, and selective reverification model |
| [PlanDraft and PlanIR](plan-ir.md) | Planner output boundary, trusted compilation, executable DAG, and validation rules |
| [Repository consolidation](repository-consolidation.md) | Component disposition and default-path cleanup rules |
| [Dynamic workflow synthesis](dynamic-workflow-synthesis.md) | Next-phase design for task-specific WorkflowIR generation from modules, filtered docs, validation, and lesson distillation |

## M1 Proposed Architecture

| Concept | Purpose |
|---|---|
| [Gate execution pipeline](gate-execution-pipeline.md) | Proposed path from Gate selection to actual GateRun-backed Evidence |
| [Goal execution lifecycle](goal-execution-lifecycle.md) | Proposed durable parent lifecycle across plan versions, Defects, repairs, and completion |

## Legacy Compatibility And Trace

| Concept | Purpose |
|---|---|
| [Agent workflow foundation](agent-workflow-foundation.md) | Project positioning as a complete Agent workflow and work-governance foundation |
| [Workflow modules](workflow-modules.md) | Legacy workflow module contracts retained for compatibility trace |
| [Agent drivers and workflow invocation](agent-drivers-and-workflow-invocation.md) | Legacy workflow launch and adapter model retained for compatibility trace |
| [Reference runtime adapters and removed MCP trace](reference-runtime-adapters-and-mcp.md) | Optional adapter notes and historical MCP trace |
| [EvidenceGate](evidence-gate.md) | Verifier-side completion gate for acceptance criteria and evidence |
| [ApprovalService](approval-service.md) | Scoped approval records for risky actions without requiring a human-facing UI |
| [Observability and Evaluation](observability-and-evaluation.md) | Minimal local trace, audit, cost, replay, and eval records |

## Trace And Superseded

| Concept | Purpose |
|---|---|
| [Framework completion roadmap](../../archive/docs/architecture/framework-completion-roadmap.md) | Superseded implementation roadmap retained for traceability |
