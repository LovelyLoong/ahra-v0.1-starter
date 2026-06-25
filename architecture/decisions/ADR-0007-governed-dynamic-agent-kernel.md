# ADR-0007: Governed dynamic Agent execution kernel

- Status: accepted
- Date: 2026-06-25
- Decision owner: human:maintainer

## Context

AHRA 当前同时包含固定任务工作流、有限目标循环、AWKP 治理、EvidenceGate、Policy、Context、Memory、RunService 和多个适配入口。固定 Workflow 对可重复任务仍然有价值，但不应成为长期核心：Planner Agent 可以根据 Goal、反馈和当前状态动态产生新的执行拓扑。

直接让 Planner 生成并运行任意工作流会带来权限扩大、无限派生、验收漂移、状态混淆和不可恢复等问题。因此动态性必须位于确定性治理边界之内。

## Decision

AHRA 将被定位为**受治理的动态 Agent 执行内核**。

1. 人类提交版本化 `GoalContract`。
2. 验收规划先生成 `ClaimGraph` 和 `GatePlan`。
3. Execution Planner 只生成不可信 `PlanDraft`。
4. Plan Compiler、Plan Validator 和 Capability Admission 将其转换为不可变 `PlanIR`。
5. Scheduler 只执行已准入 PlanIR 节点。
6. Executor 只在 Capability Grant 内产生 Artifact。
7. Verification System 以 L0/L1/L2 Gate 产生 Evidence。
8. 最终完成要求全部 Claim 具有 current Evidence，但物理复验只运行失效或强制 Gate。
9. 验收失败生成 `DefectRecord`，触发有界局部修复和选择性复验。
10. Planner、Executor、Verifier 和 EvidenceGate 具有不可合并的权力边界。
11. `standard-harness` 重构为 `bounded_task` 执行原语。
12. `loop-engineering` 冻结为兼容/回归实现，不再作为核心方向。
13. 本阶段不实现框架自我修改。

## Consequences

### Positive

- 工作流拓扑可动态变化，而治理、权限和完成语义保持稳定。
- 验收可以间接约束实现，不需要人类预先规定步骤。
- Evidence 可按依赖摘要复用，减少 Token 和全量测试成本。
- 固定执行器仍可作为认证原语和降级路径。
- Planner 失误不会自动获得副作用权限。

### Negative

- 需要新建 Claim、Gate、Evidence validity、PlanIR、Capability 和 Defect 契约。
- 在 Planner 可用前必须先完成静态 PlanIR 纵向闭环。
- 迁移期会同时维护新旧入口。
- 增量失效图错误可能导致漏测，因此第一版必须保守扩大验证范围。

## Rejected alternatives

### Continue expanding fixed Workflow Modules

拒绝。它会把业务步骤固化到核心，无法满足动态复杂任务，也造成中央 Handler 持续膨胀。

### Let Planner emit executable Python or arbitrary workflow definitions

拒绝。缺少类型、权限、预算、恢复和 Evidence 责任，难以安全审计。

### Run a full independent review after every executor action

拒绝。成本高且造成频繁重头验证。采用 L0 快速确定性 Gate、风险驱动 L1 和逻辑全量/物理增量的 L2。

### Remove all existing workflow code immediately

拒绝。新路径未通过端到端验证前，旧路径仍是回归和降级资产。

## Migration condition

只有 `TASK-0031` 的 fixture 纵向闭环通过，并证明局部修复不会重跑全部 Gate 后，才能由 `TASK-0032` 删除或隔离旧路径。
