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

| Concept | Purpose |
|---|---|
| [Agent workflow foundation](agent-workflow-foundation.md) | Project positioning as a complete Agent workflow and work-governance foundation |
| [Workflow modules](workflow-modules.md) | Concrete workflow implementations plugged into the AHRA template |
| [Framework entrypoints](framework-entrypoints.md) | Default CLI plus Skill operation path and MCP deprecation |
| [Agent drivers and workflow invocation](agent-drivers-and-workflow-invocation.md) | Agent-neutral driver adapters and stable workflow launch requests |
| [Reference runtime adapters and MCP](reference-runtime-adapters-and-mcp.md) | Codex CLI driver, optional Codex SDK driver, resume requests, and MCP entrypoint |
| [Framework completion roadmap](framework-completion-roadmap.md) | Current implementation decisions for the reusable AI-operated framework template |
| [EvidenceGate](evidence-gate.md) | Verifier-side completion gate for acceptance criteria and evidence |
| [ApprovalService](approval-service.md) | Scoped approval records for risky actions without requiring a human-facing UI |
| [Observability and Evaluation](observability-and-evaluation.md) | Minimal local trace, audit, cost, replay, and eval records |
