# ADR-0004: Pluggable workflow modules

- Status: accepted
- Date: 2026-06-22

## Decision

`E:\ahra-v0.1-starter` is the primary repository and the authority for the
outer Harness template: contracts, object boundaries, ports, governance,
evidence, artifacts, policy, context, memory, and adapter rules.

Workflow execution is a pluggable module family. AHRA defines the module
contract and guardrails, but it does not hard-code one workflow implementation
as the only valid path.

`E:\harness-first-starter` is the initial implementation source for the
reference workflow modules. Its code may be migrated into this repository only
behind AHRA ports and contracts. Concrete SDK integrations such as OpenAI
Agents stay in adapters or optional extras, not in the AHRA domain core.

The initial workflow module set is:

1. `standard-harness`: bounded task execution with isolated workspace,
   path/size policy, deterministic checks, independent review, limited retry,
   artifact/evidence capture, and rollback.
2. `loop-engineering`: goal-level orchestration over standard Harness tasks,
   global verification, independent goal review, bounded planning, and human
   plan approval before executing proposed tasks by default.

New workflow modules or extensions must register their scope, inputs, outputs,
state mapping, required ports, safety gates, artifacts, evidence, and tests
before implementation.

## Consequences

- AHRA remains the bottom-layer constraint system and template entry point.
- Workflow modules can evolve independently as long as they preserve AHRA
  Task/Run/Artifact/Evidence/Approval semantics.
- Existing `WorkflowEngine` contracts are extension points, not proof that the
  core must own every workflow implementation.
- No workflow module may let an implementation agent self-declare completion.
- No workflow module may bypass AHRA policy, approval, runtime, artifact, or
  evidence gates.
