from __future__ import annotations

import asyncio
import json
import sys
import types
import unittest

from ahra.adapters import CodexDriverConfig, CodexSDKClient, CodexSDKDriver
from ahra.ports import AgentOutputContractError, AgentRole, AgentRunRequest
from ahra.reference_runner.models import NextStepDecision, PlanAction, WorkReport
from ahra.reference_runner.output_contracts import output_contract


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

    def test_output_contract_schema_is_prompted_and_validated(self) -> None:
        client = FakeCodexClient(
            {
                "ReviewResult": json.dumps(
                    {
                        "status": "pass",
                        "findings": [],
                    }
                )
            }
        )
        driver = CodexSDKDriver(client=client)
        with self.assertRaisesRegex(AgentOutputContractError, "verdict"):
            asyncio.run(
                driver.run(
                    AgentRunRequest(
                        role=AgentRole.TASK_REVIEWER,
                        run_id="RUN-codex-test",
                        expected_output="ReviewResult",
                        output_contract=output_contract("ReviewResult"),
                        payload={"task": {"id": "task-1"}},
                    )
                )
            )
        self.assertIn("JSON Schema", client.calls[0]["prompt"])
        self.assertIn('"verdict"', client.calls[0]["prompt"])
        self.assertIn("Do not add fields outside the output contract", client.calls[0]["prompt"])

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

    def test_sdk_client_passes_cwd_to_codex_session(self) -> None:
        captured: dict[str, object] = {}

        class FakeSandbox:
            workspace_write = "workspace_write"
            read_only = "read_only"
            full_access = "full_access"

        class FakeCodexConfig:
            def __init__(self, **kwargs):
                captured["config"] = kwargs

        class FakeThread:
            async def run(self, prompt):
                captured["prompt"] = prompt
                return types.SimpleNamespace(
                    final_response=json.dumps(
                        {
                            "summary": "done",
                            "changed_files": [],
                            "verification_commands_run": [],
                        }
                    )
                )

        class FakeAsyncCodex:
            def __init__(self, **kwargs):
                captured["codex_kwargs"] = kwargs

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return None

            async def thread_start(self, **kwargs):
                captured["thread_kwargs"] = kwargs
                return FakeThread()

        previous = sys.modules.get("openai_codex")
        sys.modules["openai_codex"] = types.SimpleNamespace(
            AsyncCodex=FakeAsyncCodex,
            CodexConfig=FakeCodexConfig,
            Sandbox=FakeSandbox,
        )
        try:
            client = CodexSDKClient(CodexDriverConfig(codex_bin="codex-bin"))
            raw = asyncio.run(
                client.run(
                    request=AgentRunRequest(
                        role=AgentRole.EXECUTOR,
                        run_id="RUN-codex-test",
                        expected_output="WorkReport",
                        workspace_ref="C:/repo",
                        payload={},
                    ),
                    prompt="prompt",
                    sandbox="workspace_write",
                    model="gpt-test",
                    cwd="C:/repo",
                )
            )
        finally:
            if previous is None:
                sys.modules.pop("openai_codex", None)
            else:
                sys.modules["openai_codex"] = previous

        self.assertIn("done", raw)
        self.assertEqual(captured["config"], {"codex_bin": "codex-bin", "cwd": "C:/repo"})
        self.assertEqual(captured["thread_kwargs"]["cwd"], "C:/repo")
        self.assertEqual(captured["thread_kwargs"]["model"], "gpt-test")
        self.assertEqual(captured["thread_kwargs"]["sandbox"], "workspace_write")

if __name__ == "__main__":
    unittest.main()
