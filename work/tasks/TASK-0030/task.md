---
type: WorkItem
id: TASK-0030
schema_version: awkp/0.1
title: Add acceptance and execution Planner adapters with bounded replan protocol
description: Introduce model-driven planning only after the static execution path is stable.
context_id: CTX-ahra-dynamic-kernel
priority: P1
risk_level: R2
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-25T00:00:00Z
depends_on: [TASK-0029]
input_refs:
  - Claim/Gate contracts
  - PlanDraft/PlanIR compiler
  - AgentDriver port
  - ContextBuilder
  - DefectRecord
output_contract:
  - kind: acceptance_planner_port
  - kind: execution_planner_port
  - kind: repair_planner_port
  - kind: planner_context_builder
  - kind: fixture_planner
  - kind: optional_model_adapter
  - kind: planner_security_tests
---

# Goal

Allow Agents to dynamically create Claims and PlanDrafts without receiving execution or permission authority.

# Scope

- Define provider-neutral AcceptancePlanner, ExecutionPlanner, and RepairPlanner ports.
- Build deterministic Context Manifests containing Goal, policy, Claim subset, available node/Gate types, budgets and current Defects.
- Validate all planner outputs against contracts before compilation.
- Implement a deterministic fixture planner for tests and an optional real AgentDriver adapter path.
- Limit plan nodes, depth, proposed capabilities, repair cycles and total budget.
- Require plan review or human approval for configured risk classes.
- Allow replan only from validated triggers and produce a new Plan version.

# Non-goals

- Do not let Planner execute tools or write project files.
- Do not allow Planner to alter Goal/Policy/Claim semantics during a Run.
- Do not require one model vendor.

# Acceptance criteria

- [ ] Planner roles receive read-only runtime profiles and no project write grants.
- [ ] Malformed, uncovered, cyclic, over-budget or over-privileged drafts fail before execution.
- [ ] Planner input and output are content-addressed Artifacts with release and Context Manifest digests.
- [ ] Fixture planner tests are deterministic and do not require an external account.
- [ ] Optional model adapter failures are structured and cannot silently fall back to a different driver.
- [ ] A Defect can produce a bounded PlanPatchDraft while unchanged nodes and Evidence remain referenced.

# Verification method

- python scripts/check.py
- planner contract/adversarial tests
- context manifest determinism
- budget/fan-out tests
- optional adapter smoke when available
- git diff --check

# Required evidence and handoff

- Publish an implementation/change report with exact files, contracts, migrations, known limitations, and unresolved items.
- Preserve deterministic command outputs or structured summaries with content digests.
- Map every acceptance criterion to one or more Evidence IDs.
- Record the producer Agent Release, Context Manifest, workspace/branch, base commit, and final commit or rejected patch.
- Create an immutable Handoff with one exact next action when blocked, failed, paused, or returned for changes.
- The producer must not mark this task completed; an independent verifier and EvidenceGate decide completion.

# Rollback and compatibility

- Do not silently overwrite released contracts or historical events.
- Use a new schema version when field meaning changes or compatibility is broken.
- Keep compatibility adapters until the task explicitly authorizes their removal.
- Any rollback must preserve Artifact/Evidence references and explain state projection changes.

# Risk and approvals

Risk level: **R2**. Planner quality is evaluated separately from control-plane correctness.
