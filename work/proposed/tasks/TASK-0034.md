---
type: WorkItem
id: TASK-0034
schema_version: awkp/0.1
title: Make Capability Admission mandatory before Node execution
description: Remove synthetic runtime grants from the default path and require every executable side effect to use a grant issued by Capability Admission.
context_id: CTX-ahra-dynamic-kernel
priority: P0
risk_level: R2
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-26T00:00:00Z
depends_on: [TASK-0033]
input_refs:
  - ../../../docs/policies/agent-authority-boundaries.md
  - ../../../docs/architecture/plan-ir.md
  - ../../../src/ahra/capabilities.py
  - ../../../src/ahra/plan_ir.py
  - ../../../src/ahra/plan_execution.py
  - ../../../src/ahra/reference_runner/bounded_task.py
  - ../../../src/ahra/ports.py
output_contract:
  - kind: plan_capability_intent_contract
  - kind: mandatory_admission_service_wiring
  - kind: runtime_grant_records
  - kind: node_admission_audit
  - kind: legacy_compatibility_adapter
  - kind: security_test_report
---

# Goal

Ensure a Plan node cannot enter execution until every requested runtime capability has been admitted, narrowed, issued and recorded by the configured Capability Admission service.

# Why now

The current model and admission implementation exist, but default scheduling can synthesize runtime grants and PolicyDecision identifiers. That makes the security boundary descriptive rather than authoritative.

# Scope

- Represent PlanIR capability needs as immutable capability intent/request data rather than self-authorized runtime grants.
- Invoke CapabilityAdmissionPort for each runnable Node before the Node enters running.
- Store AdmissionDecision and CapabilityGrant refs/digests on NodeRun or a linked admission record.
- Pass only admitted, current and correctly bound grants into NodeExecutionRequest.
- Remove synthetic PDEC/CGRANT generation from the default Scheduler and dynamic fixture.
- Preserve legacy compatibility through an explicit adapter, not the default path.
- Record deny decisions and ensure denied Nodes cannot cause side effects.

# Non-goals

- Do not implement a production secret broker.
- Do not enable external writes or production deployment.
- Do not add distributed identity.
- Do not broaden the allowed capability set.
- Do not change Evidence current-set semantics.

# Architectural invariants

- Planner and PlanCompiler may request privilege but cannot grant it.
- Capability Admission narrows; it never widens Goal or Policy scope.
- Every runtime grant binds Goal/Plan/Node/role/action/resource/expiry/policy decision.
- A Node without all required grants cannot transition to running.
- Planner, reviewer and verifier write access remains denied by default.
- RuntimeGateway audit must reference the real AdmissionDecision.

# Implementation slices

1. Version the PlanIR capability contract without silently changing released field meaning.
2. Add an admission preparation step to Scheduler.
3. Persist admission/grant refs on NodeRun.
4. Delete or quarantine grant synthesis helpers.
5. Migrate deterministic fixture and bounded_task executor.
6. Add role, scope, expiry and binding tests.

# Acceptance criteria

- [ ] Every Node that performs a side effect has a current CapabilityGrant issued by CapabilityAdmissionService.
- [ ] Capability admission coverage is 100% in dynamic-path tests.
- [ ] No default-path code fabricates policy_decision_id, issuer or admission success.
- [ ] A denied capability leaves the Node non-running and creates an audit/terminal failure record.
- [ ] Privilege widening, wrong role, wrong node, wrong plan, expired grant and undeclared command are rejected.
- [ ] Planner/reviewer/verifier filesystem.write attempts are rejected.
- [ ] The path-escape fixture is denied before side effect and traces to a real AdmissionDecision.
- [ ] Legacy compatibility behavior is explicitly named and excluded from the default path.
- [ ] Full checks and security tests pass.

# Required negative and adversarial cases

- missing admission service
- partial grant set
- resource wider than Goal scope
- resource wider than Policy scope
- expired request or grant
- wrong role/plan/node binding
- stale or superseded grant
- high-risk action without approval
- undeclared command
- attempted synthetic PolicyDecision

# Verification method

- python scripts/check.py
- python scripts/lint_awkp.py
- git diff --check
- capability admission contract tests
- scheduler test proving denied Node never enters running
- runtime gateway audit lineage test
- dynamic fixture security profile

# Required metrics

- capability_admission_coverage
- unadmitted_node_execution_count
- synthetic_grant_count
- deny count by reason
- pre_side_effect_denial_rate
- runtime audit records with valid decision/grant lineage

# Stop conditions

- Stop if compatibility requires treating a Planner request as an admitted grant.
- Stop if a Node can enter running with only a PlanIR capability field and no AdmissionDecision.
- Stop if a denied action is detected only after the external effect.

# Required evidence and handoff

- Publish an implementation/change report with exact files, contracts, schema
  versions, migrations, known limitations and unresolved items.
- Preserve deterministic command outputs or structured summaries with content
  digests.
- Map every acceptance criterion to one or more Evidence IDs.
- Record producer Agent Release, Context Manifest, workspace/branch, base
  commit, final commit or rejected patch.
- Publish the required metrics for this Task.
- Create an immutable Handoff with one exact next action when blocked, failed,
  paused or returned for changes.
- The producer must not mark this Task completed; an independent verifier and
  EvidenceGate decide completion.

# Rollback and compatibility

- Do not silently overwrite released contracts or historical events.
- Use a new schema version when field meaning changes or compatibility breaks.
- Keep legacy adapters explicit and outside the default path.
- A rollback must preserve Artifact/Evidence references and explain state
  projection changes.

# Risk and approvals

Risk level: **R2**. This establishes a real reference monitor in the default path. Any compatibility exception requires explicit maintainer approval and separate tests.
