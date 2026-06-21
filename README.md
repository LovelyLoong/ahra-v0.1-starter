# AHRA v0.1 Starter

这是 **Agent Harness Reference Architecture（AHRA）v0.1** 的可运行参考骨架。它把现有 AWKP 作为治理与工作知识 Profile，并提供 Harness 核心领域对象、JSON Schema、Ports、内存参考实现、状态转换、Context Manifest、策略示例和契约测试。

## 边界

- `profiles/awkp/`：Task、长期知识、Artifact、Evidence、Handoff。
- `src/ahra/domain.py`：Run、Memory、Context、Tool、Policy 等领域对象。
- `src/ahra/ports.py`：外部系统适配端口。
- `src/ahra/orchestrator.py`：带 CAS 和 lease/fencing token 的单机 Run Service。
- `src/ahra/memory.py`：候选→生效的受治理 Memory 参考实现。
- `src/ahra/context.py`：确定性 Context Builder 与内容摘要。
- `src/ahra/policy.py`：风险分级的参考 Policy Engine。
- `contracts/schemas/`：跨语言契约。

这个 Starter **不是生产级分布式编排器**。它用于先冻结领域契约；生产部署应通过 Ports 接 Postgres、Durable Workflow Engine、对象存储、MCP、A2A、Model Gateway、隔离 Runtime 和 OTel。

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

## 第一条实施规则

不要从“做一个多 Agent 对话循环”开始。先确保：

1. Task、Run、Session、Checkpoint、Memory、Artifact 各有唯一权威；
2. Tool 副作用经过 Policy 和 Approval；
3. Runtime 可隔离、取消和回收；
4. 每次 Run 能生成 Context Manifest、Trace、Artifact 与 Evidence；
5. 故障后从 Checkpoint 恢复，而不是重新猜测状态。
