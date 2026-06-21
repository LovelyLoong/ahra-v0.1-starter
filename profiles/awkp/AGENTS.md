# Agent Entry Map

## Mission

在不降低验收条件、不破坏权威状态和审计链的前提下，完成当前任务的一个可验证增量。

## Read order

1. 当前任务的 `task.md` 与 `state.json`。
2. `WORKFLOW.md` 中的状态、租约、验证和权限规则。
3. 任务 `input_refs` 链接的 `docs/` 概念。
4. 仅加载当前工作所需的 `skills/<name>/SKILL.md`。
5. 查看相关 Git 历史并运行最小基线检查。

## Non-negotiable rules

- `task.md` 是目标/验收契约；未经批准不得降低或删除验收条件。
- `state.json` 只能由 Harness 或当前租约持有者以 CAS 更新。
- `events.jsonl` 只追加，严禁改写历史。
- 不在聊天中“交付”正式结果；发布 Artifact、Evidence 和 Manifest。
- 不自行把高风险任务直接标记为 completed；先进入 review。
- 不写入密钥、令牌、个人敏感信息或私有思维链。
- 不直接在共享主分支工作；每任务使用隔离分支/worktree。
- 会话结束前提交可恢复增量、更新 next_action，并在需要时写 Handoff。

## Project map

- Harness policy: `WORKFLOW.md`
- Full profile: `SPEC.md`
- Durable knowledge: `docs/index.md`
- Live work: `work/index.md`
- Schemas: `schemas/`
- Reusable procedures: `skills/`
- Validation: `python3 scripts/lint_awkp.py`

## Completion

完成必须同时具备：验收证据、可追溯 Artifact、必要文档更新、风险等级要求的审批，以及 verifier/Harness 的终态写入。
