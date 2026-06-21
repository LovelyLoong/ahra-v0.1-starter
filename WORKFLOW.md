# Harness Development Workflow

## 变更顺序

1. 修改或新增 `contracts/schemas/`。
2. 更新 `architecture/SPEC.md` 或 ADR，说明兼容性。
3. 更新领域对象和 Port。
4. 更新 Adapter/参考实现。
5. 增加契约、状态恢复和安全测试。
6. 运行 `make check`。

## 兼容规则

- 新增 optional 字段：允许同一 minor profile。
- 改变字段含义、删除字段或收紧枚举：必须新 schema version。
- 事件消费者必须忽略未知扩展字段，但不得忽略未知事件 major version。
- Release、Tool、Runtime 和 Workflow 必须以 digest 或不可变版本运行。

## 完成门禁

- Schema 示例通过验证；
- 合法与非法状态转换均有测试；
- 重试、重复事件和 lease 过期路径有测试；
- 高风险 Tool 无 Approval 时被拒绝；
- Memory 不能未经晋升直接成为 active；
- Context Manifest 对同一输入生成相同摘要；
- 未引入领域层对具体云、模型或 Agent SDK 的依赖。
