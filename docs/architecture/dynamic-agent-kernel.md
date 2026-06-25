---
type: Architecture
id: ARCH-dynamic-agent-kernel
schema_version: awkp/0.1
title: Governed dynamic Agent kernel
description: Defines the authoritative control and execution path for acceptance-first dynamic Agent work.
status: active
owner: team:platform
source_refs:
  - ../../AHRA_dynamic_kernel_master_plan_2026-06-25.md
  - ../../architecture/decisions/ADR-0007-governed-dynamic-agent-kernel.md
evidence_refs: []
confidence: reviewed
last_verified_at: 2026-06-25T00:00:00Z
review_after: 2026-09-25T00:00:00Z
tags: [architecture, control-plane, execution, planning]
---

# Summary

AHRA Core controls dynamic Agent work without hard-coding the work itself. A Goal is accepted, converted into verifiable Claims, planned into an untrusted PlanDraft, compiled into PlanIR, executed through capability-restricted nodes, and completed only when every Claim has current Evidence.

# Planes

| Plane | Responsibilities | Must not do |
|---|---|---|
| Governance | Goal, Claim, policy, approval, artifact/evidence authority | Execute tools |
| Planning | Acceptance plan, execution plan, bounded repair plan | Grant permissions or complete Goal |
| Control | Admission, compiler, scheduler, state, checkpoint, budgets | Judge semantic correctness |
| Execution | Agent/model/tool/runtime invocation in isolated workspace | Rewrite governance contracts |
| Verification | Gate selection, execution, evidence validity, defects | Secretly repair implementation |
| Integration | Driver, Tool, MCP/A2A optional adapters | Become a second authority |

# Authoritative service path

```text
GoalService
  -> AcceptanceService
  -> PlanService
  -> AdmissionService
  -> Scheduler
  -> NodeExecutorRegistry
  -> VerificationService
  -> EvidenceGate
```

All CLI, Skill and optional protocol adapters call the same services. No adapter owns workflow logic.

# Core interfaces

```python
class AcceptanceService(Protocol):
    def propose(self, goal_ref: str) -> ClaimGraphDraft: ...
    def validate(self, draft: ClaimGraphDraft) -> ClaimGraph: ...

class PlanCompiler(Protocol):
    def compile(self, draft: PlanDraft, claims: ClaimGraph) -> PlanIR: ...

class AdmissionService(Protocol):
    def admit(self, plan: PlanIR, policy_context: PolicyContext) -> AdmittedPlan: ...

class NodeExecutor(Protocol):
    async def execute(self, node: PlanNode, grant: CapabilityGrant) -> NodeResult: ...

class VerificationService(Protocol):
    def select(self, trigger: VerificationTrigger) -> VerificationSelection: ...
    async def run(self, selection: VerificationSelection) -> VerificationResult: ...

class CompletionGate(Protocol):
    def evaluate(self, goal: GoalContract, claims: ClaimGraph) -> CompletionDecision: ...
```

# Immutability and versioning

- Goal、ClaimGraph、GateDefinition、PlanIR 和 Agent Release 以 digest 绑定。
- Scope change 产生 Goal 新版本，不覆盖旧版本。
- Replan 产生 Plan 新版本。
- Node retry 产生新 NodeRun attempt。
- Evidence 永不原地覆盖；新的 Evidence supersede 旧记录。
- Completion decision 记录所依据的精确摘要集合。

# Dynamic topology limits

A Plan may vary its node count, specialization, sequence and parallelism, but must obey:

- finite DAG;
- maximum nodes and depth;
- bounded concurrency and fan-out;
- explicit inputs/outputs;
- explicit Claim coverage;
- explicit capability requests;
- registered node types and Gates;
- deterministic terminal states;
- bounded retry and repair cycles.

# Replanning triggers

Only these events may create a new Plan version:

- validated DefectRecord;
- unavailable declared capability;
- approved new input;
- dependency Artifact changed;
- budget/policy-driven strategy change;
- explicit Scope Change approval.

A generic model message such as “I think another task is needed” is not itself a replan trigger.

# Stage separation

The initial implementation must proceed in this order:

1. Claim/Gate/Evidence semantics;
2. static PlanIR compiler and validator;
3. capability admission;
4. static DAG execution;
5. Planner adapter;
6. bounded repair planning;
7. legacy cleanup.

This order prevents Planner uncertainty from hiding control-plane defects.
