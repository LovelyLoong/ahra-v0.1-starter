# Agent Workflow Foundation / AHRA v0.1

> **状态：建议稿（Proposed Reference Architecture），2026-06-21。**
> 本项目定位为 Agent workflow foundation：一套完整的 Agent 工作流与工作规范底座。AWKP 继续负责项目知识、任务契约、状态投影、事件、交接、产物与证据；AHRA 补齐 Agent 定义、可插拔工作流模块契约、Memory、Context、模型、工具、协议、运行环境、调度、扩缩容、安全、可观测性、评估与人工控制。
> 当前归档的 AWKP 文件标识为 `awkp/0.1`。如果项目将其正式发布为 1.1，只需通过兼容性声明和迁移记录升级版本，不应靠口头版本推断数据格式。

---

## 0. 最终建议

本项目不应只被理解为某个项目外侧的 Harness 模板，也不应当是某一个 Agent SDK 的二次封装。推荐把它作为 Agent 项目底座：工作规范是所有 Agent 的约束，受治理的动态内核路径是推荐执行路径，项目适配和自定义工作流通过稳定契约扩展。

推荐采用：

1. **稳定的领域协议**：Task、Run、Session、Checkpoint、Memory、Artifact、Evidence、Approval 等对象有明确边界。
2. **控制平面与执行平面分离**：控制平面负责准入、调度、状态、策略和恢复；执行平面负责模型调用、工具执行和隔离运行。
3. **可插拔工作流模块包住有限自主循环**：可预测步骤由确定性 workflow module 控制，只有真正需要判断的节点才交给 Agent；AHRA 核心定义契约和门禁，不把某个工作流实现写死。
4. **所有外部能力走端口与适配器**：模型、MCP、A2A、运行时、数据库、向量检索、云部署均可替换。
5. **Memory 不是聊天记录，也不是向量数据库**：它是有作用域、来源、置信度、有效期、权限和晋升流程的知识对象。
6. **模型输出只是“不可信意图”**：任何副作用都必须经过类型校验、策略判定、权限收敛、必要审批和隔离执行。
7. **可观测、可评估、可恢复是第一天能力**：不能等上线后再补 Trace、Checkpoint、Replay、Evidence 和成本账本。
8. **从单机到分布式保持同一契约**：本地可以用 SQLite/文件/容器；规模化时替换为 Postgres、对象存储和 Durable Workflow Engine，而不改领域模型。

基础使用模式：

1. **受治理的动态内核模式**：通过 Goal CLI、PlanIR、Capability Admission、Scheduler、Gate 和 EvidenceGate 运行项目工作。这是当前推荐路径。
2. **受治理的外部 Agent 模式**：使用任意 Agent 或人工工具，但必须遵守任务、状态、证据、交接和完成门禁。
3. **项目适配工作流模式**：项目添加本地 docs、Skills、命令、检查项、策略和适配器。
4. **Legacy workflow compatibility 模式**：`standard-harness`、`loop-engineering` 等历史 workflow module 仅作为回归和迁移兼容路径保留，不再作为默认或推荐路径。

建议把整体划分为八个平面：

```text
┌────────────────────────────────────────────────────────────────────────────┐
│ 1. Governance & Knowledge Plane                                            │
│    AWKP / AGENTS.md / WORKFLOW.md / Docs / Task / Artifact / Evidence      │
├────────────────────────────────────────────────────────────────────────────┤
│ 2. Control Plane                                                           │
│    API / Registry / Admission / Scheduler / Workflow / Approval / Reconcile│
├────────────────────────────────────────────────────────────────────────────┤
│ 3. Execution Plane                                                         │
│    Worker / Agent Loop / Context Builder / Model / Tool / Runtime           │
├────────────────────────────────────────────────────────────────────────────┤
│ 4. Memory & Context Plane                                                  │
│    Session / Checkpoint / Episodic / Semantic / Procedural / Retrieval      │
├────────────────────────────────────────────────────────────────────────────┤
│ 5. Integration Plane                                                       │
│    MCP / A2A / AG-UI / Webhook / Event Envelope / Project Adapters          │
├────────────────────────────────────────────────────────────────────────────┤
│ 6. Trust & Security Plane                                                  │
│    Identity / Policy / Secret Broker / Sandbox / Data & Egress Controls     │
├────────────────────────────────────────────────────────────────────────────┤
│ 7. Observability & Evaluation Plane                                        │
│    OTel / Trace / Audit / Cost / Replay / Offline & Online Evals            │
├────────────────────────────────────────────────────────────────────────────┤
│ 8. Storage Plane                                                           │
│    SQL / Event-Outbox / Object Store / Git / Search Index / Cache           │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. 适用范围与非目标

### 1.1 适用范围

AHRA 面向以下系统：

- 模型本身不保证可靠的多 Agent 派发、通信、状态恢复或长期记忆；
- 同一 Harness 需要支持多个模型、Agent SDK、工具系统和运行环境；
- 工作可能跨分钟、天或数月，并经历重试、审批、人工修改和多次交接；
- Agent 会读取不可信内容、调用外部工具、执行代码或产生真实世界副作用；
- 系统需要从本地开发平滑扩展到团队共享和分布式部署；
- 人类需要看到目标、状态、差异、证据、风险、成本和责任归属。

### 1.2 非目标

AHRA 不规定：

- 某个固定 Agent 框架、模型厂商、云平台或编程语言；
- 某个固定向量数据库、消息队列、Issue Tracker 或对象存储；
- 某个项目具体如何构建、测试、发布或访问生产数据；
- 暴露模型私有思维链；系统只保存必要的决策摘要、动作、输入依据和结果；
- 允许 Agent 绕过策略层直接取得长期凭证或宿主机权限。

---

## 2. 从现有开源方案中提炼出的共同经验

AHRA 不照搬任何一个框架，而是吸收其成熟做法：

| 来源 | 值得吸收的设计 | AHRA 中的位置 |
|---|---|---|
| LangGraph | Durable execution、Checkpoint、暂停/恢复、Human-in-the-loop、短期与长期记忆分离 | Workflow Engine、Checkpoint、Approval |
| Google ADK | Session、Session State、Memory 三者分离；Artifact 和评估独立 | Session Service、Memory Service、Eval Plane |
| Microsoft Agent Framework | 类型化 Agent、Middleware/Telemetry、显式图工作流、长期/HITL 状态 | Agent Package、Workflow、Middleware |
| OpenAI Agents SDK | Agent、Tool、Handoff、Guardrail、Tracing 的简洁对象边界 | Agent Runtime、Tool、Delegation、Trace |
| OpenAI Symphony | Tracker 作为控制面输入、每任务隔离工作区、仓库内 Workflow、并发运行观测 | AWKP Adapter、Workspace、Scheduler |
| OpenHands / SWE-agent | 任意代码必须在可复现沙箱中执行；Trajectory 可检查与回放 | Runtime Provider、Trace/Replay |
| Letta / Mem0 / Graphiti | 记忆块、跨会话检索、写入提炼、去重、实体和时间关系 | Memory Pipeline |
| Temporal / Restate / DBOS | Durable workflow、重试、计时器、恢复、幂等副作用 | Workflow Engine Adapter |
| MCP / A2A / AG-UI | 分别解决 Agent↔工具、Agent↔Agent、Agent↔用户界面的互操作 | Integration Plane |
| OTel / OpenInference / Langfuse | 统一 Trace 语义、模型/工具/检索跨度、成本和评估关联 | Observability Plane |
| OPA / SPIFFE / gVisor | 策略决策外置、工作负载身份、强化沙箱 | Trust & Security Plane |

由此可得一个关键判断：**通用 Harness 的核心不是“如何再写一个 ReAct 循环”，而是如何在不确定 Agent 周围建立可靠、可治理的分布式系统边界。**

---

## 3. 先固定对象边界：避免状态混淆

这是整个系统最重要的领域模型。

| 对象 | 含义 | 权威源 | 生命周期 |
|---|---|---|---|
| **Context** | 一个较大的业务目标或项目上下文 | AWKP/Tracker | 可包含多个 Task |
| **Task** | 对人类可审查的工作契约 | AWKP Task Store | 跨多个 Run |
| **Workflow Definition** | 预定义的步骤、分支、等待与补偿规则 | Git/Registry | 版本化、不可变发布 |
| **Workflow Execution** | 工作流引擎内部的耐久执行实例 | Workflow Engine | 可暂停、恢复、重放 |
| **Run** | 某个 Agent Release 对 Task 的一次执行尝试 | Run Store | 一个 attempt；重试生成新 Run |
| **Session/Thread** | 一段连续交互的消息与临时状态 | Session Store | 可跨多个 Turn |
| **Checkpoint** | 可恢复的 Agent/Workflow 状态快照 | Checkpoint Store | 只追加或版本化 |
| **Turn** | 一次模型主导的推理—工具循环或模型调用 | Trace/Run Store | Run 内部 |
| **Tool Invocation** | 一次有明确身份、参数和副作用边界的工具调用 | Tool Executor/Audit | 幂等或带补偿 |
| **Memory Record** | 可跨 Session 检索的受治理记忆 | Memory Store | 候选→生效→废止 |
| **Artifact** | 正式交付物 | AWKP Artifact Store | 不可变、可寻址 |
| **Evidence** | 验证交付或策略满足情况的记录 | AWKP Evidence Store | 不可变、可复核 |
| **Approval** | 人类或策略主体对具体动作的授权 | Approval Store | 有范围和有效期 |
| **Telemetry** | 对运行的观察，不是业务状态权威 | Trace/Metric/Log Backend | 可采样、可归档 |

### 3.1 必须遵守的状态权威规则

1. **Task 状态**表达“工作是否交付”，由 AWKP/Tracker 权威维护。
2. **Run 状态**表达“某次尝试运行到哪里”，由 Run Service 权威维护。
3. **Workflow 状态**表达“耐久编排如何恢复”，由 Workflow Engine 权威维护。
4. **Session State**只服务当前交互，不得冒充 Task 状态或长期 Memory。
5. **Memory**保存跨会话可检索信息，不得成为 Artifact 或政策的权威副本。
6. **Telemetry**可以丢失或采样，不能作为唯一审计或业务事实。
7. 这些系统之间通过事件和 Reconciler 投影，不得相互直接覆写内部状态。

### 3.2 推荐 ID 体系

```text
CTX-...       业务上下文
TASK-...      工作契约
WFDEF-...     工作流定义版本
WFEX-...      工作流执行
RUN-...       一次执行尝试
SES-...       会话
CHK-...       Checkpoint
TURN-...      模型回合
TCALL-...     工具调用
MEM-...       记忆记录
ART-...       产物
EVD-...       证据
APR-...       审批
REL-...       Agent Release
```

所有跨服务事件至少携带 `tenant_id`、`context_id`、`task_id`、`run_id`、`trace_id`；不适用的字段可以为空，但不得用模糊名称代替。

---

## 4. Agent 不是进程：Agent Package 与 Agent Release

### 4.1 定义

**Agent Definition** 是 Git 中可编辑的源定义。
**Agent Release** 是经校验、评估和签名后生成的不可变版本，其内容摘要是运行时身份的一部分。

Agent Release 至少包含：

- 指令与 Prompt Package 引用；
- 支持的输入/输出 Schema；
- Model Policy，而不是硬编码单一模型；
- 允许的 Tool/Skill 能力集合；
- Memory 读写策略；
- Runtime Profile；
- Token、成本、时间、工具调用和子任务预算；
- Guardrail/Policy 引用；
- 评估套件和最低门槛；
- 可选的 A2A Agent Card 和 AG-UI 能力；
- owner、变更历史、依赖锁定和 release digest。

示例：

```yaml
apiVersion: ahra.dev/v1alpha1
kind: Agent
metadata:
  name: repository-maintainer
  version: 0.1.0
  owner: team:platform
spec:
  instructions:
    refs:
      - prompts/repository-maintainer.md
      - AGENTS.md
  inputSchemaRef: schemas/repository-task-input.json
  outputSchemaRef: schemas/repository-task-output.json

  modelPolicy:
    profile: coding-high-reliability
    requiredCapabilities: [tool_calling, structured_output]
    fallbackPolicy: explicit-compatible-only

  tools:
    grants:
      - tool: filesystem.read
        mode: allow
      - tool: git.patch
        mode: allow_with_policy
      - tool: deployment.production
        mode: human_approval

  skills:
    - ref: skills/doc-gardening/SKILL.md

  memoryPolicy:
    readScopes: [project, task, user-consented]
    writeScopes: [task-episodic, project-candidate]
    directPermanentWrite: false

  runtimeProfileRef: runtimes/local-worktree.yaml
  budgets:
    wallTimeSeconds: 1800
    maxModelCalls: 80
    maxToolCalls: 200
    maxSubtasks: 8
    maxCostUsd: 12.00

  evalSuites:
    - evals/repository-maintainer-regression.yaml
```

### 4.2 硬规则

- Agent Package 不得包含密钥。
- 运行必须记录精确 release digest，不能只记录可变标签 `latest`。
- Tool 权限是白名单；未声明能力默认拒绝。
- Agent 不能直接创建无限量子 Agent。它只能向 Scheduler 提交受预算约束的 `spawn_task` 或 `spawn_run` 请求。
- Prompt、Skill、Policy、Tool Schema、Runtime Profile 任一实质变化都应产生新的 Release。
- Release 通过评估后才能晋升到生产通道；回滚只切换通道指针，不改写旧 Release。

---

## 5. 控制平面

### 5.1 组件

```text
Client / Tracker / AG-UI / A2A
            │
            ▼
       Control API
            │
  ┌─────────┼─────────────────────────────────────────────┐
  ▼         ▼              ▼              ▼               ▼
Registry  Admission     Run Service   Approval Service  AWKP Adapter
  │         │              │              │               │
  └─────────┴──────► Scheduler ◄──────────┴───────────────┘
                         │
                         ▼
                  Workflow Engine
                         │
                         ▼
                   Worker Queues
                         │
                         ▼
                      Workers

Reconciler：持续对账 Task、Run、Workflow、Lease、Artifact 和外部 Tracker。
Outbox/Event Bus：可靠发布状态变化，避免数据库提交成功但事件丢失。
```

### 5.2 Control API

至少提供：

- Agent Definition/Release 注册、验证、晋升和回滚；
- Task 提交、取消、暂停、恢复和查询；
- Run 创建、重试、分叉、取消和状态查询；
- Approval 创建、决策和过期处理；
- Artifact/Evidence 引用；
- Session/Memory 的受权访问；
- 运行时日志、Trace、成本和 Eval 链接；
- A2A、AG-UI 和项目 Tracker 的适配入口。

所有命令型接口必须支持：

- `idempotency_key`；
- `expected_version` 或事务保护；
- actor/workload identity；
- policy decision reference；
- correlation/trace ID；
- 明确的超时和取消语义。

### 5.3 Admission Controller

在 Run 进入队列前检查：

- Agent Release 是否存在且允许在目标环境运行；
- Task 风险等级和审批要求；
- 模型、工具、数据、网络和运行时能力是否匹配；
- tenant/user/team 预算、并发和速率配额；
- 依赖 Task、Artifact 和输入是否就绪；
- 数据驻留、敏感度和日志策略；
- 是否存在相同幂等键或重复执行。

### 5.4 Scheduler

Scheduler 负责：

- 按优先级、公平性、租户配额和能力标签选 Worker；
- 对模型速率限制、工具并发和沙箱容量做 Backpressure；
- 为每次分派签发 lease、fencing token 和 deadline；
- 控制 fan-out、子任务深度和总预算；
- 识别过期 heartbeat 并触发恢复或新 attempt；
- 禁止两个 Worker 同时提交同一 Run 的权威写入。

### 5.5 Reconciler

分布式系统不能只靠“理想事件流”。Reconciler 必须周期性检查：

- Task 显示 working，但没有活跃 Run；
- Run 显示 running，但 lease 已过期；
- Workflow 已成功，但 Artifact/Evidence 未登记；
- Approval 已决定，但 Run 未恢复；
- Worker 已退出，但资源未回收；
- 外部 Tracker 与 AWKP 状态投影不一致；
- 成本或调用数已经超预算；
- 孤儿 Workspace、Checkpoint 和对象存储制品。

纠正动作必须产生事件，不得静默篡改历史。

---

## 6. 工作流与 Agent 自主性的边界

本节定义 AHRA 对工作流的底层约束。具体执行算法由可插拔 workflow module 提供，而不是由 AHRA 领域核心固定实现。当前主仓库为 `E:\ahra-v0.1-starter`；`E:\harness-first-starter` 是初始 reference workflow 的实现来源。

### 6.1 默认原则

**确定性控制流优先，Agent 判断局部化。**

不需要模型决定的事情，不交给模型决定：

- 重试次数；
- 审批门槛；
- 超时；
- 预算；
- 数据权限；
- 完成状态；
- Artifact 哈希；
- 依赖是否满足；
- 生产副作用是否获批。

### 6.2 推荐的四种基础模式

这些模式是 workflow module 可以实现的模式，不是 AHRA 核心必须全部内置的类层级。

1. **Sequential Pipeline**
   明确的分析→实现→验证→审阅。用于大多数工程任务。

2. **Parallel Map/Reduce**
   将独立子任务并行执行，再用确定性聚合器或 Verifier 合并。必须限制 fan-out。

3. **Supervisor–Delegate**
   Supervisor 提出子任务计划，Harness 校验范围、预算与依赖后创建 Task/Run。Supervisor 不拥有绕过 Scheduler 的“无限派生权”。

4. **Worker–Reviewer/Verifier**
   执行者产出，独立 Reviewer 检查；高风险交给人类批准。Verifier 可以拒绝完成并生成 `changes_requested`。

### 6.3 不推荐作为默认的模式

- 多 Agent 在共享聊天里自由争论，最终由某个 Agent 自称达成共识；
- 所有 Agent 共享可写全局状态；
- Agent 自行选择是否需要审查；
- Agent 直接递归派生 Agent，直到“感觉完成”；
- 把完整对话历史当作工作流状态；
- 通过重跑整个 Agent 来处理每个瞬时错误。

### 6.4 Workflow Module Contract

每个 workflow module 必须先登记契约，再迁入实现：

- `module_id`：稳定 ID，例如 `standard-harness` 或 `loop-engineering`；
- 用途与非目标；
- 输入对象：Task、Context、Goal、Run、Approval 或项目适配输入；
- 输出对象：Run 状态、Artifact、Evidence、Handoff、Report、下一步建议；
- 状态映射：模块内部状态如何投影到 AHRA Run/AWKP Task 状态；
- 所需 Port：AgentDriver、RuntimeProvider、WorkspaceProvider、ArtifactStore、EvidenceStore、ApprovalService 等；
- 安全门禁：路径/规模策略、确定性检查、独立 Reviewer、人工审批、预算和超时；
- 产物与证据目录或对象引用；
- 失败、重试、回滚和恢复语义；
- 必须覆盖的 contract/recovery/security 测试。

历史兼容模块：

1. **standard-harness**
   一个有边界任务的 legacy Harness 工作流。来源为 `E:\harness-first-starter` 的 `TaskHarness` 思路。职责包括隔离工作区、路径与变更规模策略、确定性检查、独立只读 Reviewer、有界重试、Artifact/Evidence 捕获、接受提交或回滚。它不得合并、推送或部署，也不再作为默认或推荐路径。

2. **loop-engineering**
   目标级 legacy Loop Engineering 工作流。来源为 `E:\harness-first-starter` 的 `LoopEngine` 思路。职责是在 `standard-harness` 之上运行任务队列、累计全局检查、独立 Goal Reviewer、有限动态规划和默认人工批准计划。Planner 不能宣布完成，也不能绕过父 Goal policy。它仅作为回归和迁移兼容路径保留。

后续模块可以扩展上述模块，也可以新增独立模块，但必须通过 AHRA 端口接入，不能把模型 SDK、云 SDK、数据库客户端或单一 runner 状态写入领域核心。

### 6.5 Durable Workflow Engine 端口

AHRA 只定义接口，不绑定实现。该端口可以由 `standard-harness`、`loop-engineering`、Temporal/Restate/DBOS adapter 或其他模块实现：

```python
class WorkflowEngine(Protocol):
    def start(self, definition_ref, input, idempotency_key) -> WorkflowExecution: ...
    def signal(self, execution_id, signal_type, payload) -> None: ...
    def checkpoint(self, execution_id) -> CheckpointRef: ...
    def cancel(self, execution_id, reason) -> None: ...
    def status(self, execution_id) -> WorkflowStatus: ...
```

实现选项：

- **本地/原型**：进程内状态机 + SQLite；
- **团队部署**：Postgres 队列、事务 Outbox、明确 Step Checkpoint；
- **长任务/高可靠**：Temporal、Restate、DBOS 或其他 Durable Engine 适配器。

工作流历史中应保存小型确定性状态和对象引用；大型 Prompt、Transcript、Artifact 和 Tool Result 存对象存储，历史只保留 URI、摘要和哈希。

---

## 7. Run 生命周期与恢复

推荐 Run 状态机：

```text
created
   ↓
admitted
   ↓
queued ────────────────┐
   ↓                    │
provisioning            │ retry creates a NEW RUN attempt
   ↓                    │
running ──► paused_input│
   │       paused_auth  │
   │       paused_policy│
   │       backoff      │
   │       suspended    │
   ▼                    │
verifying               │
   ├──► succeeded       │
   ├──► failed ─────────┘
   ├──► timed_out
   └──► canceled
```

### 7.1 Task 与 Run 的映射

- 一个 Task 可以有多个 Run；每次 retry、不同 Agent 尝试或重新验证都生成新 `run_id`。
- Run 成功不自动等于 Task completed；还需 AWKP 完成门禁。
- Workflow Engine 的内部 retry 可以重试幂等 Step，但不得伪装成新的业务 attempt。
- 对外部副作用的重复执行必须依赖幂等键、事务或补偿动作，不能只“希望工具不会重复”。

### 7.2 Checkpoint 内容

Checkpoint 只保存恢复所需状态：

- workflow node/step；
- agent loop state；
- message references 或紧凑摘要；
- context manifest ref；
- outstanding tool calls；
- budgets consumed；
- workspace snapshot/ref；
- pending approval/input；
- deterministic random seed（适用时）；
- schema/release/runtime versions。

不得把未加密密钥、完整宿主机环境或无限增长的原始日志放进 Checkpoint。

### 7.3 取消与超时

取消必须向下传播：Task/Run → Workflow → Agent Loop → Model Stream → Tool → Runtime Process。
工具或外部系统不支持取消时，要记录“取消已请求但副作用可能继续”，并触发对账或补偿。

---

## 8. Memory 与 Context：完整设计

## 8.1 Memory 分类

| 类型 | 作用域 | 示例 | 权威性 |
|---|---|---|---|
| **Working Memory** | 当前 Run/Session | 临时计划、变量、已处理项 | Checkpoint 权威；短期 |
| **Episodic Memory** | Run/Task/User | 某次操作、结果、失败路径 | 事件/Trace 派生；不可覆盖 |
| **Semantic Memory** | User/Team/Project/Agent | 偏好、实体事实、稳定经验 | Memory Store；需来源与有效期 |
| **Procedural Memory** | Agent/Project | Skill、Prompt、操作流程 | Git/Agent Release 权威 |
| **Project Knowledge** | Project | 架构、政策、ADR、运行手册 | AWKP Docs 权威 |
| **Artifact/Evidence** | Task/Project | 代码、报告、测试结果 | AWKP Store；不是 Memory |

关键规则：**向量索引只是可重建的检索索引，不是 Memory 的事实权威。**

### 8.2 Memory Record

```json
{
  "schema_version": "ahra/memory-record/0.1",
  "memory_id": "MEM-01J...",
  "kind": "semantic",
  "scope": {
    "tenant_id": "TEN-1",
    "project_id": "PRJ-1",
    "subject_id": "user:42"
  },
  "content": {
    "statement": "用户偏好先看架构决策，再看实现细节。",
    "entities": ["user:42"],
    "tags": ["preference", "communication"]
  },
  "status": "candidate",
  "confidence": 0.72,
  "source_refs": ["SES-123#event-18"],
  "created_by": "REL-memory-extractor@sha256:...",
  "created_at": "2026-06-21T00:00:00Z",
  "valid_from": "2026-06-21T00:00:00Z",
  "valid_to": null,
  "review_after": "2026-09-21T00:00:00Z",
  "sensitivity": "personal",
  "retention_policy": "user-controlled",
  "supersedes": []
}
```

状态建议：

```text
candidate -> active -> superseded
                    -> expired
                    -> tombstoned
candidate -> rejected
```

### 8.3 写入管线

Agent 不得把一句模型推断直接写成永久事实。推荐：

```text
观察/会话/结果
    ↓
候选提取
    ↓
作用域与主体识别
    ↓
敏感度、同意和保留策略检查
    ↓
去重、冲突和时间关系检测
    ↓
事实验证或置信度评估
    ↓
写入 candidate
    ↓
自动规则 / 独立 Verifier / 人类晋升
    ↓
active
```

对项目架构、政策或关键事实，`active memory` 仍不能覆盖 AWKP；应转化为文档变更提案，经审核后进入项目知识层。

### 8.4 读取管线

```text
当前任务与查询意图
    ↓
Memory Query Plan
    ↓
按 tenant/project/user/agent 权限过滤
    ↓
关键词 + 向量 + 图/时间检索（可选）
    ↓
去重、冲突聚类、时效排序、rerank
    ↓
敏感数据与 Prompt Injection 清洗
    ↓
按 token budget 选择片段
    ↓
携带来源、置信度、时间和信任标签注入 Context
```

返回 Memory 时必须带 provenance；模型需要能够区分：已验证事实、用户偏好、历史事件、推断和过期信息。

### 8.5 Memory Policy

每个 Agent Release 声明：

- 允许读取哪些 scope；
- 允许提出哪些类型的候选写入；
- 哪些内容永远不得持久化；
- 最大保留时间；
- 用户删除和导出机制；
- 是否允许跨 Agent 共享；
- 冲突处理和晋升门槛；
- 每轮最大召回条数和 token 预算。

### 8.6 Context Builder

Context Builder 是独立组件，不应散落在 Agent 代码中。固定顺序：

1. 系统宪法、风险政策和 Agent Release；
2. Task Contract、当前 Run State、预算和审批状态；
3. 任务直接引用的 AWKP 知识；
4. 当前需要的 Skill 和 Tool Schema；
5. 受权检索的 Memory；
6. Session 最近消息或摘要；
7. 当前用户输入/事件；
8. 输出格式和验证要求。

Context Builder 输出一个内容寻址的 `Context Manifest`：

```json
{
  "context_manifest_id": "CTXMAN-...",
  "run_id": "RUN-...",
  "agent_release_digest": "sha256:...",
  "items": [
    {"kind":"policy", "ref":"POL-1", "sha256":"...", "trust":"system"},
    {"kind":"task", "ref":"TASK-42", "sha256":"...", "trust":"authoritative"},
    {"kind":"memory", "ref":"MEM-8", "sha256":"...", "trust":"retrieved-untrusted"}
  ],
  "token_budget": 48000,
  "compiler_version": "context-builder/0.1",
  "sha256": "..."
}
```

这样能够解释“模型当时究竟看到了什么”，也便于回放与回归评估。

---

## 9. 模型网关与路由

### 9.1 Model Gateway 职责

- 统一认证、配额、超时、取消、重试和流式协议；
- 记录精确 provider/model/revision 与参数；
- 结构化输出验证；
- 能力注册：Tool Calling、JSON Schema、Vision、长上下文、Batch 等；
- 按质量、延迟、成本、数据驻留和风险路由；
- 预算和速率限制；
- 安全过滤和内容分类；
- Telemetry、token 与成本账本；
- 可选缓存，但必须考虑隐私、租户和非确定性。

### 9.2 不应假设“统一 API = 能力完全等价”

不同模型对 Tool Schema、并行调用、结构化输出、上下文长度、取消和安全策略的语义不同。Model Registry 必须记录能力与约束，而不是把所有 provider 强制伪装成完全相同。

### 9.3 路由规则

- 高风险任务不得静默降级到不满足能力或治理要求的模型。
- Fallback 必须记录原因和新模型身份；必要时重新审批。
- Model retry 与 Task retry 分开；不要因格式错误无限重试。
- 每个调用使用 `deadline`，而不仅是单次 HTTP timeout。
- Agent 的模型选择只是请求建议，最终由 Model Policy/Router 决定。

### 9.4 推荐端口

```python
class ModelGateway(Protocol):
    def invoke(self, request: ModelRequest, policy: ModelPolicy) -> ModelResponse: ...
    def stream(self, request: ModelRequest, policy: ModelPolicy) -> Iterable[ModelEvent]: ...
    def capabilities(self, model_ref: str) -> ModelCapabilities: ...
    def estimate(self, request: ModelRequest) -> CostEstimate: ...
```

可使用 LiteLLM、Envoy AI Gateway、自建 provider adapters 或云厂商网关实现，但 AHRA 核心只依赖此端口。

---

## 10. Tool、MCP 与副作用治理

### 10.1 Tool Descriptor

所有原生工具、MCP 工具、HTTP API、CLI 和 A2A 远端能力都应归一化为内部 Tool Descriptor：

```yaml
apiVersion: ahra.dev/v1alpha1
kind: Tool
metadata:
  name: repository.git.apply_patch
  version: 1.2.0
  owner: team:developer-platform
spec:
  inputSchemaRef: schemas/git-apply-patch-input.json
  outputSchemaRef: schemas/git-apply-patch-output.json
  transport:
    kind: native
    target: tool-runner
  sideEffect: reversible_write
  idempotency: caller_key_required
  timeoutSeconds: 120
  retryPolicy: safe_on_transport_failure_only
  compensationTool: repository.git.reset_commit
  riskLevel: R1
  requiredScopes: [repo:write]
  networkEgress: []
  dataClassesAllowed: [public, internal]
  approvalPolicy: policy_engine
  resultPolicy:
    maxInlineBytes: 65536
    largeResult: artifact_reference
```

### 10.2 副作用分级

| 类别 | 示例 | 默认策略 |
|---|---|---|
| `read_only` | 查询、读取文件、检索 | 策略允许后执行 |
| `reversible_write` | Git 分支修改、草稿、临时资源 | 隔离空间中执行，记录补偿 |
| `external_write` | 发消息、创建工单、调用第三方写 API | 明确作用域；常需批准 |
| `irreversible_or_high_impact` | 生产删除、转账、权限提升 | 人类批准；双重验证；最小凭证 |

### 10.3 Tool 执行管线

```text
模型生成 Tool Intent
        ↓
JSON Schema 校验
        ↓
参数规范化与敏感数据检测
        ↓
Policy Decision + Capability Grant
        ↓
必要时 Approval / Dry Run / Diff Preview
        ↓
短期凭证签发
        ↓
隔离执行 + Deadline + Resource Limit
        ↓
输出校验、大小限制、恶意内容标记
        ↓
Artifact/Evidence/Audit/Trace
        ↓
结果作为“不可信工具输出”返回模型
```

### 10.4 MCP 的位置

MCP 是 Tool/Resource/Prompt 的互操作连接协议，不是：

- Harness 的权限权威；
- Task/Run 状态数据库；
- 永久 Memory；
- 自动可信边界。

MCP Adapter 必须：

- 维护受信 MCP Server Registry；
- 把 Server Tool Schema 转换为内部 Tool Descriptor；
- 不信任工具描述中的安全注解；
- 为每个调用做 Policy、Consent、Scope 和审计；
- 禁止任意 token passthrough；使用用户委托或工作负载短期凭证；
- 限制 Roots、文件系统、网络和数据范围；
- 支持取消、进度和错误映射。

### 10.5 Tool 可靠性规则

- 只有声明幂等或可安全判定未执行的调用才能自动重试。
- “HTTP 超时”不代表远端副作用没有发生，必须用幂等键或查询对账。
- 大结果进入 Artifact Store，模型只接收摘要和引用。
- Tool output 可能包含 Prompt Injection，不得提升为 system instruction。
- 工具版本和 Schema 变化必须兼容管理；Run 记录实际工具版本。

---

## 11. Agent、用户与外部系统互操作

### 11.1 A2A：独立 Agent 系统之间

A2A Adapter 用于：

- 发布 Agent Card；
- 将内部 Task/Run 投影为 A2A Task；
- 交换 Message、Artifact 和状态更新；
- 支持长任务、流式更新和异步回调；
- 在组织或框架边界保留远端 Agent 的不透明性。

内部同进程函数调用无需强行使用 A2A。A2A 边界处必须做身份、能力、数据和 Artifact 校验；远端 Agent 的“已完成”不能绕过本地 AWKP 验证。

### 11.2 AG-UI：用户界面

AG-UI Adapter 用于：

- 将 Run/Task/Tool/Approval 状态实时推送给前端；
- 支持暂停、输入、批准、拒绝、编辑、取消和恢复；
- 同步可见 Agent 状态和 UI Intent；
- 展示 Tool Preview、Artifact Diff、Evidence 和成本；
- 在断线重连后用状态快照和事件序列恢复 UI。

### 11.3 Event Envelope

跨服务事件建议使用 CloudEvents 兼容外壳：

```json
{
  "specversion": "1.0",
  "id": "EVT-...",
  "source": "urn:ahra:run-service",
  "type": "dev.ahra.run.status_changed.v1",
  "subject": "RUN-123",
  "time": "2026-06-21T00:00:00Z",
  "datacontenttype": "application/json",
  "tenantid": "TEN-1",
  "traceparent": "00-...",
  "data": {
    "task_id": "TASK-9",
    "from": "running",
    "to": "paused_auth",
    "version": 7
  }
}
```

事件消费者必须幂等；Event Bus 是传播机制，业务权威仍在对应 Store。

---

## 12. Runtime、Workspace 与执行隔离

### 12.1 Runtime 与 Workspace 分开

- **Workspace**：某个 Task/Run 可写的项目工作目录、分支、挂载和快照。
- **Runtime**：执行命令、代码、浏览器或工具的计算环境。

v0.1 starter 的本地默认边界是 **run-owned Git worktree isolation**：
Workflow runner 必须在每个 Run 独占的 Git worktree 中执行仓库变更、检查、
提交和回滚，避免直接污染源 worktree。这个本地默认不声明 process、
network、host 或 secret 隔离；需要这些能力时必须选择后续的 Runtime
sandbox adapter。

同一 Workspace 可以被新 Runtime 恢复；同一 Runtime 不应无边界承载不同租户的 Workspace。

### 12.2 Runtime Profile

```yaml
apiVersion: ahra.dev/v1alpha1
kind: RuntimeProfile
metadata:
  name: local-worktree
  version: 0.1.0
spec:
  providerClass: local-process
  image: local-host
  user: current-user
  filesystem:
    root: writable
    writableMounts:
      - name: run-owned-worktree
        path: ${AHRA_RUN_WORKTREE}
    deniedPaths: []
  network:
    default: allow
    allow: []
  resources:
    cpu: host
    memoryMiB: 1024
    ephemeralDiskMiB: 10240
    processLimit: 1
  timeoutSeconds: 1800
  snapshot:
    enabled: false
  secrets:
    injection: none
    persistInSnapshot: false
```

### 12.3 隔离等级

| 等级 | 形态 | 用途 |
|---|---|---|
| T0 | 无代码执行，仅模型和只读 API | 文本分析 |
| T1 | 本地子进程 + run-owned Git worktree | v0.1 starter 默认；不得处理不可信代码或敏感凭证 |
| T2 | OCI 容器 | 后续 CI/团队适配器；不是 v0.1 starter 默认 |
| T3 | 强化容器（如 gVisor/Kata 类） | 多租户、不可信代码 |
| T4 | 远端 MicroVM/专用沙箱 | 高隔离、浏览器、复杂代码、外部客户任务 |

### 12.4 RuntimeProvider 接口

```python
class RuntimeProvider(Protocol):
    def provision(self, profile, workspace, identity) -> RuntimeHandle: ...
    def exec(self, handle, command, env, deadline) -> ExecutionResult: ...
    def stream(self, handle, command, env, deadline) -> Iterable[ExecutionEvent]: ...
    def snapshot(self, handle) -> SnapshotRef: ...
    def restore(self, snapshot_ref, profile) -> RuntimeHandle: ...
    def cancel(self, handle, execution_id) -> None: ...
    def destroy(self, handle) -> None: ...
```

### 12.5 通用规则

- 本地 profile 的默认文件系统边界是 run-owned Git worktree；
- 强隔离 profile 的基础镜像使用 digest，不用可变 tag；
- 强隔离 profile 默认非 root、只读根文件系统、无宿主 Docker socket；
- 强隔离 profile 网络默认拒绝，按工具和任务放行；
- Secret 由 Broker 短期注入，不写入镜像、Git、Memory、Prompt 或 Snapshot；
- CPU、内存、磁盘、进程、文件数、执行时长均有上限；
- stdout/stderr 做大小限制、脱敏和 Artifact 外置；
- Runtime 结束后销毁凭证并清理资源；
- 本地 profile 通过 Git worktree、lockfile 和项目命令保持可复现；
- 对不可信代码、敏感凭证或外部客户任务，local worktree 不足以作为隔离边界，必须选择后续强隔离 Runtime adapter。

---

## 13. Scale、队列与弹性

### 13.1 可扩展拓扑

```text
Stateless Control API replicas
          │
          ▼
SQL Metadata + Transactional Outbox
          │
          ├── Event Bus / Queue
          │        ├── general workers
          │        ├── code-sandbox workers
          │        ├── browser workers
          │        └── verifier workers
          │
          ├── Object Store
          ├── Memory/Search Service
          ├── Model Gateway
          └── Telemetry Backend
```

### 13.2 调度与分片

- 优先按 `tenant_id`、`project_id` 或 `context_id` 做一致性和隔离分片；
- Worker Pool 按 runtime、region、data class、GPU/CPU、工具能力分类；
- 每个队列有并发上限、速率限制、优先级和最大等待时间；
- 对单个租户做公平调度，避免一个大 fan-out 吞掉系统；
- 模型限流和工具限流应反馈给 Admission/Scheduler，而非在 Worker 内无限 sleep；
- 使用 lease + fencing token 防止僵尸 Worker 回写；
- 失败进入可观测的 retry/backoff 或 dead-letter 流程，不得静默丢弃。

### 13.3 三种部署档位

#### Local Profile

- 单进程 Control API + Worker；
- SQLite 或本地 Postgres；
- 文件系统对象存储；
- local process runner + run-owned Git worktree；
- 内存队列或 DB 队列；
- OTLP Console/本地 Trace。

目标：协议一致、易调试，不追求高可用。

#### Team Profile

- Stateless API；
- Postgres；
- S3 兼容对象存储；
- Redis 可选，只做缓存/短期协调，不做最终权威；
- 容器 Worker Pools；
- 统一 Model Gateway；
- OTel Collector；
- Approval UI、RBAC 和备份。

#### Scale Profile

- Durable Workflow Engine；
- 多队列、多区域 Worker Pool；
- 强化容器或 MicroVM；
- SPIFFE/SPIRE 类工作负载身份；
- OPA 类策略服务；
- 多租户配额、数据驻留和审计归档；
- 灰度 Agent Release 和在线 Eval/Canary。

### 13.4 规模化时的反直觉规则

- 不要把完整 Transcript 存进消息队列；存引用。
- 不要把向量数据库当事务数据库。
- 不要用 Redis 锁代替所有权版本和 fencing token。
- 不要把“Worker 进程活着”当成 Run 正常；看 heartbeat、progress 和 deadline。
- 不要无限保留 Workflow History；按引擎规则 Continue-as-new、归档或分段。
- 不要给模型无限上下文来掩盖 Memory/Context 设计缺陷。

---

## 14. Trust、Security 与治理

### 14.1 威胁模型

至少考虑：

- 用户输入、网页、文件或 Tool output 中的 Prompt Injection；
- Goal hijacking 和任务范围漂移；
- Tool misuse、参数欺骗和副作用重放；
- Agent 身份伪造、过度授权和跨租户访问；
- Memory poisoning、陈旧事实和恶意共享记忆；
- 不可信 A2A Agent 或 MCP Server；
- 代码执行逃逸、网络横移和凭证窃取；
- 供应链污染：Prompt、Skill、Tool、镜像和依赖；
- 级联失败、无限循环、成本失控和 fan-out 爆炸；
- 日志、Trace、Prompt 和 Memory 中的敏感数据泄露。

### 14.2 三类身份

1. **Human/User Identity**：发起人、审批人、数据主体。
2. **Agent Identity**：Agent Release digest、owner、能力集合。
3. **Workload Identity**：实际运行 Worker/Runtime 的短期加密身份。

授权决策必须同时考虑三者，不能只看“这是某个 Agent 发来的请求”。

### 14.3 Policy Decision Point 与 Enforcement Point

Policy Engine 只作判定；真正阻断动作的是每个 Enforcement Point：

- Admission；
- Context/Memory read/write；
- Model Gateway；
- Tool Executor；
- MCP/A2A Adapter；
- Runtime Provisioner；
- Artifact publish；
- Deployment/外部副作用。

示例策略输入：

```json
{
  "principal": {"human":"user:42", "agent_release":"sha256:...", "workload":"spiffe://..."},
  "task": {"id":"TASK-9", "risk":"R2", "status":"working"},
  "action": "tool.invoke",
  "resource": {"tool":"deployment.production", "environment":"prod"},
  "arguments_summary": {"service":"billing", "region":"us-west"},
  "data_classes": ["internal"],
  "approval_refs": ["APR-7"],
  "budget_remaining": {"usd": 4.20, "tool_calls": 8}
}
```

策略输出不只 `allow/deny`，还可以包含：

- required approval；
- 参数约束或字段掩码；
- 可用 credential scope；
- 强制 runtime tier；
- 日志/保留策略；
- 最大调用次数；
- reason code 与 policy version。

### 14.4 Secret Broker

- Agent 永远不读取长期主密钥；
- Tool Executor 按已批准动作请求短期、最小范围凭证；
- 凭证绑定 workload、tool、resource、task、expiry；
- 不把 token 返回模型；
- 凭证使用和拒绝进入 Audit；
- Snapshot、Artifact、Memory、日志和错误信息必须做 Secret 扫描。

### 14.5 内容信任标签

Context 中每一项至少标注：

```text
system-authoritative
project-authoritative
human-provided
retrieved-untrusted
tool-output-untrusted
remote-agent-untrusted
model-generated
```

低信任内容不得改变高信任政策；任何内容要求“忽略系统规则”都按数据处理，而不是执行指令。

### 14.6 供应链

- Agent Release、Prompt Package、Skill、Tool、Runtime image 使用 digest；
- 生产发布前做依赖锁定、漏洞扫描、许可检查和评估；
- 可选签名与证明；
- 变更有 owner、review 和 rollback；
- 不允许运行时从不受信来源任意下载并执行代码，除非在专门隔离、无凭证环境中。

---

## 15. Observability、Audit、Cost 与 Replay

### 15.1 Trace 层级

```text
Task Trace
└── Workflow Execution
    └── Run Attempt
        ├── Context Build
        │   ├── AWKP Retrieval
        │   └── Memory Retrieval
        ├── Agent Step / Turn
        │   ├── Model Call
        │   ├── Tool Call
        │   ├── Policy Decision
        │   └── Approval Wait
        ├── Runtime Command
        └── Verification / Eval
```

推荐以 OpenTelemetry 为通用导出协议，并采用 GenAI/OpenInference 语义补充模型、Agent、工具和检索字段。后端可以是 Langfuse、其他 LLM 平台或通用 APM；核心不应绑定 UI 产品。

### 15.2 每次 Run 至少记录

- task/context/run/session/workflow/trace ID；
- Agent Release、Prompt/Skill/Policy/Tool/Runtime 版本；
- Context Manifest；
- 模型、参数、token、cache、延迟、成本；
- Tool args 摘要、结果状态、幂等键和副作用引用；
- Memory 查询、返回 ID 和写入候选；
- Policy/Approval 决策；
- Checkpoint、retry 和恢复原因；
- Artifact/Evidence；
- 最终状态与失败分类。

### 15.3 隐私默认值

- 默认导出元数据、哈希、大小和引用；
- Prompt、Completion、Tool Result 和 Memory 正文采用 opt-in，并在导出前脱敏；
- 支持按 tenant/project/data class 设置采样与保留；
- Audit Log 与 Debug Trace 分开：Audit 不可随采样丢失，Debug Trace 可以采样和过期；
- 不记录私有思维链；记录可审计的动作理由、证据和决策摘要。

### 15.4 Replay

Replay 分三种：

1. **Deterministic Workflow Replay**：从事件历史恢复控制流。
2. **Recorded Dependency Replay**：用已记录的模型/工具 cassette 重放，检查 Harness 行为。
3. **Live Re-evaluation**：在固定数据集上用新 Agent Release/模型重新运行，比较结果。

不能承诺用今天的外部模型完全复现过去的自然语言输出；可复现目标应是：输入包、版本、动作轨迹、依赖响应和验证结果可检查。

---

## 16. Evaluation 与发布门禁

### 16.1 七层评估

1. **Schema/Contract**：输入输出、事件、工具参数、状态转换。
2. **Deterministic Unit/Integration**：Context Builder、Policy、Memory 去重、幂等、取消。
3. **Trajectory**：工具选择、调用顺序、无越权、无无效循环。
4. **Outcome**：任务是否满足验收条件，Artifact 是否正确。
5. **Safety/Security**：Prompt Injection、Memory Poisoning、Tool Abuse、跨租户。
6. **Resilience**：模型超时、Worker 崩溃、重复事件、网络分区、恢复和补偿。
7. **Operational**：延迟、token、成本、成功率、人工介入率和资源消耗。

### 16.2 Eval 对象

```yaml
apiVersion: ahra.dev/v1alpha1
kind: EvalSuite
metadata:
  name: repository-maintainer-regression
  version: 0.3.0
spec:
  datasetRef: datasets/repo-maintenance-v4.jsonl
  agentReleaseSelector: repository-maintainer
  sandboxProfileRef: runtimes/eval-repo.yaml
  scorers:
    - type: schema
    - type: deterministic-tests
    - type: tool-trajectory
    - type: artifact-verifier
    - type: security-policy
    - type: llm-rubric
  gates:
    deterministicPassRate: 1.0
    securityViolations: 0
    taskSuccessRate: 0.90
    maxMedianCostUsd: 1.50
```

### 16.3 发布策略

```text
Draft Agent Definition
    ↓ lint/schema
Candidate Release
    ↓ offline regression + security
Staging
    ↓ shadow/canary + human review
Production channel
    ↓ continuous eval & drift detection
Rollback / supersede
```

LLM-as-a-Judge 可以作为一个 scorer，但不应成为高风险任务唯一的完成证据。确定性测试、外部验证器和人类门禁优先。

Eval Result 应生成 AWKP Evidence，并关联 Agent Release、数据集、运行环境、模型和 Context Builder 版本。

---

## 17. Human-in-the-loop

### 17.1 Approval 是一等对象

```json
{
  "approval_id": "APR-7",
  "task_id": "TASK-9",
  "run_id": "RUN-12",
  "requested_by": "REL-deployer@sha256:...",
  "action": "tool.invoke",
  "resource": "deployment.production",
  "preview_ref": "ART-change-plan-4",
  "risk_level": "R2",
  "requested_scopes": ["deploy:billing:us-west"],
  "expires_at": "2026-06-21T02:00:00Z",
  "status": "pending",
  "decision_by": null,
  "decision_reason": null
}
```

批准必须绑定具体动作、参数摘要、资源、范围和有效期。禁止“这个 Agent 以后什么都可以做”的模糊永久批准。

### 17.2 人类操作

界面至少支持：

- 查看目标、当前状态、负责人、预算和风险；
- 查看 Agent Release、Context 来源和 Tool Preview；
- 批准、拒绝、修改参数或缩小范围；
- 提供缺失输入；
- 暂停、取消、恢复或创建新 attempt；
- 比较 Artifact diff 和 Evidence；
- 查看关键 Trace，而非私有思维链；
- 把人工决定写入 Event/Audit，而非只留在聊天。

---

## 18. 通用扩展端口

核心代码只依赖下列抽象接口：

```text
AgentRegistry
TaskStore / AWKPAdapter
RunStore
EventStore / EventPublisher
WorkflowEngine
Scheduler / Queue
SessionStore / CheckpointStore
MemoryStore / MemoryRetriever / MemoryConsolidator
ContextBuilder
ModelGateway
ToolRegistry / ToolExecutor
MCPAdapter
A2AAdapter
AGUIAdapter
RuntimeProvider / WorkspaceProvider
PolicyEngine
IdentityProvider
SecretBroker
ApprovalService
ArtifactStore / EvidenceStore
TelemetryExporter
EvalRunner
ProjectAdapter
DeploymentAdapter
TrackerAdapter
```

### 18.1 ProjectAdapter

项目强相关能力留在这里：

```python
class ProjectAdapter(Protocol):
    def prepare_workspace(self, task, run, runtime_profile) -> WorkspaceRef: ...
    def bootstrap(self, workspace) -> StepResult: ...
    def health_check(self, workspace) -> EvidenceRef: ...
    def test(self, workspace, scope) -> EvidenceRef: ...
    def build(self, workspace, target) -> ArtifactRef: ...
    def preview_change(self, workspace) -> ArtifactRef: ...
    def publish_candidate(self, workspace, approval_ref=None) -> ArtifactRef: ...
```

这样不同项目可以使用 Git、数据库、云资源、设计文件或数据管道，而不污染 Harness 核心。

### 18.2 Adapter Capability Negotiation

每个 Adapter 声明：

- 支持的协议版本；
- 支持的能力；
- 限制和最大值；
- 一致性/幂等语义；
- 数据驻留；
- 健康状态；
- schema digest。

Harness 不得通过捕获运行时异常来猜测 Adapter 能力。

---

## 19. 推荐仓库结构

```text
agent-harness/
├── AGENTS.md
├── WORKFLOW.md
├── README.md
├── pyproject.toml / package manifests
├── architecture/
│   ├── SPEC.md                         # AHRA
│   ├── decisions/
│   └── threat-model/
├── SPEC.md                             # AWKP
├── docs/                               # AWKP durable knowledge
├── work/                               # AWKP tasks, state, events, handoffs
├── artifacts/                          # AWKP artifact references
├── evidence/                           # AWKP evidence references
├── sources/                            # AWKP source references
├── skills/                             # AWKP and project procedures
├── schemas/                            # AWKP schemas
├── contracts/
│   ├── schemas/
│   ├── events/
│   └── compatibility/
├── control_plane/
│   ├── api/
│   ├── registry/
│   ├── admission/
│   ├── scheduler/
│   ├── workflow/
│   ├── approval/
│   └── reconciler/
├── execution_plane/
│   ├── worker/
│   ├── agent_runtime/
│   ├── context_builder/
│   ├── model_gateway/
│   ├── tool_executor/
│   └── runtime_provider/
├── memory/
│   ├── service/
│   ├── retrieval/
│   ├── consolidation/
│   └── policies/
├── adapters/
│   ├── models/
│   ├── mcp/
│   ├── a2a/
│   ├── ag_ui/
│   ├── workflows/
│   ├── runtimes/
│   ├── trackers/
│   └── projects/
├── observability/
├── evaluations/
├── deployment/
│   ├── local/
│   ├── team/
│   └── scale/
├── examples/
└── tests/
    ├── contract/
    ├── recovery/
    ├── security/
    └── evals/
```

---

## 20. 推荐默认技术组合，但保持可替换

这是“参考实现默认值”，不是规范强制：

| 能力 | Local 默认 | Team/Scale 可替换 |
|---|---|---|
| API/Domain | Python + FastAPI/Pydantic | Go/Java/TS 等保持 Schema 兼容 |
| Metadata/Run Store | SQLite | Postgres |
| Execution path | Mode C Goal CLI + PlanIR scheduler + local process runner + command-gate contract | Temporal / Restate / DBOS adapter 或项目自定义模块 |
| Queue | DB queue | Kafka/NATS/SQS/云队列或引擎内队列 |
| Artifact | 本地文件 + SHA-256 | S3 compatible + retention/versioning |
| Memory | SQL records + optional local index | SQL authority + vector/graph/search index |
| Runtime | local process runner + run-owned Git worktree | Docker/Podman/gVisor/Kata/MicroVM/remote sandbox |
| Model Gateway | Provider adapters | LiteLLM/Envoy AI Gateway/自建网关 |
| Policy | 内置 declarative rules | OPA/云策略服务 |
| Identity | 开发 token | OIDC + workload identity/SPIFFE 类体系 |
| Observability | OTel console/collector | OTel + Langfuse/APM/SIEM |
| Protocols | Native HTTP | MCP + A2A + AG-UI adapters |

最重要的是：**先稳定契约，再选择产品。** 产品可以替换，Task/Run/Memory/Tool/Policy/Event 的语义不应随产品变化。

---

## 21. 分阶段实现路线

### Phase 0：契约冻结

交付：

- 本文架构与 ADR；
- Task/Run/Agent/Tool/Memory/Runtime/Policy/Event JSON Schema；
- Port interfaces；
- AWKP 与 Run/workflow module 状态映射；
- 威胁模型和数据分类；
- Contract test harness。

完成标准：两个假实现可以通过同一组契约测试。

### Phase 1：单机 Reference Core

范围：

- Agent Registry；
- Run Service + 本地 Scheduler；
- `standard-harness` reference module；
- `loop-engineering` reference module；
- SQLite Store；
- Context Builder；
- Model Gateway adapter；
- Tool Registry/Executor；
- Docker Runtime；
- AWKP Adapter；
- OTel trace；
- Approval pause/resume；
- 基础 Working/Semantic Memory；
- 最小 Eval Runner。

完成标准：进程崩溃后可以从 Checkpoint 恢复；工具副作用可审计；Task 只有在 Evidence 门禁通过后完成。

### Phase 2：团队共享

范围：

- Postgres、对象存储、事务 Outbox；
- 多 Worker Pool 和配额；
- MCP Adapter；
- AG-UI 控制台；
- Agent Release 晋升与回滚；
- Memory 候选晋升、删除和时效治理；
- 离线回归、Trajectory 与安全评估；
- 更完整的 Reconciler 和运维 Runbook。

完成标准：多 Worker 故障、重复消息和审批等待下仍能保持一致；可追踪每次 Run 的成本和上下文。

### Phase 3：跨系统与规模化

范围：

- Durable Workflow Engine adapter；
- A2A；
- 强化沙箱/远端 Runtime；
- 工作负载身份、短期凭证和集中策略；
- 多租户、数据驻留、HA/DR；
- Canary、在线评估和自动回滚建议；
- 跨区域队列和对象归档。

完成标准：明确的 SLO、容量模型、故障演练、恢复时间和安全审计。

### 推荐实施顺序

```text
Domain contracts
  → Run + workflow module state mapping
  → Runtime isolation
  → Model + Tool gateway
  → Context + Memory
  → Observability + Eval
  → Approval/UI
  → MCP/A2A
  → Distributed scale & hardening
```

不要先做复杂多 Agent 图，再补状态、安全和恢复；那会把不可控行为放大。

---

## 22. 核心 SLO 与指标

### 22.1 可靠性

- Run terminal-state consistency；
- lease 过期恢复时间；
- duplicate side-effect rate；
- orphan workspace/runtime 数量；
- checkpoint recovery success；
- event reconciliation lag。

### 22.2 质量

- Task acceptance success；
- changes_requested rate；
- verifier disagreement；
- evidence completeness；
- regression pass rate；
- memory precision/recall 与过期召回率。

### 22.3 效率

- end-to-end latency；
- queue wait；
- model/tool/runtime 各阶段耗时；
- token/cost per accepted task；
- context utilization；
- tool retry/waste；
- human approval wait。

### 22.4 安全

- policy deny 与 override；
- unapproved high-risk attempts；
- secret/PII detections；
- cross-tenant access attempts；
- prompt-injection test pass rate；
- memory poisoning detection；
- sandbox/egress violations。

指标必须能按 tenant、project、Agent Release、model、tool、runtime 和风险等级切片。

---

## 23. 必须避免的架构反模式

1. **万能 Agent Object**：Session、Memory、Tools、Workflow、权限和数据库都隐藏在一个类里。
2. **共享全局 Memory**：不同用户/项目/Agent 无作用域隔离。
3. **Vector DB 即真相**：事实、来源、时效和删除语义缺失。
4. **聊天即状态**：恢复只能重新阅读大量 Transcript。
5. **模型自证完成**：没有独立 Evidence 或 Verifier。
6. **MCP 即安全边界**：信任远端 Tool 描述或直接传递用户 token。
7. **容器即绝对安全**：给容器宿主 socket、广泛网络和生产凭证。
8. **无限自主递归**：Agent 可无预算创建子 Agent。
9. **Telemetry 即 Audit**：采样后关键授权记录丢失。
10. **静默 Fallback**：换模型、工具或权限后不记录。
11. **重试一切**：非幂等副作用被重复执行。
12. **只测最终回答**：不检查 Tool trajectory、权限和恢复。
13. **框架锁定领域模型**：更换 SDK 就要迁移 Task/Run/Memory 数据。
14. **先做分布式再定契约**：系统复杂度先于语义稳定。

---

## 24. AHRA v0.1 的十二条不可妥协准则

1. AWKP 是治理与工作知识平面，不是整个 Harness。
2. Task、Run、Session、Checkpoint、Memory、Artifact 必须分开。
3. 可插拔 workflow module 控制确定性流程，Agent 自主性被预算和策略包围；AHRA 核心只定义契约、端口和门禁。
4. 重试生成可识别 attempt；外部副作用必须幂等或可补偿。
5. Agent Release 不可变、可寻址、可评估、可回滚。
6. Context 由独立 Builder 生成并保存 Manifest。
7. Memory 写入先成为候选，带来源、作用域、时效和权限。
8. 所有 Tool/MCP/A2A 结果均视为不可信数据。
9. v0.1 本地默认只承诺 run-owned Git worktree isolation；不可信代码、敏感凭证或外部客户任务必须进入强隔离 Runtime adapter，Secret 使用短期最小权限。
10. OTel Trace、不可丢失 Audit、成本账本和 Eval 从第一天存在。
11. 完成状态由 AWKP 门禁与独立 Evidence 决定，不由 Worker 自证。
12. 所有基础设施通过 Port/Adapter 替换，项目差异进入 ProjectAdapter。

---

## 25. 下一步应冻结的决策

进入实现前，项目需要正式形成 ADR，但不阻塞当前架构：

1. 核心实现语言与 API 风格；
2. Local Profile 是否采用 SQLite，Team Profile 是否采用 Postgres；
3. 第一版 workflow module registry、模块契约和 reference module 边界；
4. 第一批强隔离 Runtime adapter 是 OCI、Dev Container 还是远端 Sandbox；
5. 第一批支持的模型 Provider；
6. Memory 的最小范围：仅 project/task，还是包含 user preference；
7. 哪些风险动作需要人工批准；
8. Trace 正文的默认采集和保留策略；
9. 第一批 MCP Server/Tool；
10. 第一套端到端 Eval 数据集和 SLO。

推荐默认：先做 **Python + Postgres-compatible domain + local SQLite + local process runner + run-owned Git worktree isolation + OTel + Mode C Goal CLI + PlanIR scheduler + command-gate contract**，但所有端口按可替换设计；当不可信代码、敏感凭证、长任务、跨天等待和分布式恢复成为真实需求时，再切强隔离 Runtime adapter、Durable Engine 或项目自定义 workflow module。`standard-harness` 和 `loop-engineering` 仅作为 legacy regression / migration compatibility 输入保留。

---

## 26. 参考资料（官方与项目文档）

- LangGraph Overview — `docs.langchain.com/oss/python/langgraph/overview`
- Google Agent Development Kit: Sessions and Memory — `adk.dev/sessions/`
- Microsoft Agent Framework Overview — `learn.microsoft.com/en-us/agent-framework/overview/`
- OpenAI Symphony Specification — `github.com/openai/symphony/blob/main/SPEC.md`
- OpenHands Runtime Architecture — `docs.openhands.dev/openhands/usage/architecture/runtime`
- Letta Stateful Agents — `docs.letta.com/guides/core-concepts/stateful-agents`
- Mem0 Memory Evaluation / Architecture — `docs.mem0.ai/core-concepts/memory-evaluation`
- Model Context Protocol Specification 2025-11-25 — `modelcontextprotocol.io/specification/2025-11-25`
- A2A Protocol Specification — `a2a-protocol.org/latest/specification/`
- AG-UI Overview — `docs.ag-ui.com/introduction`
- CloudEvents — `cloudevents.io`
- Temporal Workflow Execution — `docs.temporal.io/workflow-execution`
- Restate Workflows — `docs.restate.dev/use-cases/workflows`
- DBOS Architecture — `docs.dbos.dev/architecture`
- Development Container Specification — `containers.dev/implementors/spec/`
- gVisor Documentation — `gvisor.dev/docs/`
- Open Policy Agent — `openpolicyagent.org/docs`
- SPIFFE Overview — `spiffe.io/docs/latest/spiffe-about/overview/`
- OpenTelemetry GenAI Semantic Conventions — `opentelemetry.io`
- OpenInference Specification — `arize-ai.github.io/openinference/spec/`
- Langfuse Observability — `langfuse.com/docs/observability/overview`
- Google ADK Evaluation — `adk.dev/evaluate/`
- UK AI Security Institute Inspect — `inspect.aisi.org.uk`
- OWASP Top 10 for Agentic Applications 2026 — `genai.owasp.org`
- LiteLLM — `docs.litellm.ai`
- Envoy AI Gateway — `aigateway.envoyproxy.io/docs/`

---

## Appendix A：最小 Run Record

```json
{
  "schema_version": "ahra/run/0.1",
  "run_id": "RUN-01J...",
  "task_id": "TASK-0001",
  "context_id": "CTX-doc-health",
  "attempt": 1,
  "agent_release": "repository-maintainer@sha256:...",
  "workflow_definition": "WFDEF-maintain-repo@sha256:...",
  "workflow_execution_id": "WFEX-01J...",
  "session_id": "SES-01J...",
  "status": "running",
  "status_version": 4,
  "lease": {
    "holder": "workload:worker-17",
    "fencing_token": 12,
    "heartbeat_at": "2026-06-21T00:14:00Z",
    "expires_at": "2026-06-21T00:20:00Z"
  },
  "runtime_profile": "local-worktree@sha256:...",
  "workspace_ref": "workspace://TASK-0001/RUN-01J...",
  "context_manifest_ref": "artifact://CTXMAN-...",
  "budgets": {
    "max_cost_usd": 12.0,
    "max_model_calls": 80,
    "max_tool_calls": 200,
    "deadline": "2026-06-21T00:40:00Z"
  },
  "usage": {
    "cost_usd": 1.37,
    "model_calls": 9,
    "tool_calls": 14
  },
  "checkpoint_ref": "checkpoint://CHK-...",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "created_at": "2026-06-21T00:10:00Z",
  "updated_at": "2026-06-21T00:14:00Z"
}
```

## Appendix B：最小内部 Port 依赖方向

```text
Domain contracts
      ↑
Application services
      ↑
Ports (Protocols/Interfaces)
      ↑
Adapters (DB, model, MCP, runtime, workflow, UI)
```

领域层不得 import 某个 Agent SDK、云 SDK、数据库 ORM 或队列客户端。Adapter 可以依赖领域层，领域层不能反向依赖 Adapter。
