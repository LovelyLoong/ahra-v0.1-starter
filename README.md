# AHRA v0.1 Starter

这是 **Agent Harness Reference Architecture（AHRA）v0.1** 的模板项目。它把 **AWKP v0.1** 作为根目录的一等治理层，而不是嵌套 profile；AHRA 的外围 Harness 架构、契约、端口和参考核心与 AWKP 的任务、知识、产物、证据规则并列存在。

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

这个 Starter **不是生产级分布式编排器**，也不包含完整 WorkflowRunner。它用于先冻结模板外壳、对象边界、治理规则和跨语言契约；生产部署应通过 Ports 接 Postgres、Durable Workflow Engine、对象存储、MCP、A2A、Model Gateway、隔离 Runtime 和 OTel。

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

## 模板使用

1. 保留 `AGENTS.md`、`SPEC.md`、`WORKFLOW.md` 的根入口语义。
2. 用 `work/tasks/TASK-0001/` 复制出项目任务模板。
3. 把项目长期知识写入 `docs/`，不要把完整聊天记录当作知识库。
4. 新增 Harness 能力时先改 `contracts/schemas/` 与 `src/ahra/ports.py`。
5. 不要从“做一个多 Agent 对话循环”开始；先确保：

   - Task、Run、Session、Checkpoint、Memory、Artifact 各有唯一权威；
   - Tool 副作用经过 Policy 和 Approval；
   - Runtime 可隔离、取消和回收；
   - 每次 Run 能生成 Context Manifest、Trace、Artifact 与 Evidence；
   - 故障后从 Checkpoint 恢复，而不是重新猜测状态。
