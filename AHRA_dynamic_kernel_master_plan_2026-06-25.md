---
type: Architecture
id: ARCH-ahra-dynamic-kernel-master-plan
schema_version: awkp/0.1
title: AHRA governed dynamic Agent kernel master plan
description: Defines the acceptance-first dynamic planning architecture, verification model, repository consolidation, and implementation sequence for AHRA.
status: active
owner: human:maintainer
source_refs:
  - README.md
  - AGENTS.md
  - SPEC.md
  - WORKFLOW.md
  - architecture/SPEC.md
  - docs/architecture/workflow-modules.md
  - docs/architecture/evidence-gate.md
  - src/ahra/reference_runner/loop_engineering.py
  - src/ahra/reference_runner/standard_harness.py
  - src/ahra/reference_runner/invocation.py
  - src/ahra/evidence_gate.py
  - src/ahra/ports.py
  - work/index.md
evidence_refs: []
confidence: reviewed
last_verified_at: 2026-06-25T00:00:00Z
review_after: 2026-09-25T00:00:00Z
tags: [architecture, planning, verification, security, migration]
---

# 0. 执行摘要

AHRA 的下一阶段不再以“继续增加固定 Workflow Module”为核心，而是建设一个**受治理的动态 Agent 执行内核**。

核心命题是：

> **固定的不是任务步骤，而是目标契约、验收语义、状态权威、安全边界、预算和审计；动态的是任务分解、Agent 数量、执行拓扑、专业角色和修复计划。**

系统从人类提供的 `GoalContract` 开始。验收规划首先把目标转换为 `ClaimGraph` 和 `GatePlan`；执行规划随后生成不可信的 `PlanDraft`；确定性的 Plan Compiler、Policy/Capability Admission 和 Plan Validator 将其编译为可执行的 `PlanIR`。Scheduler 执行 Plan 节点，节点产生 Artifact 与 Evidence。Verification System 通过 L0、L1、L2 三层门禁判断局部正确性、衔接正确性和目标完成性。

最终验收遵循：

> **逻辑上全量，物理上增量。**

完成时，所有顶层 Claim 都必须具有当前有效的 Evidence；但没有被变更影响的 Evidence 可以复用。失败后生成结构化 `DefectRecord`，只修复受影响部分，并只重新运行失效、失败或安全策略要求的 Gate，而不是每次从头执行全部流程。

本阶段明确不做框架自我迭代。AHRA 不允许当前运行修改自己的 Policy、Plan Validator、EvidenceGate、权限定义或顶层验收契约。

# 1. 背景与仓库基线

截至 2026-06-25，仓库已经具备有价值的治理基础：Task、Run、Event、Artifact、Evidence、Handoff、CAS、Lease、Policy、Context 和 EvidenceGate 等概念边界。当前 `standard-harness` 已实现隔离工作区、确定性检查、语义 Reviewer、有界尝试、证据和回滚；`loop-engineering` 已实现目标级循环和有限追加任务。

但代码执行路径仍然以两个硬编码 Workflow Handler 为中心；Planner 主要在预定义任务队列完成且总体检查失败后追加少量 Task。Policy、Context、Memory、RunService 等若干能力在文档或 demo 中存在，但没有全部进入同一条真实运行主链。MCP 被文档定义为非默认路径，却仍然作为默认安装脚本和完整操作面存在。工作任务状态与代码事实也需要一次正式对账。

本规划基于以下文件快照：

| 文件 | 审查时 SHA | 用途 |
|---|---|---|
| `README.md` | `ae4123b2...` | 当前项目定位 |
| `AGENTS.md` | `26bf61cd...` | Agent 规则入口 |
| `architecture/SPEC.md` | `8577b883...` | 总体参考架构 |
| `src/ahra/reference_runner/invocation.py` | `fce829f3...` | 当前运行入口 |
| `src/ahra/reference_runner/standard_harness.py` | `23f3da2c...` | 固定任务执行器 |
| `src/ahra/reference_runner/loop_engineering.py` | `deb5f914...` | 当前目标循环 |
| `src/ahra/evidence_gate.py` | `d4b8e867...` | 当前终结验收门禁 |
| `work/index.md` | `9d6d36cd...` | 当前任务索引 |

正式实施前必须重新获取最新 SHA，并由 `TASK-0021` 记录差异。

# 2. 已确认的架构决策

## 2.1 产品定位

AHRA Core 是可信控制内核，而不是固定工作流产品集合。

Core 负责：

- Goal、Claim、Plan、Run、Node、Artifact、Evidence、Defect 和 Approval 的权威语义；
- Plan 编译、准入、调度、预算、状态、恢复和完成判定；
- 文件、工具、网络、秘密和外部副作用的能力控制；
- 可审计的事件、证据、版本和内容摘要；
- 动态 Agent 的受限创建和角色分离。

Core 不负责：

- 规定唯一 Planner 算法；
- 绑定唯一模型或 Agent SDK；
- 把任意模型输出直接当作可执行工作流；
- 允许 Agent 自行扩大权限；
- 允许执行者或规划者自行宣告完成。

## 2.2 动态工作流默认化

动态规划是目标方向，但 Planner 的输出只能是**不可信的声明式计划草案**。任何 Plan 必须经过 Schema、图结构、验收覆盖、预算、权限、风险和恢复语义验证后才可执行。

固定 Workflow 仅保留为：

- 认证的执行原语；
- 回归测试和兼容场景；
- 动态系统失效时的保守降级路径；
- Planner 可选择的已验证模板。

## 2.3 验收优先

执行规划不得早于验收规划。

先回答：

1. 目标包含哪些可验证 Claim？
2. 每个 Claim 需要什么 Evidence？
3. 哪些 Gate 能产生这些 Evidence？
4. 哪些风险要求独立 Reviewer 或人类批准？

再回答如何实现。

## 2.4 暂不进行框架自迭代

普通 Goal Run 不得修改：

- 顶层 Goal Contract；
- Claim Graph 的含义；
- Policy 和 Capability Admission；
- Plan Compiler/Validator；
- EvidenceGate；
- Runtime 隔离规则；
- 本次运行依赖的 Agent Release。

未来框架自迭代必须建立在版本化治理 Ring、旧内核验收新内核和独立回滚路径之上，本路线图不实现该能力。

# 3. 目标架构

```text
Human Goal Contract
        │
        ▼
Goal Admission ───── Policy / Budget / Scope
        │
        ▼
Acceptance Planning Authority
        │  ClaimGraph + GatePlan
        ▼
Acceptance Validator
        │
        ▼
Execution Planner Agent(s)
        │  untrusted PlanDraft
        ▼
Plan Compiler + Plan Validator + Capability Admission
        │  immutable PlanIR
        ▼
Scheduler / Run Service / Checkpoint
   ┌───────────────┼─────────────────┐
   ▼               ▼                 ▼
Executor Node   Executor Node    Verifier Node
   │               │                 │
   └──── Artifact / Evidence / Events┘
                    │
                    ▼
Verification System
  L0 Node Gate → L1 Integration Gate → L2 Goal Gate
                    │
          ┌─────────┴─────────┐
          ▼                   ▼
       Complete            DefectRecord
                              │
                              ▼
                      bounded repair planning
                              │
                              └── selective re-execution/re-verification
```

# 4. 权威对象

下一阶段只允许以下对象成为核心事实源：

| 对象 | 含义 | 权威源 | 是否可变 |
|---|---|---|---|
| `GoalContract` | 人类目标、边界、成功标准和风险容忍度 | Goal Store/AWKP | 版本化；实质变化需批准 |
| `ClaimGraph` | 对目标成功条件的可验证分解 | Acceptance Store | 版本化、不可静默改写 |
| `GateDefinition` | 如何产生某类 Evidence | Git/Registry | 不可变发布 |
| `PlanDraft` | Planner 提出的不可信计划 | Artifact Store | 不可变 |
| `PlanIR` | 经编译和准入的可执行计划 | Plan Store | 不可变；重规划生成新版本 |
| `NodeRun` | 一个执行或验证节点的一次尝试 | Run Store | 状态机 + CAS |
| `Artifact` | 正式产物 | Artifact Store | 内容寻址、不可变 |
| `Evidence` | 某 Gate 对某 Claim/Subject 的验证结果 | Evidence Store | 不可变；状态可失效/撤销 |
| `DefectRecord` | 失败 Claim、复现、影响范围和修复边界 | Defect Store | 状态机、追加事件 |
| `Approval` | 对特定高风险动作的授权 | Approval Store | 有范围和有效期 |

不允许聊天记录、Planner 内部列表、共享 Markdown 状态或 Telemetry 冒充上述权威对象。

# 5. 验收体系

## 5.1 Claim Graph

顶层成功标准拆分为稳定 Claim。Claim 类型至少包括：

- `functional`：功能和用户行为；
- `structural`：Schema、接口、文件结构和依赖；
- `quality`：测试、性能、可靠性和可维护性；
- `security`：权限、隔离、秘密和副作用；
- `operational`：恢复、取消、重试、可观测性；
- `governance`：状态、证据、审批和审计规则。

每个 Claim 必须有：

- 稳定 ID；
- 来源 Goal Criterion；
- 可验证陈述；
- 依赖 Claim；
- 风险级别；
- 所需 Evidence 类型；
- 最低 Gate 集；
- 完成规则。

## 5.2 三层 Gate

### L0 Node Gate

每个执行节点必须经过低成本快速校验：

- 输出 Schema；
- 文件和能力范围；
- 直接相关单元检查；
- Artifact/Evidence 存在性；
- 未声明副作用；
- 基本一致性。

L0 默认不启动独立语义 Reviewer，除非该节点风险高或产物主要依赖语义判断。

### L1 Integration Gate

在以下边界触发：

- 公共接口或 Schema 改变；
- 两条以上执行分支汇合；
- 安全、状态机、权限或数据边界改变；
- 大量下游依赖当前结果；
- Planner/Policy 将节点标记为高风险；
- L0 证据不足以覆盖跨组件 Claim。

### L2 Goal Gate

最终 Goal Gate 必须逻辑覆盖全部顶层 Claim，包括端到端流程、失败恢复、安全、权限和治理。但它只物理执行缺失、失效、过期、失败或强制要求重跑的 Gate。

## 5.3 Evidence 有效性

Evidence 指纹至少包含：

```text
hash(
  gate_definition_digest,
  claim_ids,
  subject_digests,
  dependency_digests,
  verifier_release_digest,
  runtime_profile_digest,
  policy_digest,
  test_definition_digest,
  relevant_environment_digest
)
```

Evidence 状态：

```text
current -> stale
current -> expired
current -> revoked
current -> contradicted
stale/expired/contradicted -> 通过新 GateRun 产生新的 current Evidence
```

旧 Evidence 不删除，只停止作为完成依据。

## 5.4 增量失效算法

当 Artifact、Policy、Gate、Runtime 或依赖发生变化时：

1. 找出摘要改变的 Subject；
2. 沿 Artifact/Claim/Gate 反向依赖图计算影响闭包；
3. 将相关 Evidence 标记为 stale；
4. 加入原始失败 Gate；
5. 加入受影响下游 Integration Gate；
6. 加入策略规定的 Safety Baseline；
7. 形成 `VerificationSelection`；
8. 只运行该集合；
9. L2 Goal Gate 重新检查全部 Claim 的 Evidence 状态，而不是重新执行全部 Gate。

无法证明无影响时，必须扩大验证范围。

# 6. Defect 与局部修复

最终或集成验收失败不能直接触发整个工作流重跑。系统必须生成 `DefectRecord`，至少包含：

- 失败 Claim 和 Gate；
- 预期与实际结果；
- 可复现命令或场景；
- 受影响 Artifact；
- 初始影响范围；
- 允许修复的路径与能力；
- 已失效 Evidence；
- 修复预算和最大循环数；
- 升级条件。

Repair Planner 只能在 Defect 边界内提出 PlanPatch。修改顶层 Goal、放宽 Claim、删除 Gate 或扩大能力必须重新进入人类/Policy Approval。

修复后的验证顺序：

1. 原始失败 Gate；
2. 修改组件的 L0 Gate；
3. 受影响的 L1 Gate；
4. 轻量全局 Safety/Smoke Gate；
5. L2 逻辑全覆盖检查。

# 7. PlanDraft 与 PlanIR

## 7.1 Planner 输出不是执行权

Planner 输出 `PlanDraft`，只能描述：

- 节点目标；
- Claim 覆盖；
- 输入和输出；
- 依赖关系；
- 所需能力；
- 建议 Agent profile；
- 节点 Gate；
- 预算和失败处理建议。

Planner 不得：

- 直接授予权限；
- 指定绕过 Policy 的 Tool；
- 删除 Claim 或 Gate；
- 自行宣布完成；
- 创建无限子 Agent；
- 将任意生成代码作为新的 Workflow Engine 执行。

## 7.2 Plan Compiler

Compiler 将 PlanDraft 转换为 PlanIR，并执行：

- JSON Schema 与类型校验；
- DAG 无环和引用完整性校验；
- Claim 覆盖与 Evidence 责任校验；
- 输入/输出兼容性校验；
- 预算与 fan-out 上限；
- Capability 请求收敛；
- Runtime Profile 解析；
- Gate 注册与摘要冻结；
- 失败、重试、补偿和取消语义校验；
- Plan 内容摘要和不可变版本生成。

## 7.3 PlanIR 节点类型

第一版只支持小集合：

- `bounded_task`：有边界的代码/文档执行；
- `deterministic_check`：命令或纯函数 Gate；
- `semantic_review`：独立只读 Reviewer；
- `integration_gate`：跨节点验证；
- `approval_wait`：等待明确批准；
- `artifact_transform`：确定性转换或聚合。

不在第一版支持任意动态脚本节点、无限递归 Agent 或运行时创建新节点类型。

# 8. Planner、Executor、Verifier 的权力分离

三者是 Authority Domain，不是固定三个进程。

| Authority | 可以 | 不可以 |
|---|---|---|
| Human/Goal Owner | 提出 Goal、批准 Scope Change 和高风险动作 | 伪造 Evidence |
| Acceptance Planner | 分解 Claim、提出 GatePlan | 实现代码、降低成功标准 |
| Execution Planner | 生成 PlanDraft、提出能力需求 | 自己授予权限、宣告完成 |
| Plan Compiler/Admission | 验证和收敛计划与能力 | 创造业务目标 |
| Executor | 在 Capability Grant 内产生 Artifact | 修改 Goal/Claim/Policy、批准自己 |
| Verifier | 运行 Gate、判断证据、生成 Defect | 偷偷修改实现后自行通过 |
| EvidenceGate | 根据当前 Evidence 决定完成状态 | 生成实现或放宽验收 |
| Scheduler | 派发、预算、并发、恢复 | 解释业务是否正确 |

独立性至少要求生产者和最终 Verifier 的 `agent_release_digest` 或主体身份不同。高风险 Claim 可要求不同模型族、不同运行时或人类批准。

# 9. 安全与能力模型

## 9.1 默认拒绝

Agent 只拥有 PlanIR 中经 Admission 签发的 Capability Grant。未声明能力一律拒绝。

第一版 Capability 至少覆盖：

- `filesystem.read` / `filesystem.write`，绑定 glob 和 workspace；
- `git.diff` / `git.commit`，绑定 branch/worktree；
- `command.exec`，绑定命令模板和工作目录；
- `tool.invoke`，绑定 Tool Descriptor 和参数约束；
- `network.egress`，绑定域名/协议；
- `secret.use`，只允许秘密引用，不暴露明文；
- `agent.spawn`，绑定数量、深度、角色和预算；
- `artifact.read/write`、`evidence.write`。

## 9.2 Reference Monitor

Prompt、AGENTS.md、Skill 不是安全边界。所有副作用必须经过同一个可审计执行点：

```text
Agent intent
   ↓
Tool/Filesystem/Runtime Gateway
   ↓
Capability + Policy + Approval + Budget check
   ↓
Isolated execution
   ↓
Audit event + result digest
```

第一阶段本地实现可以使用受限 worktree 和命令 allowlist，但不得宣称具备进程、网络或秘密隔离。未实现的隔离能力必须显式标记，不得用文档承诺代替技术强制。

# 10. 运行状态与恢复

推荐 Goal Execution 状态机：

```text
draft
  -> admitted
  -> acceptance_planning
  -> acceptance_validating
  -> execution_planning
  -> plan_validating
  -> executing
  -> verifying
       -> repair_planning -> plan_validating -> executing
       -> awaiting_approval
       -> completed
       -> blocked
       -> failed
       -> canceled
```

每次重规划生成新的 `plan_version`，旧 PlanIR 不覆盖。每个 NodeRun 使用独立 attempt ID。Checkpoint 保存节点状态、已完成 Artifact/Evidence 引用、预算、待审批和 Plan 版本；不保存秘密或无限 Transcript。

系统必须设置：

- 最大 Plan 版本数；
- 最大修复循环数；
- 最大节点数和 fan-out；
- 每节点/每 Goal 时间、Token、成本和 Tool 预算；
- 无进展超时；
- 重复 Defect 检测；
- 人类升级条件。

# 11. 现有组件处置

## 11.1 保留并提升

- AWKP 的 Task、State、Event、Artifact、Evidence、Handoff、CAS 和 Lease 规则；
- `EvidenceGate` 的独立完成判定和 Evidence 映射原则；
- Ports/Adapters 的厂商中立边界；
- Worktree 隔离、变更范围、确定性检查和回滚；
- Context Manifest 的内容摘要和信任标签思想；
- Policy 默认拒绝和高风险 Approval 原则。

## 11.2 重构

- `standard-harness` → `bounded_task` Execution Primitive；
- `EvidenceGate` → Goal/Claim 级完成门禁，并接入 Evidence validity；
- `WorkflowRunRequest` → Goal/Plan execution request 或兼容层；
- `WorkflowModuleRegistry` → Node Executor/Gate/Planner Strategy Registry；
- `RunService`、reference runner 状态与 AWKP 状态 → 通过明确 Adapter/Reconciler 连接；
- `ContextBuilder` → 所有 Planner/Executor/Verifier 请求的统一 Context 编译入口。

## 11.3 冻结

- `loop-engineering`：不再添加功能，只保留兼容和回归测试；
- 当前固定 Workflow Module descriptors：不再扩展新模块；
- MCP：不添加 MCP-only 能力；
- Memory：不阻塞动态内核，暂不扩展。

## 11.4 隔离或删除候选

满足以下任一条件且无明确近期接入任务的组件，移入 `experimental/`、`legacy/` 或删除：

- 只有 demo 消费；
- 文档声称存在但真实入口未调用；
- 与当前权威路径重复；
- 默认安装暴露但产品定位已废弃；
- 没有 owner、contract test 或运行入口；
- 无法说明它服务哪个 Core Object。

具体候选：

- 默认 `ahra-mcp` 脚本及 `mcp_server.py`；
- demo-only Memory/Context/Policy 组合；
- 只验证描述但不负责真实执行的 Workflow Module 表象；
- 被新文档替代的重复架构说明；
- 旧 examples 和历史 fixture 中会误导使用者的路径。

删除必须在替代路径通过 `TASK-0031` 端到端验收后进行，并保留迁移记录。

# 12. 仓库权威文档结构

目标结构：

```text
README.md                         人类入口和当前能力
AGENTS.md                         Agent 入口及不可违反规则
WORKFLOW.md                       当前运行治理策略
SPEC.md                           AWKP 对象与知识治理规范
architecture/decisions/           ADR 历史
contracts/schemas/                机器可执行契约

docs/architecture/
  dynamic-agent-kernel.md         当前核心架构唯一入口
  verification-system.md
  plan-ir.md
  repository-consolidation.md

docs/policies/
  agent-authority-boundaries.md
  component-lifecycle.md

docs/future/                      未实现的远期构想
legacy/                           有期限兼容实现
experimental/                     非默认、非稳定能力
```

所有旧文档必须明确标记 `superseded`、`legacy` 或 `future`。不得让多个 active 文档同时定义同一对象或默认入口。

# 13. 实施阶段

## Stage 0：冻结方向与仓库对账

任务：`TASK-0021`、`TASK-0022`

完成条件：

- 所有组件有生命周期分类；
- 当前代码、任务状态、文档和入口差异已记录；
- 新 ADR 和权威文档已集成；
- 旧 backlog 已正式 defer/cancel/rewrite，不再自动推进。

## Stage 1：验收优先内核

任务：`TASK-0023`、`TASK-0024`、`TASK-0025`

完成条件：

- GoalContract、ClaimGraph、GatePlan、Evidence v2、DefectRecord 有 Schema；
- Evidence 失效和选择性复验有确定性实现；
- 不依赖动态 Planner 也能运行完整验证闭环。

## Stage 2：静态 PlanIR 执行

任务：`TASK-0026`、`TASK-0027`、`TASK-0028`、`TASK-0029`

完成条件：

- 手写 PlanIR 可通过编译、能力准入、DAG 调度和节点执行；
- `standard-harness` 已成为执行节点原语；
- Run/Checkpoint/Artifact/Evidence 路径统一；
- 非授权写操作可被确定性拒绝。

## Stage 3：动态规划闭环

任务：`TASK-0030`、`TASK-0031`

完成条件：

- Planner 只能生成 PlanDraft；
- PlanDraft 经 Compiler/Admission 后执行；
- 验收失败生成 Defect，并触发有界 Repair Plan；
- 局部修改只重跑受影响 Gate；
- Goal Gate 对所有 Claim 完成逻辑全覆盖。

## Stage 4：清理与收口

任务：`TASK-0032`

完成条件：

- Legacy/Experimental/Core 边界清晰；
- 无默认暴露的废弃入口；
- 无未分类、无 owner、无测试的 Core 组件；
- 文档和 CLI 只指向新主路径；
- 历史审计链保留。

# 14. 端到端最小可行场景

第一条纵向闭环必须运行在独立 fixture 项目，不得直接让 AHRA 修改自身。

示例 Goal：为 fixture 项目添加一个文档陈旧性检查。

期望流程：

1. Goal Admission 接受目标和边界；
2. Acceptance Planner 生成 5–8 个 Claim；
3. Execution Planner 生成 2–4 个节点；
4. PlanIR Validator 验证 DAG、Claim 覆盖和能力；
5. Executor 在隔离 workspace 修改代码和测试；
6. L0 Gate 快速检查节点；
7. L1 Gate 检查 CLI/文档/测试衔接；
8. 首次 L2 故意发现一个 fixture 缺陷；
9. DefectRecord 限定修复边界；
10. Repair Planner 只修改对应模块；
11. Selection Engine 只重跑失败 Gate、相关组件 Gate、下游 Gate 和 Smoke Gate；
12. L2 复用未失效 Evidence，并完成所有 Claim 覆盖；
13. EvidenceGate 将 Goal/Task 转为 completed。

必须证明：第二次验证没有重新执行全部 Gate，且未受影响 Evidence 摘要保持不变。

# 15. 非目标

本路线图不实现：

- AHRA 自动修改自身；
- 生产级分布式工作流引擎；
- Dashboard 或可视化工作流编辑器；
- 全功能长期 Memory；
- 任意递归子 Agent；
- 自动生产部署、支付、发信或不可逆外部副作用；
- 无人工批准的顶层 Scope Change；
- 通过 Prompt 声明替代真实权限隔离。

# 16. 全局完成定义

AHRA 动态内核第一阶段完成必须同时满足：

- [ ] 人类只需提供 Goal Contract，而不是固定任务序列；
- [ ] 验收规划先于执行规划；
- [ ] Planner 输出只是一份不可信 PlanDraft；
- [ ] PlanIR 经过确定性编译、能力准入和摘要冻结；
- [ ] 手写 PlanIR 和 Planner 生成 PlanIR 走同一执行路径；
- [ ] 每个节点产生 Artifact、Evidence、事件和预算记录；
- [ ] L0/L1/L2 Gate 分层可运行；
- [ ] 最终完成逻辑覆盖所有 Claim；
- [ ] 局部变更只失效受影响 Evidence；
- [ ] Defect 驱动局部修复和选择性复验；
- [ ] Planner/Executor/Verifier 权力分离；
- [ ] Capability 默认拒绝且 Agent 无法自授予；
- [ ] 失败、取消、超时和恢复路径有测试；
- [ ] Legacy 和 Experimental 不出现在默认主路径；
- [ ] 不存在无 owner、无消费者、无测试的 Core 组件；
- [ ] 不依赖 MCP、Dashboard 或远程服务即可运行本地闭环。

# 17. 风险与缓解

| 风险 | 表现 | 缓解 |
|---|---|---|
| 动态规划放大故障面 | 无法判断 Planner、执行器或状态层谁出错 | 先做静态 PlanIR，再接 Planner |
| 验收缓存误复用 | 过期 Evidence 导致错误完成 | 摘要、依赖图、TTL、保守扩大范围 |
| Planner 越权 | 计划中请求任意 Tool/路径 | Capability Admission 默认拒绝 |
| Reviewer 成本过高 | 每节点都启动大模型审查 | L0 确定性校验，风险驱动 L1，L2 增量执行 |
| 状态重复权威 | Task/Run/Workflow 相互覆盖 | 单一 authority + Adapter/Reconciler |
| 迁移中断 | 新路径未稳定就删除旧路径 | 兼容期和 Stage Gate，T0031 后再删除 |
| 文档再次膨胀 | 多份 active 文档定义同一事实 | Authority Map + component/doc lifecycle lint |
| 自托管风险 | 框架修改自身安全边界 | 本阶段禁止；只在 fixture 运行 |

# 18. 执行纪律

每个后续任务必须：

1. 先读取本总规划、对应架构文档和任务契约；
2. 在隔离工作区运行基线；
3. 只完成一个可验证增量；
4. 不顺手实现后续任务；
5. 产生 Artifact、Evidence 和 Handoff；
6. 由不同主体独立验收；
7. 验收失败生成明确 Defect，而不是反复全量重跑；
8. 未通过 Stage Gate 前不得进入下一阶段。
