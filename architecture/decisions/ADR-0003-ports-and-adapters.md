# ADR-0003：核心采用 Ports and Adapters

- 状态：accepted
- 日期：2026-06-21

## 决策

领域层不依赖模型厂商、Agent SDK、云、数据库、MCP SDK、队列或 Runtime 产品。外部能力实现 `src/ahra/ports.py` 的协议。

## 原因

框架和协议仍在快速演进；稳定的是 Task、Run、Memory、Tool、Policy 和 Artifact 的领域语义。
