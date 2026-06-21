# Contract Compatibility

- Schema `$id` 和 `schema_version` 是兼容性权威。
- 消费者可忽略未知 optional 字段。
- 枚举新增值需要消费者有 unknown/fail-closed 策略。
- 破坏性变化发布新的 major schema 路径。
- 事件 type 使用 `dev.ahra.<domain>.<event>.vN`。
