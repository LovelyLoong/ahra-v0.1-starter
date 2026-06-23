# Local Profile

建议：SQLite、本地 Artifact 目录、进程内/DB Queue、local process runner、run-owned Git worktree、OTel Console。

Local Profile 必须保持与 Team/Scale 相同的领域 Schema。它可以牺牲高可用，但不能省略 CAS、lease、idempotency、Policy、Approval 和 Audit 语义。
