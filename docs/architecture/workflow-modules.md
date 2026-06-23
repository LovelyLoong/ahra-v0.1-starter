---
type: Architecture
id: ARCH-workflow-modules
schema_version: awkp/0.1
title: Workflow modules
description: Defines how concrete workflow implementations plug into the Agent workflow foundation.
status: active
owner: team:platform
source_refs:
  - ../../architecture/decisions/ADR-0004-pluggable-workflow-modules.md
evidence_refs: []
confidence: reviewed
last_verified_at: 2026-06-22T00:00:00Z
review_after: 2026-09-22T00:00:00Z
tags: [architecture, workflow, modules]
---

# Summary

`E:\ahra-v0.1-starter` is the primary repository for the Agent workflow
foundation. It owns the stable bottom-layer constraints: contracts, ports,
object boundaries, governance, policy, context, memory, artifact, evidence,
and approval semantics.

Workflow implementations are modules. A module may execute tasks, compose
goals, propose follow-up work, or delegate to an external durable engine, but it
must preserve AHRA's object boundaries and evidence gates.

The built-in modules are the recommended path, but external agents may also
operate under the same work-governance rules. Advanced users may add custom
workflow modules when standard workflows are not enough.

# Module Contract

Every workflow module must declare:

- Stable `module_id`.
- Purpose and non-goals.
- Inputs and outputs.
- Mapping from internal state to AHRA Run and AWKP Task states.
- Required AHRA ports and adapters.
- Deterministic gates, semantic review gates, human approval points, budgets,
  timeouts, retry limits, rollback behavior, and recovery behavior.
- Artifact and Evidence records produced by each accepted or rejected run.
- Contract, recovery, and security tests.

# Initial Modules

`standard-harness` is the default bounded task workflow. It uses an isolated
workspace, path and change-size policy, deterministic checks, independent
read-only review, limited correction attempts, artifact/evidence capture, and
rollback. Its implementation source is `E:\harness-first-starter`'s
`TaskHarness`, migrated only behind AHRA contracts and ports.

`loop-engineering` is the default goal-level workflow. It composes
`standard-harness` tasks, runs cumulative global checks, performs independent
goal review, supports bounded dynamic planning, and requires human plan
approval before executing proposed tasks by default. Its implementation source
is `E:\harness-first-starter`'s `LoopEngine`, migrated only behind AHRA
contracts and ports.

# Non-Negotiable Rules

- AHRA domain code must not import concrete model SDKs, cloud SDKs, databases,
  queues, or sandbox products.
- Workflow modules must not let the implementation agent self-declare Task or
  Goal completion.
- Workflow modules must not bypass AHRA Policy, Approval, Runtime, Artifact, or
  Evidence gates.
- A reviewer PASS is not enough unless the host code verifies criterion
  coverage and internal consistency.
- Formal AWKP task runs must publish accepted changes and review evidence back
  to the source workspace after gates pass, then leave completion to
  EvidenceGate. Standalone fixture or exploratory runs may keep accepted
  changes in isolated artifacts or branches.
- The reference runner must treat `workspaceRef` as a source workspace and run
  module mutations only inside a run-owned isolated workspace.

# Extension Rules

A new module can reuse or extend an existing module, but it must register a new
module contract when it changes state semantics, safety gates, external side
effects, artifact formats, or completion criteria. A small adapter that only
changes a model provider or runtime provider does not need a new workflow
module if the observable contract stays the same.

Higher-level "workflow building block" helpers should be added only after the
module contract, gate types, artifact/evidence records, and recovery semantics
are stable.
