from __future__ import annotations

import asyncio
import subprocess
import tempfile
import unittest
from pathlib import Path

from ahra.mcp_server import AhraMCPServer
from ahra.ports import AgentDriver, AgentDriverRegistry, AgentRole, AgentRunRequest, AgentRunResult
from ahra.reference_runner.models import (
    CriterionAssessment,
    ReviewResult,
    ReviewVerdict,
    WorkReport,
    WorkflowOutcome,
)


class MCPFakeDriver(AgentDriver):
    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        if request.role == AgentRole.EXECUTOR:
            workspace = Path(str(request.workspace_ref))
            (workspace / "value.py").write_text("VALUE = 2\n", encoding="utf-8")
            return AgentRunResult(output=WorkReport(summary="Updated value", changed_files=("value.py",)))
        if request.role == AgentRole.TASK_REVIEWER:
            task = request.payload["task"]
            return AgentRunResult(
                output=ReviewResult(
                    verdict=ReviewVerdict.PASS,
                    summary="Criterion is supported.",
                    criteria=tuple(
                        CriterionAssessment(
                            criterion=criterion,
                            passed=True,
                            evidence="MCP fake driver accepted deterministic result.",
                        )
                        for criterion in task.acceptance_criteria
                    ),
                )
            )
        raise AssertionError(f"unexpected role: {request.role}")


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def _init_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "value.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(
        repo,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-q",
        "-m",
        "initial",
    )
    return repo


class MCPServerTests(unittest.TestCase):
    def test_mcp_handler_validates_and_starts_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = _init_repo(Path(temp))
            registry = AgentDriverRegistry()
            registry.register("fake-reference", MCPFakeDriver())
            server = AhraMCPServer(drivers=registry)
            document = {
                "apiVersion": "ahra.dev/v1alpha1",
                "kind": "WorkflowRunRequest",
                "metadata": {"name": "mcp-standard-task"},
                "spec": {
                    "moduleId": "standard-harness",
                    "input": {
                        "task": {
                            "id": "mcp-task",
                            "title": "MCP task",
                            "objective": "Set VALUE to 2",
                            "acceptance_criteria": ["VALUE equals 2"],
                        }
                    },
                    "workspaceRef": str(repo),
                    "driverRef": "fake-reference",
                    "storeRef": "local-file",
                    "artifactDir": str(Path(temp) / "artifacts"),
                    "runId": "RUN-mcp-standard",
                    "approvalMode": "manual",
                },
            }
            validation = asyncio.run(
                server.call_tool("ahra.validate_workflow_run_request", {"document": document})
            )
            self.assertTrue(validation["valid"])
            started = asyncio.run(server.call_tool("ahra.start_workflow", {"document": document}))
            self.assertEqual(started["status"], WorkflowOutcome.ACCEPTED)
            run = asyncio.run(
                server.call_tool("ahra.get_workflow_run", {"artifactDir": str(Path(temp) / "artifacts")})
            )
            self.assertIn("workflow-run-request.json", run["files"])
            self.assertIn("artifact-manifest.json", run["files"])

    def test_mcp_lists_reference_modules(self) -> None:
        server = AhraMCPServer()
        result = asyncio.run(server.call_tool("ahra.list_workflow_modules", {}))
        self.assertEqual(
            [module["module_id"] for module in result["modules"]],
            ["loop-engineering", "standard-harness"],
        )


if __name__ == "__main__":
    unittest.main()
