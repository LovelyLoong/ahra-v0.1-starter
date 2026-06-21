# Agent Workflow Knowledge Profile（AWKP）v0.1

> **状态：建议稿（Proposed Profile），2026-06-21。** 这不是 Google、A2A 项目或 Linux Foundation 发布的官方标准，而是一套面向外部 Agent Harness 的工程应用剖面：以 OKF v0.1 Draft 为知识格式，以 A2A 1.0 的任务语义为互操作基线，并补齐长期工程所需的状态权威、并发控制、交接、验证、人工治理和审计规则。

## 0. 结论

大型、长期、多 Agent 项目不应依赖一个不断膨胀的 `AGENTS.md`、一个共享 `status.md` 或聊天记录。推荐采用以下组合：

1. **入口与宪法层**：短小的 `AGENTS.md` + 可版本化的 `WORKFLOW.md`。
2. **工作状态层**：严格结构化的 `state.json` + 只追加的 `events.jsonl`，由 Harness 以租约和 CAS 管理。
3. **长期知识层**：符合 OKF 形态的 Markdown + YAML frontmatter，一概念一文件，Git 审核与追踪。
4. **产物与证据层**：产物不可变、内容寻址、带哈希；“完成”必须关联验收证据。
5. **能力与连接层**：Agent Skills 保存可复用流程；MCP 接工具/资源；A2A 用于跨进程 Agent 通信。

最重要的规则是：**每一类事实只能有一个权威源；高频机器状态与低频人类知识必须分离。**

---

## 1. 适用范围与非目标

### 1.1 适用范围

AWKP 适用于：

- 模型本身没有可靠多 Agent 通信或长期记忆能力；
- Harness 在外部负责任务派发、重试、并发、恢复和人类介入；
- 项目跨多次上下文窗口、多个 Agent、多个工作区与多个月份；
- 人类需要随时检查目标、状态、证据、决策和责任归属；
- Agent 需要低成本、渐进式读取上下文，而不是每次扫描全库。

### 1.2 非目标

AWKP 不规定特定模型、编排框架、Issue Tracker、向量数据库、对象存储或消息中间件；也不要求暴露 Agent 的私有思维链。它规范的是**可观察工作事实、可验证产物和可维护知识**。

---

## 2. 规范性术语

本文中的 **必须（MUST）**、**不得（MUST NOT）**、**应当（SHOULD）**、**不应（SHOULD NOT）**、**可以（MAY）**按 RFC 2119 风格理解。

- **Harness**：模型外部的编排、状态、权限、工具、工作区和恢复系统。
- **Task Contract**：任务目标、范围、验收条件与输出契约；不等同于运行时状态。
- **State Snapshot**：任务当前机器状态的结构化快照。
- **Event Ledger**：只追加、不可原地修改的状态与审计事件流。
- **Artifact**：任务输出；例如代码提交、补丁、报告、数据集或构建结果。
- **Evidence**：证明验收条件被满足或未满足的可复核记录。
- **Knowledge Concept**：长期有效的一项知识，以一个 OKF 风格 Markdown 文件表示。
- **Handoff**：供下一 Agent 或人类在新上下文中恢复工作的紧凑交接包。
- **Materialized View**：从权威状态生成的索引、看板或摘要，不是新的事实源。

---

## 3. 标准组合与职责边界

| 层 | 推荐约定/标准 | 负责 | 不负责 |
|---|---|---|---|
| 长期知识 | OKF v0.1 Draft | Markdown/YAML、概念、索引、引用、可移植知识包 | 任务锁、并发、审批、重试 |
| Agent 间通信 | A2A 1.0 | Agent Card、Message、Task、Artifact、状态更新 | 项目长期知识治理、产物版本策略 |
| Agent 入口 | AGENTS.md | 可预测的项目入口、局部指令与优先级 | 当百科全书或运行时状态库 |
| Harness 策略 | WORKFLOW.md（本剖面） | 调度、租约、重试、审批、验证、写入权限 | 业务知识正文 |
| 工具/资源连接 | MCP | Agent 与工具、数据、资源间的上下文交换 | Agent 间任务状态与长期记忆 |
| 可复用程序知识 | Agent Skills | 按需加载的说明、脚本、参考资料 | 项目当前任务状态 |
| 审计与协作 | Git/PR/CI | 版本、差异、归因、门禁、回滚 | 高频分布式锁本身 |

### 3.1 推荐的四类权威事实

任何实现都必须在 `WORKFLOW.md` 中明确以下权威源：

| 事实类别 | 权威源 | 典型内容 |
|---|---|---|
| 运行时工作状态 | Tracker/DB；文件模式下为 `state.json` | 当前状态、负责人、租约、下一动作、阻塞 |
| 审计历史 | 追加式 Event Store；文件模式下为 `events.jsonl` | 谁在何时因何理由改变了什么 |
| 长期项目知识 | Git 中的 OKF 风格 Markdown | 架构、决策、术语、规范、运行手册 |
| 交付物与证据 | Git commit/对象存储/制品库 + Manifest | 产物 URI、哈希、来源、测试与审批 |

**不得**让 Issue Tracker、任务 Markdown、聊天和看板同时声称自己是同一状态的权威源。非权威副本必须标注为生成视图，并可被重建。

---

## 4. 推荐目录

```text
repo/
├── AGENTS.md                         # ≤约 120 行；只做入口地图和不可违反的规则
├── WORKFLOW.md                       # Harness 的版本化运行策略
├── README.md                         # 面向人类的项目入口
├── docs/                             # 长期知识层（OKF 风格）
│   ├── index.md                      # 生成或半生成的渐进式目录
│   ├── architecture/
│   ├── product/
│   ├── decisions/                    # ADR/决策，废止时保留并标 superseded
│   ├── runbooks/
│   ├── policies/
│   ├── glossary/
│   ├── risks/
│   └── log.md                        # 人类可读更新史，不是任务状态账本
├── work/                             # 工作态；可映射到外部 Tracker/DB
│   ├── index.md                      # 生成视图
│   ├── contexts/
│   └── tasks/TASK-xxxx/
│       ├── task.md                   # 目标/范围/验收契约
│       ├── state.json                # 当前机器状态；Harness 权威写入
│       ├── events.jsonl              # 只追加事件；严禁改写历史
│       ├── handoffs/                 # 不可变交接记录
│       └── artifact-manifest.json    # 产物、证据和哈希索引
├── sources/                          # 原始来源清单或不可变来源；Agent 不得改写原文
├── evidence/                         # 可复核测试、评估、截图、基准等
├── artifacts/                        # 可选；大制品通常只存 Manifest/URI/哈希
├── skills/                           # Agent Skills；按需加载的程序知识
├── schemas/                          # JSON Schema、状态机和扩展版本
└── scripts/                          # lint、索引生成、对账、陈旧性检查
```

### 4.1 分层写入权限

- `AGENTS.md`、`WORKFLOW.md`、`docs/policies/`：受保护；实质修改必须经指定人类或代码所有者批准。
- `task.md`：创建后视为任务契约；Agent 不得自行降低验收条件。范围变化必须产生 `scope_changed` 事件并经授权者批准。
- `state.json`：只有 Harness 或获得当前租约的执行器可经 CAS 更新。
- `events.jsonl`：只追加；不得删除、重排或修改既有事件。纠错使用补偿事件。
- `handoffs/`、Manifest、证据：一经发布不可原地覆盖；新版本使用新 ID，并通过 `supersedes` 关联。
- `docs/`：通过分支/PR 更新；不得多个 Agent 在主分支同时原地编辑同一概念。

---

## 5. 文档数据模型

### 5.1 长期知识概念

每个长期知识文件必须是 UTF-8 Markdown，并至少包含以下 frontmatter：

```yaml
---
type: Architecture                 # OKF 要求的类型
id: ARCH-auth-boundary             # 稳定 ID；重命名路径时仍能追踪
schema_version: awkp/0.1
title: Authentication trust boundary
description: 一句话说明本文件回答什么问题。
status: active                     # draft | active | deprecated | superseded
owner: team:platform
source_refs:                       # 原始依据；可为文件、commit、URL 或证据 ID
  - SRC-0042
evidence_refs:
  - EVD-0198
confidence: verified               # unverified | inferred | reviewed | verified
last_verified_at: 2026-06-21T00:00:00Z
review_after: 2026-09-21T00:00:00Z
supersedes: []
tags: [architecture, security]
---
```

正文应使用可预测章节；不是每种类型都要求全部章节：

```markdown
# 摘要
# 适用范围
# 事实与约束
# 决策或规则
# 依据与证据
# 例外与已知限制
# 相关概念
# 变更说明
```

规范要求：

1. 一个概念一个文件；不要在五个文档复制同一规则。
2. 先写摘要和结论，再写细节；描述字段必须能用于索引与路由。
3. 事实、推断、决策、假设和未验证说法必须可区分。
4. 关键主张必须有 `source_refs` 或 `evidence_refs`；无依据时标 `confidence: unverified|inferred`。
5. 废止内容不得静默删除；标记 `deprecated/superseded` 并链接替代项。
6. 文件过长时按概念拆分；入口文件只做导航。建议普通概念控制在约 400 行以内。
7. 不得把密钥、令牌或隐私数据写入文档；只保存秘密管理器中的引用 ID。
8. 不得保存私有思维链；保存可审计的简短理由、证据、决策和不确定性即可。

### 5.2 任务契约 `task.md`

`task.md` 负责相对稳定的“要做什么”，不得承担高频状态：

```yaml
---
type: WorkItem
id: TASK-0001
schema_version: awkp/0.1
title: 为文档索引增加陈旧性检查
description: 在 CI 中检测超过 review_after 的活动文档。
context_id: CTX-doc-health
priority: P1
risk_level: R1
requester: human:alice
reviewer: team:platform
created_at: 2026-06-21T00:00:00Z
depends_on: []
input_refs:
  - ../../../../docs/policies/document-governance.md
output_contract:
  - kind: code_change
  - kind: verification_report
---

# 目标

# 范围

# 非目标

# 约束

# 验收条件
- [ ] 在固定时钟测试下能确定性识别过期文档。
- [ ] 不修改原始文档内容。
- [ ] CI 失败信息给出文件、owner 和 review_after。

# 验证方法

# 风险与人工门禁
```

验收条件必须具体、可判断，最好可由测试、查询、基准或人工检查表验证。诸如“做得更好”“尽量完善”不得作为唯一验收条件。

### 5.3 当前状态 `state.json`

`state.json` 是高频机器状态；建议使用 JSON 而非自由文本：

```json
{
  "schema_version": "awkp/0.1",
  "task_id": "TASK-0001",
  "context_id": "CTX-doc-health",
  "state": "working",
  "state_version": 4,
  "owner": "agent:implementer-07",
  "attempt": 1,
  "lease": {
    "holder": "agent:implementer-07",
    "acquired_at": "2026-06-21T00:10:00Z",
    "heartbeat_at": "2026-06-21T00:14:00Z",
    "expires_at": "2026-06-21T00:20:00Z"
  },
  "next_action": "实现并运行过期文档的固定时钟测试",
  "pause_reason": null,
  "blockers": [],
  "artifact_refs": [],
  "evidence_refs": [],
  "updated_at": "2026-06-21T00:14:00Z"
}
```

更新必须携带期望的 `state_version`。不匹配时更新失败，执行器必须重新读取并对账；不得盲写覆盖。

### 5.4 追加式事件 `events.jsonl`

每行一个完整 JSON 对象：

```json
{"schema_version":"awkp/0.1","event_id":"EVT-000001","idempotency_key":"TASK-0001:create","task_id":"TASK-0001","context_id":"CTX-doc-health","event_type":"task_created","actor":"human:alice","occurred_at":"2026-06-21T00:00:00Z","causation_id":null,"correlation_id":"CTX-doc-health","from_state":null,"to_state":"ready","reason":"批准进入执行队列","refs":["task.md"]}
{"schema_version":"awkp/0.1","event_id":"EVT-000002","idempotency_key":"run-123:lease-1","task_id":"TASK-0001","context_id":"CTX-doc-health","event_type":"lease_acquired","actor":"harness:dispatcher","occurred_at":"2026-06-21T00:10:00Z","causation_id":"EVT-000001","correlation_id":"CTX-doc-health","from_state":"ready","to_state":"working","reason":"任务无依赖且并发额度可用","refs":[]}
```

事件必须具有唯一 `event_id` 和 `idempotency_key`。Harness 必须能从事件或外部 Tracker 重建当前状态，并检测 `state.json` 漂移。

推荐事件类型：

`task_created`、`task_ready`、`lease_acquired`、`heartbeat`、`progress_recorded`、`artifact_published`、`evidence_attached`、`blocker_added`、`blocker_cleared`、`input_requested`、`input_provided`、`scope_changed`、`handoff_created`、`review_requested`、`review_approved`、`changes_requested`、`task_completed`、`task_failed`、`task_canceled`、`task_reopened`、`knowledge_updated`。

### 5.5 Artifact Manifest

任务输出必须从聊天消息中剥离为正式 Artifact。每个 Artifact 应记录：

```json
{
  "artifact_id": "ART-0001",
  "task_id": "TASK-0001",
  "kind": "verification_report",
  "name": "doc-staleness-test-report.json",
  "uri": "git://repo@4c1d2ab/evidence/doc-staleness-test-report.json",
  "sha256": "<64 lowercase hex chars>",
  "media_type": "application/json",
  "created_by": "agent:verifier-03",
  "created_at": "2026-06-21T01:00:00Z",
  "input_refs": ["TASK-0001", "ARCH-doc-system"],
  "evidence_refs": ["EVD-0001"],
  "supersedes": null
}
```

二进制或大型制品可存外部对象库，但 Manifest、哈希、版本和访问策略必须留在可审计系统中。

### 5.6 Handoff

交接不是聊天摘要，也不是完整日志。每个 Handoff 必须是不可变的“恢复胶囊”，包含：

1. 原目标和当前状态；
2. 已完成事项及对应 Artifact/commit；
3. 已执行验证及结果；
4. 未完成事项与**唯一明确的下一动作**；
5. 阻塞项、需要谁提供什么输入；
6. 已失败方法以及失败原因；
7. 假设、不确定性和风险；
8. 触及的文件/工作区/服务；
9. 租约是否已释放；
10. 交接接收方与过期时间（如有）。

建议 Handoff 控制在约 1,500–2,500 tokens；详细日志通过引用按需读取。

---

## 6. 状态机

### 6.1 AWKP 内部状态

```text
queued -> ready -> working -> review -> completed
                    |          |  ^
                    |          v  |
                    |    changes_requested
                    |
                    +-> waiting_input ------> working
                    +-> waiting_auth -------> working
                    +-> waiting_dependency -> ready
                    +-> failed

任意非终态可在授权下 -> canceled / rejected
completed 可经明确事件 -> reopened -> ready
```

| 状态 | 含义 | 是否终态 |
|---|---|---|
| `queued` | 已记录但尚未满足调度条件 | 否 |
| `ready` | 依赖已满足、允许领取 | 否 |
| `working` | 有有效租约的执行器正在工作 | 否 |
| `waiting_input` | 缺少人类或上游输入 | 否 |
| `waiting_auth` | 缺少认证、授权或批准 | 否 |
| `waiting_dependency` | 等待其他任务/Artifact | 否 |
| `review` | 产物已提交，等待独立验证或人类评审 | 否 |
| `changes_requested` | 评审未通过，需在同一任务契约下修订 | 否 |
| `completed` | 验收通过且证据齐全 | 是 |
| `failed` | 本次任务按当前契约无法成功结束 | 是 |
| `canceled` | 经授权停止 | 是 |
| `rejected` | 在执行前或中途判定不应执行 | 是 |

### 6.2 与 A2A 1.0 的投影

| AWKP | A2A TaskState | 附加 metadata |
|---|---|---|
| queued, ready | submitted | `awkp_state`、依赖/优先级 |
| working, changes_requested | working | `awkp_state`、lease 摘要 |
| waiting_input, review | input-required | `awkp_state`、所需响应/评审人 |
| waiting_auth | auth-required | 所需 scope/批准 |
| waiting_dependency | submitted | `pause_reason=dependency` |
| completed | completed | Artifact 与 evidence refs |
| failed | failed | 错误类别、可重试性 |
| canceled | canceled | 取消主体和原因 |
| rejected | rejected | 策略依据 |

A2A 的核心状态适合互操作，但不足以表达依赖等待、独立评审和变更请求，因此这些语义必须放在版本化扩展字段中，不得伪装成自由文本约定。

### 6.3 完成门禁

Worker 不得只凭自我陈述把高风险任务直接置为 `completed`。从 `review` 到 `completed` 至少必须满足：

- 所有验收条件都有对应 Evidence；
- 必需测试/检查已运行，且记录环境和版本；
- Artifact 有稳定 ID、URI/commit 和哈希；
- 变更所影响的长期文档已更新，或明确记录“不需更新”的理由；
- 不存在未披露 blocker、失败方法或已知限制；
- 达到风险等级所要求的独立 Agent 或人类批准；
- 最终状态由 verifier、Harness 或授权人写入，而非仅由产出者自证。

---

## 7. 并发、租约与工作区

1. 每个 Task 同时最多有一个写租约持有者。只读分析可以并行，但不得竞争写 `state.json` 或同一工作区。
2. 租约必须有 TTL、heartbeat 和明确 holder；超时后由 Reconciler 回收，不由另一个 Agent直接覆盖。
3. 状态写入必须使用 CAS（`state_version`、ETag 或数据库事务）。
4. 每个 Task 使用独立分支、Git worktree、容器或沙箱；不得让多个 Agent 共享可变工作目录。
5. 共享文件的变更通过 patch/PR 合并；策略文档和热点文件应有 owner/merge queue。
6. 调度器只能派发依赖已完成且无未解决 blocker 的 Task。
7. 重试必须增加 `attempt` 并关联原 run；幂等副作用必须使用 `idempotency_key`。
8. Agent 失联、崩溃或上下文耗尽时，Harness 先冻结/回收租约，再创建 Handoff 或根据已有事件重建，不假设上一会话成功结束。
9. 索引、看板和统计应从权威数据生成，避免多个 Agent 争写同一“总状态文件”。

---

## 8. Agent 的标准读写协议

### 8.1 启动读取顺序（Progressive Disclosure）

每次新会话必须按以下顺序读取，禁止无差别扫描全库：

1. 根 `AGENTS.md`：项目地图、不可违反规则、验证入口；
2. 当前 Task 的 `task.md`、`state.json` 与最近相关事件；
3. 任务链接的架构、政策、决策和输入概念；
4. 任务所需 Skill 的 `SKILL.md`，再按需读取 references/scripts；
5. 当前工作区最近相关 Git 提交与基础健康检查；
6. 只有在证据不足时才扩展搜索范围。

Agent 在开始实质工作前必须能回答：目标是什么、完成如何判断、当前权威状态是什么、谁持有租约、下一动作是什么、不能改什么、需要运行哪些验证。

### 8.2 单次工作循环

```text
Read -> Claim -> Baseline Check -> Execute One Increment
     -> Verify -> Publish Artifact/Evidence -> Append Event
     -> CAS Update State -> Continue / Review / Handoff
```

- 一次循环聚焦一个可验证增量，不尝试“一口气完成整个大项目”。
- 在修改前运行最小基线检查，发现前序损坏时先记录并处理。
- 重要发现应立即记录为事件或知识候选，不能只留在上下文窗口。
- 会话结束前必须：提交可恢复工作、写 Evidence/Artifact、追加事件、更新 `next_action`，并在需要时生成 Handoff。

### 8.3 知识写回

只有满足至少一项时才写入长期 `docs/`：

- 发现跨任务仍然有效的事实或约束；
- 做出会影响后续工作的决策；
- 形成稳定运行手册或验证方法；
- 旧知识被证据推翻、废止或需要限定适用范围。

临时猜测、逐步调试输出、冗长聊天、运行日志应留在事件/证据系统或外部日志库，不应污染长期知识。

---

## 9. 人类参与和风险等级

| 等级 | 典型行为 | 最低门禁 |
|---|---|---|
| R0 | 只读分析、可确定性重建的生成视图 | 自动执行；保留日志 |
| R1 | 可逆的代码/文档更改、隔离环境测试 | Agent 独立验证；PR 可异步人审 |
| R2 | 生产写入、数据迁移、权限变化、外部发送、显著成本 | 行动前明确人类批准；双人/双 Agent 验证视情况启用 |
| R3 | 高影响安全、法律、财务、隐私或不可逆决策 | 人类为决策主体；Agent 只能准备分析与证据 |

人类界面至少应展示：任务目标、当前状态、owner/lease、依赖与 blocker、最新 Artifact、验收证据、风险、下一动作、待批准事项和完整 diff。人类修改必须走同一事件与版本机制，不得成为“看不见的外部口头指令”。

---

## 10. 自动化维护与 CI 门禁

### 10.1 每次提交必须检查

- Markdown frontmatter 必填字段与 schema version；
- JSON/JSONL 语法、唯一 ID、合法状态和引用完整性；
- 相对链接、孤儿概念、重复 ID；
- `review_after` 陈旧性；
- `completed` 是否有 Evidence 和 Artifact；
- Manifest 哈希与本地产物是否匹配；
- 任务状态迁移是否合法；
- `AGENTS.md` 是否仍是地图而非百科全书；
- 任务契约的验收条件是否被 Agent 未授权修改；
- 秘密、凭据和高风险数据扫描；
- 生成索引是否与源数据一致。

### 10.2 维护机器人

Doc Gardener 应定期：

- 打开 PR，而不是静默改主分支；
- 找出过期、冲突、重复、无 owner、无来源和断链文档；
- 对照代码、schema、API 或运行事实检测文档漂移；
- 压缩过长日志为可追溯摘要，但不删除权威事件；
- 更新生成索引和文档健康报告；
- 把不能确定的修改标为 review，不伪造确定性。

### 10.3 推荐维护节奏

- 每次状态变化：立即追加事件并更新快照；
- 每个可恢复增量：发布 Artifact/Evidence；
- 每次会话结束：更新下一动作并视情况 Handoff；
- 每次合并：更新受影响长期知识；
- 持续/每小时：回收陈旧租约并做 Tracker↔Event 对账；
- 每日：断链、失败重试、无 owner 任务检查；
- 每周：文档陈旧性、重复和知识候选整理；
- 每季度：schema/profile 版本、状态机和人工门禁复审。

---

## 11. 可观测性与质量指标

不要只统计“Agent 跑了多少次”。至少跟踪：

- **Handoff Recovery Time**：新 Agent 从启动到第一次有效动作的时间；
- **Reopen Rate**：完成后因缺陷重开比例；
- **Verification Pass Rate**：首次独立验证通过率；
- **Stale Knowledge Rate**：超过 `review_after` 的 active 文档比例；
- **Broken/Orphan Link Rate**；
- **Duplicate Truth Rate**：同一规则多处冲突的数量；
- **Lease Conflict / Lost Update Count**；
- **Blocked Time Ratio** 与平均等待人工响应时长；
- **Artifact Traceability**：可追溯到 Task、输入、Evidence 和提交的产物比例；
- **Context Efficiency**：启动读取 tokens 与首次有效动作/成功交付的关系；
- **Human Override Rate** 与覆盖原因；
- **Doc-to-Reality Drift Incidents**。

指标用于修复 Harness 和知识结构，不应用于诱导 Agent 草率标记完成。

---

## 12. 常见反模式

1. **一个巨型 `AGENTS.md`**：挤占上下文、快速腐烂、不可机械验证。
2. **一个共享 `status.md`**：并发覆盖、无法 CAS、状态和叙述混在一起。
3. **聊天即记忆**：消息可能丢失、不可稳定查询、关键输出未形成 Artifact。
4. **Worker 自己宣布 Done**：没有独立证据和门禁。
5. **Task 与知识混为一体**：临时调试污染长期文档，长期规则被任务日志淹没。
6. **复制而不链接**：同一事实在多个文件产生漂移。
7. **原地覆盖 Artifact/Handoff**：失去版本、归因和回滚能力。
8. **所有 Agent 共用工作区**：隐式冲突、难以判断谁改变了什么。
9. **允许 Agent 修改验收条件来通过**：目标漂移和奖励黑客。
10. **全量加载日志和 Wiki**：渐进披露失效，Agent 找不到真正约束。
11. **保存私有思维链**：既非必要审计事实，也会带来隐私、噪音和不稳定性。
12. **多权威源**：Tracker、Markdown、Dashboard 各说各话。

---

## 13. 最小落地路径

### 阶段 A：1–5 个 Agent，单仓库

- 加入短 `AGENTS.md`、`WORKFLOW.md`；
- 每任务一个目录，采用 `task.md + state.json + events.jsonl + handoffs/ + manifest`；
- Git worktree/branch 隔离；
- CI 做 schema、链接、陈旧性和完成门禁；
- 人类通过 PR 参与。

### 阶段 B：5–50 个并发 Agent

- 将运行时状态迁移到 Tracker/数据库，文件成为生成镜像；
- 增加租约服务、重试队列、Reconciler 和 Artifact Store；
- 引入独立 verifier 与风险分级审批；
- 对外提供 A2A Task/Artifact 投影。

### 阶段 C：跨团队/跨组织

- 发布 Agent Card、schema/profile version 和扩展 URI；
- 对 Artifact、身份和事件签名；
- 明确数据分级、租户、保留期与访问控制；
- 对 OKF bundle 做导入/导出与兼容性测试；
- 维护 profile 的变更日志和迁移工具。

---

## 14. 参考实现中的不可妥协项

一个系统只有同时满足以下十项，才可声称符合 AWKP Core：

1. 每类事实有且只有一个声明的权威源；
2. Task Contract 与运行时 State 分离；
3. 状态是结构化、带版本且可 CAS 的；
4. 审计事件只追加且幂等；
5. 每任务独立写租约和工作区；
6. Artifact 不靠聊天交付，且可哈希追踪；
7. 完成状态有独立 Evidence 与风险门禁；
8. 长期知识采用一概念一文件、来源、owner、复核时间和版本控制；
9. Agent 使用渐进式读取与可恢复 Handoff；
10. 人类可以通过同一状态、事件、diff 和审批机制检查与介入。

---

## 15. 资料依据

- Andrej Karpathy, **LLM Wiki**: https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
- Google Cloud, **Introducing the Open Knowledge Format**, 2026-06-12: https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing
- GoogleCloudPlatform, **Open Knowledge Format v0.1 Draft**: https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md
- A2A Project, **Agent2Agent Protocol Specification 1.0.0**: https://a2a-protocol.org/latest/specification/
- AGENTS.md open format: https://agents.md/
- Model Context Protocol, architecture: https://modelcontextprotocol.io/docs/learn/architecture
- Agent Skills specification: https://agentskills.io/specification
- OpenAI, **Harness engineering: leveraging Codex in an agent-first world**: https://openai.com/index/harness-engineering/
- OpenAI, **Symphony Service Specification Draft v1**: https://github.com/openai/symphony/blob/main/SPEC.md
- Anthropic, **Effective harnesses for long-running agents**: https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
- Anthropic, **Long-running Claude for scientific computing**: https://www.anthropic.com/research/long-running-Claude
