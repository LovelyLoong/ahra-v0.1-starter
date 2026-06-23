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
a complete Agent work system: work-governance rules, executable standard
workflows, artifact and evidence authority, project adaptation boundaries, and
extension contracts for custom workflows.

The preferred use is to run project work through the standard Agent workflows.
Projects may still use other agents or human-operated tools, but their work
must follow this framework's governance rules for scope, state, evidence,
handoff, and completion.

# Layers

The foundation has five layers:

| Layer | Purpose |
|---|---|
| Work-governance framework | Defines task contracts, state authority, events, artifacts, evidence, handoffs, leases, and completion gates. |
| Standard workflows | Provides executable workflows such as `standard-harness` and `loop-engineering`. |
| Project adaptation | Lets a concrete project add local docs, Skills, commands, checks, policies, and domain rules without changing the foundation. |
| Custom workflow extension | Lets advanced users compose or implement project-specific workflow modules behind stable contracts. |
| Operation entrypoint | Uses Skill plus docs now, then CLI plus Skill, to operate the framework consistently. |

# Usage Modes

Supported usage modes are:

1. **Standard workflow mode**: use the built-in workflow modules. This is the
   recommended path.
2. **Governed external-agent mode**: use any compatible human or Agent tool,
   but require it to follow the work-governance framework and produce the
   expected artifacts and evidence.
3. **Project-adapted workflow mode**: add project-specific rules, Skills,
   checks, and adapters while preserving the foundation contracts.
4. **Custom workflow mode**: compose or implement new workflow modules when the
   standard modules are not enough.

# Non-Negotiable Boundary

Workflows are optional at the operation boundary, but governance is not.

Any agent that writes project state, artifacts, evidence, or completion status
must follow the framework rules even if it does not use the built-in workflow
runner.

# Custom Workflow Direction

Custom workflows should feel composable, but the first implementation should
not start with a broad visual builder. The stable foundation should come first:

- workflow module descriptors;
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
2. Make standard workflows the recommended happy path.
3. Keep project adaptation local and explicit.
4. Allow custom workflows through contracts, not ad hoc scripts.
5. Operate through Skill plus docs now and CLI plus Skill next.
