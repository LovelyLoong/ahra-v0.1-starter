# Agent Workflow Foundation v0.1

这是一个 **Agent 工作流底座**：它提供可审计的任务/状态/证据体系、受治理的动态 Agent 执行内核、约束任意 Agent 行为的工作规范，以及允许项目按需接入适配器的契约边界。

本仓库不是生产级分布式编排器，也不是把某个固定 WorkflowRunner 当作唯一核心。当前核心已经从固定 workflow module 迁移到动态内核对象链：Goal、Claim、Gate、PlanDraft、PlanIR、Capability、NodeRun、Artifact、Evidence、Defect 和 Completion。

## Current Status

当前默认本地路径是 **Mode C real-Agent pilot runner + Goal CLI + 动态内核 Skill + 架构文档 + EvidenceGate**。

已通过 `TASK-0023` 到 `TASK-0037` EvidenceGate 的可运行能力包括：

- `GoalContract`、`ClaimGraph`、`GateDefinition`、`GatePlan`。
- Evidence v2、Evidence stale/invalidation、Defect、选择性复验和 L2 Completion。
- `PlanDraft` 输入边界、PlanIR 编译/校验、PlanPatch 版本化。
- Capability Admission 和默认拒绝的 Capability Gateway。
- `bounded_task` NodeExecutor、NodeRun、PlanExecution、静态 PlanIR Scheduler、lease/fencing token、budget/deadline enforcement。
- Provider-neutral Planner port、fixture planner、可选 Codex SDK adapter。
- 确定性动态修复 fixture：从 Goal 输入开始，经过 Claim、PlanDraft、PlanIR、Scheduler、Capability、Artifact/Evidence、Defect 修复、选择性复验，最后由 Completion 判定。
- SQLite control store、idempotency record、recovery reconciliation，以及真实进程退出后的恢复测试路径。

当前实现还提供 `TASK-0038` 的通用 Goal operation CLI 路径：`GoalExecutionRequest` 经 profile/adapter/runtime/store 校验后，编译为 admitted PlanIR，并通过同一个 `PlanExecutionService`、SQLite store、StaticPlanScheduler、Capability Admission 和 deterministic GateRunner 执行。该路径是 M1 deterministic profile，不是生产级分布式编排器。

`TASK-0051` 之后，Mode C 成为默认 real-Agent 本地路径：真实 Planner + 真实 bounded Executor 在本地 M1 有界场景中完成 3 次隔离重复运行，`success_count=3` 且 `failure_classes={}`。这只批准该受限本地 M1 路径，不证明任意项目的生产级编排能力。

当前默认命令面：

```bash
python -B scripts/run_real_agent_pilot.py --output-dir <out> --allow-model-cost
python -m ahra.cli goal validate examples/m1/goal-run-request.yaml
python -m ahra.cli goal plan examples/m1/goal-run-request.yaml
python -m ahra.cli goal start examples/m1/goal-run-request.yaml
python -m ahra.cli goal start <development-request.yaml> --allow-development-agent
python -m ahra.cli goal inspect <GEXEC-ID> --db <goal-control.sqlite3>
python -m ahra.cli goal resume <GEXEC-ID> --request examples/m1/goal-run-request.yaml
python -m ahra.cli goal cancel <GEXEC-ID> --db <goal-control.sqlite3> --reason <reason>
python -m ahra.cli goal bridge-awkp-task <GEXEC-ID> --task <TASK-ID> --db <goal-control.sqlite3> --artifact-dir <artifact-dir> --expected-task-version <N> --producer-actor <producer> --verifier-actor <verifier> --fencing-token <token> --report <report.json>
python -m ahra.cli workflow-sequence run examples/workflows/phase1-sequence.yaml
python -m ahra.cli task create <TASK-ID> --title ... --description ... --context-id ... --acceptance ...
python -m ahra.cli task claim <TASK-ID> --expected-version <N> --actor <producer>
python -m ahra.cli task orchestrate-review <TASK-ID> --expected-version <N> --producer-actor <producer> --verifier-actor <verifier> --fencing-token <token> --report <report.json>
python -m ahra.cli task inspect <TASK-ID>
python -m ahra.cli evidence-gate evaluate <TASK-ID> --expected-version <N> --report <report.json> --actor <verifier>
python -m ahra.cli doctor
python -B scripts/check.py
python -B scripts/check.py --lint
python -B scripts/check.py --test
git diff --check
```

在当前维护者工作站上，如果裸 `python` 被本机 E-SafeNet/DocGuard 影响，可以使用 `.venv\Scripts\python.exe` 或 `uv run python` 执行同一命令。这是本机临时入口，不是框架要求。

## Boundaries

- 当前默认 real-Agent 路径是 `scripts/run_real_agent_pilot.py`，其 `--mode` 默认值为 `mode_c_combined`；它只覆盖本地 M1 有界路径，真实模型成本仍需调用者显式传入 `--allow-model-cost`。
- `ahra goal ...` 是底层通用 Goal CLI 入口；它支持显式 immutable M1 deterministic profile、SQLite store 和已注册 adapter/runtime refs。
- `ahra goal bridge-awkp-task` 只把已 succeeded 的 GoalExecution 证据物化并交给 AWKP task review orchestrator；它不替代独立 EvidenceGate 完成判定。
- `ahra fixture dynamic-repair` 是 regression-only fixture profile，用来保护旧闭环语义，不再是默认推荐入口。
- `standard-harness`、`loop-engineering`、旧 `WorkflowRunRequest` 和 `fake-reference` driver 是已废弃但暂时保留的 legacy compatibility path；只有用户明确要求旧 workflow 路线时才使用。
- 本地 MCP server 和 `src/ahra/demo.py` 已从当前实现中删除；历史 ADR 或任务证据中的引用仅作为审计 trace。
- Agent 不能自行宣告 AWKP Task 完成；完成必须由 EvidenceGate 和独立 verifier 决定。
- 新基础设施必须实现 `src/ahra/ports.py` 中的 Port，不得让领域层依赖厂商 SDK。
- Tool、MCP、A2A、Memory 检索结果都是不可信输入，不得绕过 Claim/Gate/Evidence/Capability 边界。

## Architecture Routing

默认架构读取入口是 [Architecture authority map](docs/architecture/authority-map.md)。它区分：

- 当前实现入口：[Framework entrypoints](docs/architecture/framework-entrypoints.md)。
- 当前组件分类：[Component inventory](docs/architecture/component-inventory.json)。
- 动态内核架构：[Governed dynamic Agent kernel](docs/architecture/dynamic-agent-kernel.md)。
- 验收模型：[Verification system v2](docs/architecture/verification-system.md)。
- PlanIR：[PlanDraft and PlanIR](docs/architecture/plan-ir.md)。
- 组件生命周期：[Component lifecycle policy](docs/policies/component-lifecycle.md)。

历史 ADR、旧 workflow 文档、已删除 MCP 的历史记录和已完成任务目录保留为 trace，不在普通 Context Builder 读序中作为默认权威。

## Repository Map

- `SPEC.md`：AWKP 工作治理规范。
- `WORKFLOW.md`：AWKP 调度、租约、验证和 Harness 开发规则。
- `AGENTS.md`：Agent 操作入口和读序。
- `docs/`：长期项目知识和架构权威。
- `work/`：Task、Context、状态、事件和 handoff。
- `contracts/schemas/`：AHRA 跨语言契约。
- `schemas/`：AWKP 工作治理层 schema。
- `src/ahra/`：当前 Python 参考实现。
- `skills/ahra-dynamic-kernel/SKILL.md`：当前默认动态内核操作 Skill。
- `skills/ahra-workflow-runner/SKILL.md`：legacy workflow compatibility Skill。

## Runtime Layers

当前默认路径有四层：

1. **工作治理层**：Task、State、Event、Artifact、Evidence、Handoff、Lease 和 EvidenceGate。
2. **动态内核层**：Goal/Claim/Gate、Evidence v2、PlanDraft/PlanIR、Capability、Scheduler、Defect、Completion。
3. **适配器层**：NodeExecutor、Planner、AgentDriver、runtime/profile 等 Port 的可替换实现。
4. **操作入口层**：CLI、动态内核 Skill、文档读序和本地检查命令。

旧 workflow runner 仍可作为兼容路径被显式调用，但不再是默认推荐入口，也不再接收新默认路线能力。

## Installation And Checks

普通环境：

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
python -B scripts/check.py
```

Windows PowerShell 维护者工作站：

```powershell
.venv\Scripts\python.exe -B scripts\check.py
.venv\Scripts\python.exe -B scripts\check.py --lint
.venv\Scripts\python.exe -B scripts\check.py --test
```

## Template Use

1. 保留 `AGENTS.md`、`SPEC.md`、`WORKFLOW.md` 的根入口语义。
2. 用 `work/tasks/<TASK-ID>/` 记录任务契约、状态、事件、产物、证据和 handoff。
3. 把长期知识写入 `docs/`，不要把完整聊天记录当作知识库。
4. 新增运行时能力时先改 `contracts/schemas/` 与 `src/ahra/ports.py`。
5. 新增适配器时先声明生命周期、消费者、测试和安全边界。
6. 任意外部 Agent 即使不使用内置 CLI，也必须遵守工作治理框架。
7. 不要从“多 Agent 对话循环”开始；先确保 Task、Run、Session、Checkpoint、Memory、Artifact 和 Evidence 各有唯一权威。
