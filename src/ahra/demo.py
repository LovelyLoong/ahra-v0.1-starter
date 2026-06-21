from __future__ import annotations

import json
from datetime import timedelta

from .context import ContextBuilder, ContextSource
from .domain import Budget, MemoryKind, MemoryScope, RunStatus, SideEffect, ToolDescriptor, PolicyInput, utc_now
from .memory import InMemoryMemoryStore, MemoryService
from .orchestrator import InMemoryRunStore, RunService
from .policy import ReferencePolicyEngine


def main() -> None:
    now = utc_now()
    run_service = RunService(InMemoryRunStore())
    run = run_service.create_run(
        task_id="TASK-0001",
        context_id="CTX-example",
        attempt=1,
        agent_release="repository-maintainer@sha256:demo",
        budget=Budget(5.0, 20, 50, now + timedelta(minutes=30)),
    )
    run = run_service.transition(run.run_id, RunStatus.ADMITTED, expected_version=run.status_version)
    run = run_service.transition(run.run_id, RunStatus.QUEUED, expected_version=run.status_version)
    run = run_service.acquire_lease(
        run.run_id,
        holder="workload:worker-1",
        ttl_seconds=60,
        expected_version=run.status_version,
    )
    run = run_service.transition(run.run_id, RunStatus.PROVISIONING, expected_version=run.status_version)
    run = run_service.transition(run.run_id, RunStatus.RUNNING, expected_version=run.status_version)

    memory_service = MemoryService(InMemoryMemoryStore())
    candidate = memory_service.propose(
        kind=MemoryKind.SEMANTIC,
        scope=MemoryScope(tenant_id="TEN-1", project_id="PRJ-1"),
        statement="项目要求所有完成状态都关联 Evidence。",
        source_refs=("profiles/awkp/WORKFLOW.md",),
        created_by="REL-memory-extractor@sha256:demo",
        confidence=0.95,
        sensitivity="internal",
        retention_policy="project-governed",
        tags=("awkp", "evidence"),
    )
    active = memory_service.promote(candidate.memory_id, verifier="human:reviewer")

    context = ContextBuilder().build(
        run_id=run.run_id,
        agent_release_digest="sha256:demo",
        token_budget=400,
        sources=[
            ContextSource("policy", "POL-1", b"Never bypass approval.", "system-authoritative"),
            ContextSource("agent_release", "REL-1", b"repository-maintainer", "system-authoritative"),
            ContextSource("task", "TASK-0001", b"Maintain repository docs.", "project-authoritative"),
            ContextSource("run_state", run.run_id, json.dumps(run.to_dict()).encode(), "system-authoritative"),
            ContextSource("memory", active.memory_id, active.statement.encode(), "retrieved-untrusted"),
            ContextSource("output_contract", "SCHEMA-output", b"Return artifact and evidence refs.", "system-authoritative"),
        ],
    )

    tool = ToolDescriptor(
        name="deployment.production",
        version="1.0.0",
        side_effect=SideEffect.EXTERNAL_WRITE,
        risk_level="R2",
        required_scopes=("deploy:billing",),
        data_classes_allowed=("internal",),
        idempotency="caller_key_required",
        timeout_seconds=300,
    )
    policy_request = PolicyInput(
        human_identity="user:42",
        agent_release="sha256:demo",
        workload_identity="spiffe://example/worker/1",
        task_id="TASK-0001",
        task_risk="R2",
        action="tool.invoke",
        resource=tool.name,
        granted_scopes=("deploy:billing",),
        data_classes=("internal",),
        approval_refs=(),
    )
    decision = ReferencePolicyEngine().decide(policy_request, tool)

    print(json.dumps({
        "run": run.to_dict(),
        "active_memory": active.to_dict(),
        "context_manifest": context.to_dict(),
        "production_tool_decision": {
            "allow": decision.allow,
            "reason": decision.reason_code,
            "approval_required": decision.approval_required,
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
