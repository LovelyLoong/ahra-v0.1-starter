from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class WorkflowModuleError(RuntimeError):
    pass


VALID_RUN_STATUSES = {
    "created",
    "admitted",
    "queued",
    "provisioning",
    "running",
    "paused_input",
    "paused_auth",
    "paused_policy",
    "backoff",
    "suspended",
    "verifying",
    "succeeded",
    "failed",
    "timed_out",
    "canceled",
}

VALID_TASK_STATUSES = {
    "queued",
    "ready",
    "working",
    "waiting_input",
    "waiting_auth",
    "waiting_dependency",
    "review",
    "changes_requested",
    "completed",
    "failed",
    "canceled",
    "rejected",
}

VALID_PORTS = {
    "AgentDriver",
    "RunStore",
    "EventPublisher",
    "WorkflowEngine",
    "SessionStore",
    "CheckpointStore",
    "MemoryStore",
    "ContextBuilderPort",
    "ModelGateway",
    "ToolRegistry",
    "ToolExecutor",
    "PolicyEngine",
    "RuntimeProvider",
    "WorkspaceProvider",
    "ArtifactStore",
    "EvidenceStore",
    "ApprovalService",
    "EvalRunner",
    "ProjectAdapter",
}


@dataclass(frozen=True, slots=True)
class WorkflowModuleSource:
    repository: str
    components: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WorkflowModuleContract:
    name: str
    version: str
    owner: str
    module_id: str
    description: str
    source: WorkflowModuleSource
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    run_state_mapping: dict[str, str]
    task_state_mapping: dict[str, str]
    required_ports: tuple[str, ...]
    safety_gates: tuple[str, ...]
    artifacts: tuple[str, ...]
    evidence: tuple[str, ...]
    tests: tuple[str, ...]
    extends: str | None = None

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> WorkflowModuleContract:
        if document.get("apiVersion") != "ahra.dev/v1alpha1":
            raise WorkflowModuleError("workflow module apiVersion must be ahra.dev/v1alpha1")
        if document.get("kind") != "WorkflowModule":
            raise WorkflowModuleError("workflow module kind must be WorkflowModule")
        metadata = document["metadata"]
        spec = document["spec"]
        source = spec["source"]
        mapping = spec["stateMapping"]
        contract = cls(
            name=metadata["name"],
            version=metadata["version"],
            owner=metadata["owner"],
            module_id=spec["moduleId"],
            extends=spec.get("extends"),
            description=spec["description"],
            source=WorkflowModuleSource(
                repository=source["repository"],
                components=tuple(source["components"]),
            ),
            inputs=tuple(spec["inputs"]),
            outputs=tuple(spec["outputs"]),
            run_state_mapping=dict(mapping["run"]),
            task_state_mapping=dict(mapping["task"]),
            required_ports=tuple(spec["requiredPorts"]),
            safety_gates=tuple(spec["safetyGates"]),
            artifacts=tuple(spec["artifacts"]),
            evidence=tuple(spec["evidence"]),
            tests=tuple(spec["tests"]),
        )
        contract.validate()
        return contract

    def validate(self) -> None:
        if self.name != self.module_id:
            raise WorkflowModuleError("workflow module metadata.name must match spec.moduleId")
        unknown_ports = sorted(set(self.required_ports) - VALID_PORTS)
        if unknown_ports:
            raise WorkflowModuleError(f"unknown workflow module ports: {unknown_ports}")
        invalid_run_states = sorted(set(self.run_state_mapping.values()) - VALID_RUN_STATUSES)
        if invalid_run_states:
            raise WorkflowModuleError(f"invalid AHRA run states: {invalid_run_states}")
        invalid_task_states = sorted(set(self.task_state_mapping.values()) - VALID_TASK_STATUSES)
        if invalid_task_states:
            raise WorkflowModuleError(f"invalid AWKP task states: {invalid_task_states}")
        if "ArtifactStore" not in self.required_ports:
            raise WorkflowModuleError("workflow module must declare ArtifactStore")
        if "EvidenceStore" not in self.required_ports:
            raise WorkflowModuleError("workflow module must declare EvidenceStore")
        if "EventPublisher" not in self.required_ports:
            raise WorkflowModuleError("workflow module must declare EventPublisher")
        if "AgentDriver" not in self.required_ports:
            raise WorkflowModuleError("workflow module must declare AgentDriver")

    @classmethod
    def from_path(cls, path: Path) -> WorkflowModuleContract:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise WorkflowModuleError(f"workflow module document is not an object: {path}")
        return cls.from_document(document)

    @property
    def ref(self) -> str:
        return f"{self.module_id}@{self.version}"


class WorkflowModuleRegistry:
    def __init__(self) -> None:
        self._modules: dict[str, WorkflowModuleContract] = {}

    def register(self, module: WorkflowModuleContract) -> None:
        if module.module_id in self._modules:
            raise WorkflowModuleError(f"duplicate workflow module: {module.module_id}")
        if module.extends and module.extends not in self._modules:
            raise WorkflowModuleError(
                f"workflow module {module.module_id} extends unknown module {module.extends}"
            )
        self._modules[module.module_id] = module

    def get(self, module_id: str) -> WorkflowModuleContract:
        try:
            return self._modules[module_id]
        except KeyError as exc:
            raise WorkflowModuleError(f"unknown workflow module: {module_id}") from exc

    def list(self) -> tuple[WorkflowModuleContract, ...]:
        return tuple(self._modules[key] for key in sorted(self._modules))


def load_workflow_module_registry(paths: list[Path]) -> WorkflowModuleRegistry:
    registry = WorkflowModuleRegistry()
    pending = [WorkflowModuleContract.from_path(path) for path in paths]
    while pending:
        progressed = False
        remaining: list[WorkflowModuleContract] = []
        for module in pending:
            if module.extends and module.extends not in {item.module_id for item in registry.list()}:
                remaining.append(module)
                continue
            registry.register(module)
            progressed = True
        if not progressed:
            unresolved = ", ".join(module.module_id for module in remaining)
            raise WorkflowModuleError(f"unresolved workflow module dependencies: {unresolved}")
        pending = remaining
    return registry
