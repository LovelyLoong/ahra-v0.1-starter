# 最小威胁模型

必须为每个新 Adapter 评估：

- Prompt injection / goal hijacking；
- tool misuse 与非幂等重放；
- 身份、权限、跨租户和 token passthrough；
- memory poisoning、过期事实和删除语义；
- 不可信 MCP/A2A/网页/文件内容；
- Runtime 逃逸、网络横移、宿主挂载和 Secret 泄露；
- fan-out、循环、成本和资源耗尽；
- Trace、Artifact、Memory 与 Snapshot 的敏感数据。

模型输出是 intent，不是授权。每个副作用 Enforcement Point 必须独立执行 Policy。
