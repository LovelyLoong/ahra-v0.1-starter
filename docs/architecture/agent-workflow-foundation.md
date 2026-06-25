---
type: Architecture
id: ARCH-agent-workflow-foundation
schema_version: awkp/0.1
title: Agent workflow foundation
description: Defines the project as a complete Agent workflow and work-governance foundation, not only a harness wrapper template.
status: active
owner: team:platform
source_refs:
  - ../../README.md
  - ../../SPEC.md
  - ../../WORKFLOW.md
  - ../../architecture/SPEC.md
  - ../../docs/architecture/workflow-modules.md
evidence_refs: []
confidence: reviewed
last_verified_at: 2026-06-23T14:32:49+08:00
review_after: 2026-09-23T00:00:00Z
tags: [architecture, workflow, foundation]
---

# Summary

This project is an **Agent workflow foundation**.

It is not merely an outer harness template around another project. It provides
a complete Agent work system: work-governance rules, dynamic execution
contracts, artifact and evidence authority, project adaptation boundaries, and
adapter contracts.

The current default use is to operate through the dynamic-kernel entrypoints in
`framework-entrypoints.md`. Projects may still use other agents or
human-operated tools, but their work must follow this framework's governance
rules for scope, state, evidence, handoff, and completion.

# Layers

The foundation has five layers:

| Layer | Purpose |
|---|---|
| Work-governance framework | Defines task contracts, state authority, events, artifacts, evidence, handoffs, leases, and completion gates. |
| Dynamic kernel | Provides the current Goal, Claim, PlanIR, Capability, Scheduler, Evidence, Defect, and Completion path. |
| Project adaptation | Lets a concrete project add local docs, Skills, commands, checks, policies, and domain rules without changing the foundation. |
| Adapter extension | Lets advanced users add planners, executors, runtimes, and drivers behind stable ports. |
| Operation entrypoint | Uses CLI plus Skill plus docs to operate the framework consistently. |

# Usage Modes

Supported usage modes are:

1. **Dynamic-kernel mode**: use the current default dynamic fixture, Python
   services, task inspection, EvidenceGate, and local checks.
2. **Governed external-agent mode**: use any compatible human or Agent tool,
   but require it to follow the work-governance framework and produce the
   expected artifacts and evidence.
3. **Project-adapted workflow mode**: add project-specific rules, Skills,
   checks, and adapters while preserving the foundation contracts.
4. **Legacy workflow compatibility mode**: explicitly invoke historical
   workflow modules for migration or regression trace.

# Non-Negotiable Boundary

Workflows are optional at the operation boundary, but governance is not.

Any agent that writes project state, artifacts, evidence, or completion status
must follow the framework rules even if it does not use the built-in workflow
runner.

# Custom Workflow Direction

Custom execution paths should feel composable, but new default behavior should
not start with a broad visual builder. The stable foundation should come first:

- typed inputs and outputs;
- deterministic gates;
- semantic review gates;
- approval points;
- artifact and evidence records;
- recovery and resume semantics;
- contract and security tests.

Only after these pieces are stable should the project add higher-level
composition helpers.

# Product Direction

The product direction is:

1. Keep the work-governance framework strict and file-auditable.
2. Make the dynamic kernel the default local execution model.
3. Keep project adaptation local and explicit.
4. Allow custom adapters through contracts, not ad hoc scripts.
5. Operate through CLI plus Skill plus docs.
