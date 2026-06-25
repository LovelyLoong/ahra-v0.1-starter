from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping, Protocol, runtime_checkable

from .capabilities import CapabilityGrant
from .plan_ir import PlanIR, PlanNodeIR


class NodeExecutionStatus(StrEnum):
    ACCEPTED = "accepted"
    NEEDS_HUMAN = "needs_human"
    REJECTED = "rejected"
    ERROR = "error"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class NodeExecutionRequest:
    plan: PlanIR
    node: PlanNodeIR
    capability_grants: tuple[CapabilityGrant, ...]
    workspace_ref: str
    branch: str
    run_id: str
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.node.node_id not in {node.node_id for node in self.plan.nodes}:
            raise ValueError(f"node {self.node.node_id} is not part of plan {self.plan.plan_id}")
        if not self.capability_grants:
            raise ValueError("node execution requires at least one capability grant")


@dataclass(frozen=True, slots=True)
class NodeExecutionResult:
    node_run_id: str
    plan_id: str
    node_id: str
    node_type: str
    executor_release: str
    status: NodeExecutionStatus
    artifact_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    gate_refs: tuple[str, ...] = ()
    terminal_failure_refs: tuple[str, ...] = ()
    task_completed_state_update_attempted: bool = False
    message: str = ""
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "apiVersion": "ahra.dev/v1alpha1",
            "kind": "NodeRun",
            "metadata": {
                "nodeRunId": self.node_run_id,
                "planId": self.plan_id,
                "nodeId": self.node_id,
                "executorRelease": self.executor_release,
            },
            "spec": {
                "nodeType": self.node_type,
                "status": self.status.value,
                "artifactRefs": list(self.artifact_refs),
                "evidenceRefs": list(self.evidence_refs),
                "gateRefs": list(self.gate_refs),
                "terminalFailureRefs": list(self.terminal_failure_refs),
                "taskCompletedStateUpdateAttempted": self.task_completed_state_update_attempted,
                "message": self.message,
                "details": dict(self.details),
            },
        }


@runtime_checkable
class NodeExecutor(Protocol):
    @property
    def node_type(self) -> str: ...

    @property
    def release_ref(self) -> str: ...

    async def execute(self, request: NodeExecutionRequest) -> NodeExecutionResult: ...


class NodeExecutorRegistry:
    def __init__(self) -> None:
        self._executors: dict[tuple[str, str], NodeExecutor] = {}

    def register(self, executor: NodeExecutor) -> None:
        _require_immutable_release(executor.release_ref)
        key = (executor.node_type, executor.release_ref)
        if key in self._executors:
            raise ValueError(f"duplicate node executor: {executor.node_type} {executor.release_ref}")
        self._executors[key] = executor

    def get(self, node_type: str, release_ref: str) -> NodeExecutor:
        _require_immutable_release(release_ref)
        try:
            return self._executors[(node_type, release_ref)]
        except KeyError as exc:
            raise ValueError(f"unknown node executor: {node_type} {release_ref}") from exc

    def refs(self) -> tuple[str, ...]:
        return tuple(f"{node_type}@{release_ref}" for node_type, release_ref in sorted(self._executors))


def _require_immutable_release(release_ref: str) -> None:
    if not release_ref:
        raise ValueError("node executor release_ref is required")
    if release_ref.strip().lower().endswith("latest") or release_ref.strip().lower() == "latest":
        raise ValueError("node executor release_ref must be immutable, not latest")
    if "sha256:" not in release_ref:
        raise ValueError("node executor release_ref must include a sha256 digest")
