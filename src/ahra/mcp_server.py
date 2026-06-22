from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from ahra.evidence_gate import evaluate_task_gate, inspect_task
from ahra.ports import AgentDriverRegistry
from ahra.reference_runner.invocation import (
    load_reference_workflow_module_registry,
    load_workflow_resume_request,
    load_workflow_run_request,
    resume_workflow,
    run_workflow,
    workflow_resume_request_from_document,
    workflow_run_request_from_document,
)
from ahra.reference_runner.models import to_jsonable
from ahra.workflow_modules import WorkflowModuleRegistry


class AhraMCPServer:
    def __init__(
        self,
        *,
        drivers: AgentDriverRegistry | None = None,
        module_registry: WorkflowModuleRegistry | None = None,
        workspace_provider=None,
        runtime_provider=None,
    ) -> None:
        self.drivers = drivers or _default_driver_registry()
        self.module_registry = module_registry
        self.workspace_provider = workspace_provider
        self.runtime_provider = runtime_provider

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "ahra.list_workflow_modules",
                "description": "List registered AHRA workflow modules.",
                "inputSchema": {"type": "object", "additionalProperties": False},
            },
            {
                "name": "ahra.validate_workflow_run_request",
                "description": "Validate a WorkflowRunRequest document or requestPath.",
                "inputSchema": {
                    "type": "object",
                    "oneOf": [
                        {"required": ["document"]},
                        {"required": ["requestPath"]},
                    ],
                    "properties": {
                        "document": {"type": "object"},
                        "requestPath": {"type": "string"},
                    },
                },
            },
            {
                "name": "ahra.start_workflow",
                "description": "Start a workflow through the reference runner API.",
                "inputSchema": {
                    "type": "object",
                    "oneOf": [
                        {"required": ["document"]},
                        {"required": ["requestPath"]},
                    ],
                    "properties": {
                        "document": {"type": "object"},
                        "requestPath": {"type": "string"},
                    },
                },
            },
            {
                "name": "ahra.get_workflow_run",
                "description": "Read local workflow run artifacts and manifests.",
                "inputSchema": {
                    "type": "object",
                    "required": ["artifactDir"],
                    "properties": {"artifactDir": {"type": "string"}},
                },
            },
            {
                "name": "ahra.resume_workflow",
                "description": "Resume a paused workflow through WorkflowResumeRequest.",
                "inputSchema": {
                    "type": "object",
                    "oneOf": [
                        {"required": ["document"]},
                        {"required": ["requestPath"]},
                    ],
                    "properties": {
                        "document": {"type": "object"},
                        "requestPath": {"type": "string"},
                    },
                },
            },
            {
                "name": "ahra.task_inspect",
                "description": "Inspect AWKP task state, manifests, events, and acceptance criteria.",
                "inputSchema": {
                    "type": "object",
                    "required": ["taskId"],
                    "properties": {
                        "taskId": {"type": "string"},
                        "workRoot": {"type": "string"},
                    },
                },
            },
            {
                "name": "ahra.evidence_gate_evaluate",
                "description": "Evaluate an AWKP task through EvidenceGate and update task state.",
                "inputSchema": {
                    "type": "object",
                    "required": ["taskId", "expectedVersion", "reportPath", "actor"],
                    "properties": {
                        "taskId": {"type": "string"},
                        "expectedVersion": {"type": "integer"},
                        "reportPath": {"type": "string"},
                        "actor": {"type": "string"},
                        "decision": {"type": "string", "enum": ["approve", "request_changes"]},
                        "workRoot": {"type": "string"},
                        "dryRun": {"type": "boolean"},
                    },
                },
            },
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        arguments = arguments or {}
        if name == "ahra.list_workflow_modules":
            registry = self._module_registry()
            return {"modules": [to_jsonable(module) for module in registry.list()]}
        if name == "ahra.validate_workflow_run_request":
            try:
                request = self._run_request(arguments)
            except Exception as exc:  # noqa: BLE001 - MCP tools return structured errors.
                return {"valid": False, "error": str(exc)}
            return {"valid": True, "request": to_jsonable(request)}
        if name == "ahra.start_workflow":
            request = self._run_request(arguments)
            envelope = await run_workflow(
                request,
                drivers=self.drivers,
                module_registry=self._module_registry(),
                workspace_provider=self.workspace_provider,
                runtime_provider=self.runtime_provider,
            )
            return _envelope_summary(envelope)
        if name == "ahra.get_workflow_run":
            return _read_workflow_run(Path(str(arguments["artifactDir"])))
        if name == "ahra.resume_workflow":
            request = self._resume_request(arguments)
            envelope = await resume_workflow(
                request,
                drivers=self.drivers,
                module_registry=self._module_registry(),
                workspace_provider=self.workspace_provider,
                runtime_provider=self.runtime_provider,
            )
            return _envelope_summary(envelope)
        if name == "ahra.task_inspect":
            return inspect_task(
                str(arguments["taskId"]),
                work_root=str(arguments.get("workRoot") or "work"),
            )
        if name == "ahra.evidence_gate_evaluate":
            return evaluate_task_gate(
                str(arguments["taskId"]),
                work_root=str(arguments.get("workRoot") or "work"),
                expected_version=int(arguments["expectedVersion"]),
                report_path=str(arguments["reportPath"]),
                actor=str(arguments["actor"]),
                decision=arguments.get("decision"),
                dry_run=bool(arguments.get("dryRun") or False),
            ).to_dict()
        raise ValueError(f"unknown AHRA MCP tool: {name}")

    def _module_registry(self) -> WorkflowModuleRegistry:
        if self.module_registry is None:
            self.module_registry = load_reference_workflow_module_registry()
        return self.module_registry

    @staticmethod
    def _run_request(arguments: dict[str, Any]):
        if "requestPath" in arguments:
            return load_workflow_run_request(Path(str(arguments["requestPath"])))
        document = arguments.get("document")
        if not isinstance(document, dict):
            raise ValueError("document must be an object")
        return workflow_run_request_from_document(document)

    @staticmethod
    def _resume_request(arguments: dict[str, Any]):
        if "requestPath" in arguments:
            return load_workflow_resume_request(Path(str(arguments["requestPath"])))
        document = arguments.get("document")
        if not isinstance(document, dict):
            raise ValueError("document must be an object")
        return workflow_resume_request_from_document(document)


def _default_driver_registry() -> AgentDriverRegistry:
    registry = AgentDriverRegistry()
    try:
        from ahra.adapters import CodexSDKDriver

        driver = CodexSDKDriver()
        registry.register(driver.config.driver_ref, driver)
    except ImportError:
        pass
    return registry


def _envelope_summary(envelope: Any) -> dict[str, Any]:
    return {
        "runId": envelope.run_id,
        "moduleId": envelope.module_id,
        "driverRef": envelope.driver_ref,
        "status": envelope.status,
        "artifactDir": envelope.artifact_dir,
        "result": to_jsonable(envelope.result),
    }


def _read_workflow_run(artifact_dir: Path) -> dict[str, Any]:
    if not artifact_dir.exists() or not artifact_dir.is_dir():
        raise ValueError(f"workflow artifactDir does not exist: {artifact_dir}")
    names = [
        "workflow-run-request.json",
        "workflow-run-result.json",
        "workspace.json",
        "workflow-resume-request.json",
        "workflow-resume-result.json",
        "artifact-manifest.json",
        "evidence-manifest.json",
    ]
    result: dict[str, Any] = {"artifactDir": str(artifact_dir.resolve()), "files": {}}
    for name in names:
        path = artifact_dir / name
        if path.exists():
            result["files"][name] = json.loads(path.read_text(encoding="utf-8"))
    events = artifact_dir / "events.jsonl"
    if events.exists():
        result["events"] = [
            json.loads(line)
            for line in events.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    return result


async def _handle_message(server: AhraMCPServer, message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")
    try:
        if method == "initialize":
            result = {
                "protocolVersion": "2025-06-18",
                "serverInfo": {"name": "ahra-reference", "version": "0.1.0"},
                "capabilities": {"tools": {}},
            }
        elif method == "tools/list":
            result = {"tools": server.list_tools()}
        elif method == "tools/call":
            params = message.get("params") or {}
            tool_result = await server.call_tool(params["name"], params.get("arguments") or {})
            result = {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(tool_result, ensure_ascii=False, indent=2),
                    }
                ]
            }
        elif method == "notifications/initialized":
            return None
        else:
            raise ValueError(f"unsupported JSON-RPC method: {method}")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except Exception as exc:  # noqa: BLE001 - JSON-RPC must serialize tool errors.
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32000, "message": str(exc)},
        }


async def amain() -> None:
    server = AhraMCPServer()
    for line in sys.stdin:
        if not line.strip():
            continue
        response = await _handle_message(server, json.loads(line))
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()
