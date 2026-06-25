# AHRA 受治理动态 Agent 内核文档包

> 状态：**Proposed / 待仓库集成**  
> 生成日期：2026-06-25  
> 目标仓库：`LovelyLoong/ahra-v0.1-starter`  
> 基线分支：`main`

本包把 AHRA 从“固定工作流集合”迁移为“以验收契约为起点、以动态计划为执行方式、以证据有效性为完成条件、以权限内核为安全边界”的 Agent 工作系统。

## 使用顺序

1. 先阅读 `AHRA-DYNAMIC-KERNEL-MASTER-PLAN.md`。
2. 审核并集成 `architecture/decisions/ADR-0007-governed-dynamic-agent-kernel.md`。
3. 按 `work/proposed/TASK-SEQUENCE.md` 的顺序逐项执行 `TASK-0021` 至 `TASK-0032`。
4. 每个任务由执行 Agent 产出 Artifact/Evidence，再由独立 Verifier 验收。
5. 在 `TASK-0031` 通过前，不启用 AHRA 自我修改，也不删除旧执行路径。

## 文档清单

- `AHRA-DYNAMIC-KERNEL-MASTER-PLAN.md`：总架构、迁移原则、验收模型和路线图。
- `architecture/decisions/ADR-0007-governed-dynamic-agent-kernel.md`：核心架构决策。
- `docs/architecture/dynamic-agent-kernel.md`：控制内核与运行流程。
- `docs/architecture/verification-system.md`：Claim、Gate、Evidence、Defect 与选择性复验。
- `docs/architecture/plan-ir.md`：PlanDraft、PlanIR、编译与验证规则。
- `docs/architecture/repository-consolidation.md`：仓库组件处置和删除标准。
- `docs/policies/agent-authority-boundaries.md`：Planner、Executor、Verifier 和 Harness 权限边界。
- `docs/policies/component-lifecycle.md`：组件进入 Core、Experimental、Legacy、Removal 的规则。
- `docs/roadmaps/dynamic-kernel-roadmap.md`：阶段门与实施顺序。
- `work/proposed/CTX-ahra-dynamic-kernel.md`：本次迁移的 Context 契约。
- `work/proposed/TASK-SEQUENCE.md`：逐项执行说明。
- `work/proposed/tasks/`：十二个可直接迁入 AWKP 的任务契约草案。
- `templates/`：执行 Agent 和独立 Verifier 的提示模板。

## 重要说明

本包基于对仓库文件的静态审查生成，没有在维护者本机运行测试，也不声称当前代码已经满足本文档中的目标架构。任务 ID 是截至生成时的建议编号；正式集成前应由 `TASK-0021` 原子确认不存在编号冲突。
