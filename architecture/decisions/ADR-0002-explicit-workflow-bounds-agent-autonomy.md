# ADR-0002：显式工作流边界包住有限 Agent 自主性

- 状态：accepted
- 日期：2026-06-21
- 更新：2026-06-22；由 ADR-0004 明确为可插拔工作流模块原则

## 决策

重试、超时、审批、预算、依赖和完成门禁由 Harness 外围控制面决定。模型只在需要语义判断的节点内运行，并通过受限的 Tool/Spawn 请求影响系统。

工作流实现不得硬编码进 AHRA 领域核心。具体执行顺序、任务循环、目标循环和恢复策略由可插拔 workflow module 提供，并通过 AHRA Port、Run、Artifact、Evidence、Policy 和 Approval 契约接入。

## 原因

确定性控制流更易恢复、测试、审计和控制成本；自由递归多 Agent 会放大错误和权限风险。

AHRA 的目标是通用外围模板。工作流可能有标准 Harness、LoopEngineering 或后续扩展版本；它们共享底层约束，但不应让单一实现污染核心对象边界。
