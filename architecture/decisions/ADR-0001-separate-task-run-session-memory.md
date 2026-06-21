# ADR-0001：分离 Task、Run、Session、Checkpoint 与 Memory

- 状态：accepted
- 日期：2026-06-21

## 决策

Task 由 AWKP 表达工作契约与交付状态；Run 表达一次 attempt；Session 表达交互连续性；Checkpoint 表达可恢复执行状态；Memory 表达跨 Session 可检索信息。

## 原因

它们的生命周期、写入频率、保留策略、权限和失败语义不同。合并会导致 retry 覆盖历史、聊天冒充任务状态、Memory 污染和无法确定恢复点。
