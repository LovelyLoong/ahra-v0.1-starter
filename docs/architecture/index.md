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
| [Governed dynamic Agent kernel](dynamic-agent-kernel.md) | Target acceptance-first dynamic execution architecture |
| [Verification system v2](verification-system.md) | Claim, Gate, Evidence validity, Defect, and selective reverification model |
| [PlanDraft and PlanIR](plan-ir.md) | Planner output boundary, trusted compilation, executable DAG, and validation rules |
| [Repository consolidation](repository-consolidation.md) | Component disposition and default-path cleanup rules |

## Current Compatibility Path

| Concept | Purpose |
|---|---|
| [Framework entrypoints](framework-entrypoints.md) | Current CLI plus Skill operation path and MCP deprecation |
| [Agent workflow foundation](agent-workflow-foundation.md) | Project positioning as a complete Agent workflow and work-governance foundation |
| [Workflow modules](workflow-modules.md) | Concrete workflow implementations plugged into the AHRA template |
| [Agent drivers and workflow invocation](agent-drivers-and-workflow-invocation.md) | Agent-neutral driver adapters and stable workflow launch requests |
| [Reference runtime adapters and MCP](reference-runtime-adapters-and-mcp.md) | Codex Python SDK driver, resume requests, and legacy MCP entrypoint |
| [EvidenceGate](evidence-gate.md) | Verifier-side completion gate for acceptance criteria and evidence |
| [ApprovalService](approval-service.md) | Scoped approval records for risky actions without requiring a human-facing UI |
| [Observability and Evaluation](observability-and-evaluation.md) | Minimal local trace, audit, cost, replay, and eval records |

## Trace And Superseded

| Concept | Purpose |
|---|---|
| [Framework completion roadmap](framework-completion-roadmap.md) | Superseded implementation roadmap retained for traceability |
