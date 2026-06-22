from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Iterable, Protocol, runtime_checkable

from .domain import (
    ContextManifest,
    MemoryRecord,
    PolicyDecision,
    PolicyInput,
    RunRecord,
    ToolDescriptor,
)


class AgentRole(StrEnum):
    EXECUTOR = "executor"
    TASK_REVIEWER = "task_reviewer"
    GOAL_REVIEWER = "goal_reviewer"
    PLANNER = "planner"


@dataclass(frozen=True, slots=True)
class AgentRunRequest:
    role: AgentRole
    run_id: str
    expected_output: str
    payload: dict[str, Any]
    workspace_ref: str | None = None
    attempt: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentRunResult:
    output: Any
    raw_output: Any | None = None
    trace_ref: str | None = None
    evidence_refs: tuple[str, ...] = ()


@runtime_checkable
class AgentDriver(Protocol):
    async def run(self, request: AgentRunRequest) -> AgentRunResult: ...


class AgentDriverRegistry:
    def __init__(self) -> None:
        self._drivers: dict[str, AgentDriver] = {}

    def register(self, driver_ref: str, driver: AgentDriver) -> None:
        if driver_ref in self._drivers:
            raise ValueError(f"duplicate agent driver ref: {driver_ref}")
        self._drivers[driver_ref] = driver

    def get(self, driver_ref: str) -> AgentDriver:
        try:
            return self._drivers[driver_ref]
        except KeyError as exc:
            raise ValueError(f"unknown agent driver ref: {driver_ref}") from exc

    def refs(self) -> tuple[str, ...]:
        return tuple(sorted(self._drivers))


@runtime_checkable
class RunStore(Protocol):
    def create(self, run: RunRecord) -> None: ...
    def get(self, run_id: str) -> RunRecord: ...
    def compare_and_swap(self, run: RunRecord, expected_version: int) -> RunRecord: ...


@runtime_checkable
class EventPublisher(Protocol):
    def publish(self, event_type: str, subject: str, data: dict[str, Any]) -> None: ...


@runtime_checkable
class WorkflowEngine(Protocol):
    def start(self, definition_ref: str, input_data: dict[str, Any], idempotency_key: str) -> str: ...
    def signal(self, execution_id: str, signal_type: str, payload: dict[str, Any]) -> None: ...
    def cancel(self, execution_id: str, reason: str) -> None: ...
    def status(self, execution_id: str) -> str: ...


@runtime_checkable
class SessionStore(Protocol):
    def append_event(self, session_id: str, event: dict[str, Any]) -> None: ...
    def events(self, session_id: str, limit: int = 100) -> list[dict[str, Any]]: ...


@runtime_checkable
class CheckpointStore(Protocol):
    def put(self, run_id: str, payload: dict[str, Any]) -> str: ...
    def get(self, checkpoint_ref: str) -> dict[str, Any]: ...


@runtime_checkable
class MemoryStore(Protocol):
    def put(self, record: MemoryRecord) -> None: ...
    def get(self, memory_id: str) -> MemoryRecord: ...
    def replace(self, record: MemoryRecord) -> None: ...
    def list_for_scope(self, tenant_id: str, project_id: str | None = None) -> list[MemoryRecord]: ...


@runtime_checkable
class ContextBuilderPort(Protocol):
    def build(self, run_id: str, agent_release_digest: str, sources: Iterable[Any], token_budget: int) -> ContextManifest: ...


@runtime_checkable
class ModelGateway(Protocol):
    def invoke(self, request: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]: ...
    def capabilities(self, model_ref: str) -> dict[str, Any]: ...
    def estimate(self, request: dict[str, Any]) -> dict[str, Any]: ...


@runtime_checkable
class ToolRegistry(Protocol):
    def get(self, name: str, version: str | None = None) -> ToolDescriptor: ...


@runtime_checkable
class ToolExecutor(Protocol):
    def invoke(
        self,
        descriptor: ToolDescriptor,
        arguments: dict[str, Any],
        idempotency_key: str,
        deadline: datetime,
        policy_decision: PolicyDecision,
    ) -> dict[str, Any]: ...


@runtime_checkable
class PolicyEngine(Protocol):
    def decide(self, request: PolicyInput, tool: ToolDescriptor) -> PolicyDecision: ...


@runtime_checkable
class RuntimeProvider(Protocol):
    def provision(self, profile_ref: str, workspace_ref: str, identity: str) -> str: ...
    def exec(self, handle: str, command: list[str], env: dict[str, str], deadline: datetime) -> dict[str, Any]: ...
    def snapshot(self, handle: str) -> str: ...
    def cancel(self, handle: str, execution_id: str) -> None: ...
    def destroy(self, handle: str) -> None: ...


@runtime_checkable
class WorkspaceProvider(Protocol):
    def resolve_path(self, workspace_ref: str) -> str: ...
    def current_head(self, workspace_ref: str) -> str: ...
    def changed_files(self, workspace_ref: str, checkpoint: str) -> list[str]: ...
    def numstat(self, workspace_ref: str, checkpoint: str) -> tuple[int, int]: ...
    def patch(self, workspace_ref: str, checkpoint: str) -> str: ...
    def restore_patch(self, workspace_ref: str, checkpoint: str, patch_text: str) -> None: ...
    def rollback(self, workspace_ref: str, checkpoint: str) -> None: ...
    def commit_all(self, workspace_ref: str, message: str) -> str: ...


@runtime_checkable
class ArtifactStore(Protocol):
    def put(self, content: bytes, media_type: str, metadata: dict[str, Any]) -> str: ...
    def get(self, artifact_ref: str) -> bytes: ...


@runtime_checkable
class EvidenceStore(Protocol):
    def put(self, content: bytes, media_type: str, metadata: dict[str, Any]) -> str: ...
    def get(self, evidence_ref: str) -> bytes: ...


@runtime_checkable
class ApprovalService(Protocol):
    def request(self, request: dict[str, Any]) -> str: ...
    def status(self, approval_id: str) -> str: ...


@runtime_checkable
class EvalRunner(Protocol):
    def run(self, suite_ref: str, agent_release: str, environment: str) -> dict[str, Any]: ...


@runtime_checkable
class ProjectAdapter(Protocol):
    def prepare_workspace(self, task_id: str, run_id: str, runtime_profile: str) -> str: ...
    def bootstrap(self, workspace_ref: str) -> dict[str, Any]: ...
    def health_check(self, workspace_ref: str) -> str: ...
    def test(self, workspace_ref: str, scope: str) -> str: ...
    def build(self, workspace_ref: str, target: str) -> str: ...
    def preview_change(self, workspace_ref: str) -> str: ...
