from __future__ import annotations

import asyncio
import json
import unittest

from ahra.adapters.codex_sdk import CodexSDKDriver
from ahra.alignment_session import (
    ACCEPTANCE_DRAFT_OUTPUT,
    ALIGNMENT_DECISION_OUTPUT,
    REQUIREMENT_DRAFT_OUTPUT,
    _output_contract,
)
from ahra.ports import AgentOutputContractError, AgentRole, AgentRunRequest


class FakeCodexClient:
    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    async def run(self, *, request, prompt, sandbox, model, cwd):
        self.calls.append(
            {
                "expected_output": request.expected_output,
                "prompt": prompt,
                "sandbox": sandbox,
                "model": model,
                "cwd": cwd,
            }
        )
        return self.responses[request.expected_output]


class CodexSDKDriverAlignmentOutputTests(unittest.TestCase):
    def test_alignment_turn_decision_output_parses_as_mapping(self) -> None:
        output = {
            "message": "Need the artifact path before drafting.",
            "converged": False,
            "missingDimensions": ["artifact path"],
        }
        result, client = self._run_alignment_output(ALIGNMENT_DECISION_OUTPUT, output)

        self.assertEqual(result.output, output)
        self.assertEqual(client.calls[0]["sandbox"], "read_only")
        self.assertIn("Expected output type: AlignmentTurnDecision", client.calls[0]["prompt"])
        self.assertIn("Output contract name: AlignmentTurnDecision", client.calls[0]["prompt"])

    def test_requirement_draft_output_parses_as_mapping(self) -> None:
        output = {
            "summary": "Create the bounded artifact.",
            "planDraft": {
                "kind": "PlanDraft",
                "metadata": {"goalId": "GOAL-1", "proposedBy": "agent:test"},
                "spec": {"nodes": []},
            },
        }
        result, client = self._run_alignment_output(REQUIREMENT_DRAFT_OUTPUT, output)

        self.assertEqual(result.output, output)
        self.assertIn("Expected output type: RequirementDraft", client.calls[0]["prompt"])
        self.assertIn("Output contract name: RequirementDraft", client.calls[0]["prompt"])

    def test_acceptance_draft_output_parses_as_mapping(self) -> None:
        output = {
            "summary": "Acceptance covers the required artifact.",
            "claimGraph": {
                "kind": "ClaimGraph",
                "claims": [],
                "edges": [],
            },
        }
        result, client = self._run_alignment_output(ACCEPTANCE_DRAFT_OUTPUT, output)

        self.assertEqual(result.output, output)
        self.assertIn("Expected output type: AcceptanceDraft", client.calls[0]["prompt"])
        self.assertIn("Output contract name: AcceptanceDraft", client.calls[0]["prompt"])

    def test_malformed_alignment_json_is_structured_output_error(self) -> None:
        client = FakeCodexClient({ALIGNMENT_DECISION_OUTPUT: "not json"})
        driver = CodexSDKDriver(client=client)

        with self.assertRaises(AgentOutputContractError) as raised:
            asyncio.run(
                driver.run(
                    AgentRunRequest(
                        role=AgentRole.PLANNER,
                        run_id="RUN-alignment-json-error",
                        expected_output=ALIGNMENT_DECISION_OUTPUT,
                        output_contract=_output_contract(ALIGNMENT_DECISION_OUTPUT),
                        payload={"phase": "alignment-dialogue"},
                    )
                )
            )

        self.assertEqual(raised.exception.expected_output, ALIGNMENT_DECISION_OUTPUT)
        self.assertIn("JSON object", raised.exception.message)

    def _run_alignment_output(self, expected_output: str, output: dict[str, object]):
        client = FakeCodexClient({expected_output: json.dumps(output)})
        driver = CodexSDKDriver(client=client)
        result = asyncio.run(
            driver.run(
                AgentRunRequest(
                    role=AgentRole.PLANNER,
                    run_id=f"RUN-{expected_output}",
                    expected_output=expected_output,
                    output_contract=_output_contract(expected_output),
                    payload={"phase": expected_output},
                    workspace_ref=".",
                )
            )
        )
        return result, client


if __name__ == "__main__":
    unittest.main()
