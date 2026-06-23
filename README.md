# Agent Workflow Foundation v0.1

这是一个 **Agent 工作流底座**：它同时提供可执行的标准 Agent 工作流、约束任意 Agent 行为的工作规范、可审计的任务/状态/证据体系，以及允许项目按需扩展的工作流模块和项目规范。

本仓库不是只给具体项目外围套一层 Harness 的模板。它本身就是一套完整的 Agent 工作系统：工作规范定义所有 Agent 必须遵守的边界，标准 workflow modules 提供推荐执行路径，项目可以在此基础上适配自己的文档、Skill、命令、检查项和领域规则。

具体工作流不是写死在核心里，而是以可插拔 workflow module 的方式接入。`E:\harness-first-starter` 是当前 reference workflow 的实现来源，迁入本仓库时必须通过 AHRA Port、Run、Artifact、Evidence、Policy 和 Approval 契约隔离。

更高阶的使用者可以在稳定契约之上自定义或组合自己的工作流模块。外部 Agent 可以不使用内置 workflow，但只要它写入任务状态、产物、证据或完成结论，就必须遵守本框架的工作规范。

## 边界

- `SPEC.md`：AWKP 完整规范。
- `WORKFLOW.md`：AWKP 调度、租约、验证和 Harness 开发规则。
- `docs/`：长期项目知识。
- `work/`：Task、Context、状态、事件和 Handoff。
- `artifacts/`、`evidence/`、`sources/`：正式产物、证据和来源。
- `schemas/`：AWKP 工作治理层 Schema。
- `architecture/SPEC.md`：AHRA 外围 Harness 架构。
- `contracts/schemas/`：AHRA 跨语言 Harness 契约。
- `src/ahra/domain.py`：Run、Memory、Context、Tool、Policy 等领域对象。
- `src/ahra/ports.py`：外部系统适配端口。
- `src/ahra/orchestrator.py`：带 CAS 和 lease/fencing token 的单机 Run Service。
- `src/ahra/memory.py`：候选→生效的受治理 Memory 参考实现。
- `src/ahra/context.py`：确定性 Context Builder 与内容摘要。
- `src/ahra/policy.py`：风险分级的参考 Policy Engine。
- `docs/architecture/agent-workflow-foundation.md`：项目定位、使用模式和未来发展方向。
- `architecture/decisions/ADR-0004-pluggable-workflow-modules.md`：主仓库与可插拔工作流模块边界。

这个项目 **不是生产级分布式编排器**，也不把某一个 WorkflowRunner 当作唯一核心。它先冻结 Agent 项目底座的对象边界、治理规则、工作流契约、适配端口和证据门禁；生产部署应通过 Ports 接 Postgres、Durable Workflow Engine、对象存储、A2A、Model Gateway、隔离 Runtime 和 OTel。

当前默认使用入口是 **CLI + 本地 Skill + 文档**。MCP 不再作为默认路线；CLI 只封装稳定 Python API，不拥有新的工作流逻辑。

## Workflow Foundation

本项目有五个层次：

1. **工作规范框架**：Task、Run、State、Event、Artifact、Evidence、Handoff、Lease 和完成门禁。
2. **标准工作流**：`standard-harness` 与 `loop-engineering` 等内置 workflow modules。
3. **项目适配**：具体项目通过本地 docs、Skills、命令、检查项和策略接入。
4. **自定义工作流**：高级使用者可以在模块契约之上组合或实现专属 workflow。
5. **操作入口**：当前是 CLI + Skill + 文档。

当前规划的内置标准模块包括：

1. `standard-harness`：一个有边界任务的标准 Harness 工作流。职责包括隔离工作区、路径/规模策略、确定性检查、独立 Reviewer、有界重试、Artifact/Evidence 捕获和回滚。
2. `loop-engineering`：目标级 Loop Engineering 工作流。职责是在 `standard-harness` 任务之上做目标队列、全局验证、目标 Reviewer、有限动态规划和默认人工批准计划。

后续新增模块或扩展模块必须先登记模块契约：用途、输入、输出、状态映射、依赖端口、安全门禁、Artifact/Evidence 产物和测试。模块可以复用或扩展已有模块，但不得绕过 AHRA 的 Task/Run/Session/Checkpoint/Memory/Artifact/Evidence/Approval 边界。

## Agent drivers and workflow invocation

Workflow module 和 Agent 执行器是两个不同边界。`standard-harness` 和
`loop-engineering` 只依赖 Agent-neutral driver port，不绑定 Codex、Claude
Code、OpenAI Agents SDK、LangGraph、开源 Agent 框架或直接 LLM API。

开发者或外部 Agent 启动工作流时应先形成 `WorkflowRunRequest`，其中声明
`moduleId`、输入引用、`workspaceRef`、`driverRef`、`storeRef` 和
`approvalMode`。`driverRef` 由 registry 解析到具体 driver adapter。Codex 只
能作为一个 adapter 示例，不能成为 AHRA core 的特殊路径。

## 运行

```bash
make check
make demo
```

或：

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest -q
python -m ahra.demo
```

## 操作入口

当前模板优先使用：

1. `AGENTS.md` 和本地 `skills/*/SKILL.md` 作为 Agent 操作入口。
2. `docs/architecture/framework-entrypoints.md` 作为入口路线权威文档。
3. `uv run ahra workflow validate/start/inspect/resume` 操作 workflow。
4. `uv run ahra task inspect` 和 `uv run ahra evidence-gate evaluate` 操作
   AWKP 任务检查与完成门禁。
5. `uv run ahra doctor`、`scripts/check.py`、`scripts/lint_awkp.py` 和
   `git diff --check` 作为本地验证命令。

MCP 代码路径如果存在，也只作为旧的可选适配器，不作为默认使用前提。

## 模板使用

1. 保留 `AGENTS.md`、`SPEC.md`、`WORKFLOW.md` 的根入口语义。
2. 用 `work/tasks/TASK-0001/` 复制出项目任务模板。
3. 把项目长期知识写入 `docs/`，不要把完整聊天记录当作知识库。
4. 新增 Harness 能力时先改 `contracts/schemas/` 与 `src/ahra/ports.py`。
5. 新增或迁移 workflow module 时先写 ADR/模块契约，再迁移代码。
6. 任意外部 Agent 即使不使用内置 workflow，也必须遵守工作规范框架。
7. 不要从“做一个多 Agent 对话循环”开始；先确保：

   - Task、Run、Session、Checkpoint、Memory、Artifact 各有唯一权威；
   - Tool 副作用经过 Policy 和 Approval；
   - Runtime 可隔离、取消和回收；
   - 每次 Run 能生成 Context Manifest、Trace、Artifact 与 Evidence；
   - 故障后从 Checkpoint 恢复，而不是重新猜测状态。
