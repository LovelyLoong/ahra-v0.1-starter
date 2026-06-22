from __future__ import annotations

import asyncio
import json
import unittest

from ahra.adapters import CodexDriverConfig, CodexSDKDriver
from ahra.ports import AgentRole, AgentRunRequest
from ahra.reference_runner.models import NextStepDecision, PlanAction, WorkReport


class FakeCodexClient:
    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = responses
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
        return self.responses[request.expected_output]


class CodexSDKDriverTests(unittest.TestCase):
    def test_executor_response_parses_work_report(self) -> None:
        client = FakeCodexClient(
            {
                "WorkReport": json.dumps(
                    {
                        "summary": "Updated value",
                        "changed_files": ["value.py"],
                        "verification_commands_run": ["python -m unittest"],
                    }
                )
            }
        )
        driver = CodexSDKDriver(
            CodexDriverConfig(model="gpt-5.4"),
            client=client,
        )
        result = asyncio.run(
            driver.run(
                AgentRunRequest(
                    role=AgentRole.EXECUTOR,
                    run_id="RUN-codex-test",
                    expected_output="WorkReport",
                    workspace_ref=".",
                    payload={"task": {"id": "task-1"}},
                )
            )
        )
        self.assertIsInstance(result.output, WorkReport)
        self.assertEqual(result.output.changed_files, ("value.py",))
        self.assertEqual(client.calls[0]["sandbox"], "workspace_write")
        self.assertEqual(client.calls[0]["model"], "gpt-5.4")
        self.assertIn("Expected output type: WorkReport", client.calls[0]["prompt"])

    def test_planner_response_parses_next_step_decision(self) -> None:
        client = FakeCodexClient(
            {
                "NextStepDecision": json.dumps(
                    {
                        "action": "add_tasks",
                        "rationale": "Add bounded follow-up task.",
                        "proposed_tasks": [
                            {
                                "id": "set-value-3",
                                "title": "Set value to 3",
                                "objective": "Set VALUE to 3",
                                "acceptance_criteria": ["VALUE equals 3"],
                            }
                        ],
                    }
                )
            }
        )
        driver = CodexSDKDriver(client=client)
        result = asyncio.run(
            driver.run(
                AgentRunRequest(
                    role=AgentRole.PLANNER,
                    run_id="RUN-codex-test",
                    expected_output="NextStepDecision",
                    payload={"goal": {"id": "goal-1"}},
                )
            )
        )
        self.assertIsInstance(result.output, NextStepDecision)
        self.assertEqual(result.output.action, PlanAction.ADD_TASKS)
        self.assertEqual(result.output.proposed_tasks[0].id, "set-value-3")
        self.assertEqual(client.calls[0]["sandbox"], "read_only")

    def test_invalid_json_fails_closed(self) -> None:
        driver = CodexSDKDriver(client=FakeCodexClient({"WorkReport": "not json"}))
        with self.assertRaisesRegex(ValueError, "JSON object"):
            asyncio.run(
                driver.run(
                    AgentRunRequest(
                        role=AgentRole.EXECUTOR,
                        run_id="RUN-codex-test",
                        expected_output="WorkReport",
                        payload={},
                    )
                )
            )


if __name__ == "__main__":
    unittest.main()
