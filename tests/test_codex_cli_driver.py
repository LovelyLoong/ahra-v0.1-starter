from __future__ import annotations

import asyncio
import json
import unittest

from ahra.adapters import CodexCLIConfig, CodexCLIDriver
from ahra.adapters.codex_cli import _cli_sandbox
from ahra.ports import AgentRole, AgentRunRequest
from ahra.reference_runner.models import WorkReport


class FakeCodexCLIClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls = []

    async def run(self, *, request, prompt, sandbox, model, cwd):
        self.calls.append(
            {
                "role": request.role,
                "expected_output": request.expected_output,
                "prompt": prompt,
                "sandbox": sandbox,
                "model": model,
                "cwd": cwd,
            }
        )
        return self.response


class CodexCLIDriverTests(unittest.TestCase):
    def test_executor_response_parses_work_report(self) -> None:
        client = FakeCodexCLIClient(
            json.dumps(
                {
                    "summary": "Updated README",
                    "changed_files": ["README.md"],
                    "verification_commands_run": ["python scripts/check.py"],
                }
            )
        )
        driver = CodexCLIDriver(CodexCLIConfig(model="gpt-5.5"), client=client)

        result = asyncio.run(
            driver.run(
                AgentRunRequest(
                    role=AgentRole.EXECUTOR,
                    run_id="RUN-codex-cli-test",
                    expected_output="WorkReport",
                    workspace_ref=".",
                    payload={"task": {"id": "task-1"}},
                )
            )
        )

        self.assertIsInstance(result.output, WorkReport)
        self.assertEqual(result.output.changed_files, ("README.md",))
        self.assertEqual(client.calls[0]["sandbox"], "workspace_write")
        self.assertEqual(client.calls[0]["model"], "gpt-5.5")
        self.assertIn("Executor duty", client.calls[0]["prompt"])

    def test_cli_sandbox_mapping(self) -> None:
        self.assertEqual(_cli_sandbox("read_only"), "read-only")
        self.assertEqual(_cli_sandbox("workspace_write"), "workspace-write")
        self.assertEqual(_cli_sandbox("danger_full_access"), "danger-full-access")
        with self.assertRaisesRegex(ValueError, "unsupported"):
            _cli_sandbox("networked")


if __name__ == "__main__":
    unittest.main()
