from __future__ import annotations

import asyncio
import copy
import tempfile
import unittest
from pathlib import Path

from ahra.alignment_session import ACCEPTANCE_DRAFT_OUTPUT, REQUIREMENT_DRAFT_OUTPUT, AlignmentSessionError
from ahra.ports import AgentRunRequest, AgentRunResult
from ahra.workflow_a_cli import (
    RequestDraftAdmissionError,
    WorkflowAFixtureDriver,
    advance_session,
    approve_requirement,
    draft_request,
    read_snapshot,
    start_session,
)


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "intents" / "phase1-example-intent.yaml"


class WorkflowACliTests(unittest.TestCase):
    def test_draft_preflights_admission_before_writing_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            session = root / "session.json"
            request_draft = root / "request-draft.json"
            approval = root / "approval.json"

            start_session(intent_path=EXAMPLE, session_path=session)
            asyncio.run(
                advance_session(
                    session_path=session,
                    message="Keep the scope local.",
                    actor="human:maintainer",
                    driver=WorkflowAFixtureDriver(),
                )
            )
            approve_requirement(session_path=session, actor="human:maintainer")

            with self.assertRaises(RequestDraftAdmissionError) as raised:
                asyncio.run(
                    draft_request(
                        session_path=session,
                        request_draft_path=request_draft,
                        approval_path=approval,
                        driver=InvalidBudgetDriver(),
                    )
                )

            self.assertEqual(raised.exception.to_error_dict()["code"], "request_draft_admission_rejected")
            self.assertIn("invalid-budget", raised.exception.codes)
            self.assertTrue(request_draft.exists())
            self.assertFalse(approval.exists())

            snapshot = read_snapshot(session_path=session)["snapshot"]
            self.assertEqual(snapshot["stage"], "frozen")
            self.assertEqual(snapshot["turns"][-1]["actor"], "agent:request-admission")
            rejections = snapshot["turns"][-1]["error"]["rejections"]
            self.assertIn("invalid-budget", {item["code"] for item in rejections})

    def test_draft_timeout_writes_structured_resumable_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            session = root / "session.json"
            request_draft = root / "request-draft.json"

            start_session(intent_path=EXAMPLE, session_path=session)
            asyncio.run(
                advance_session(
                    session_path=session,
                    message="Keep the scope local.",
                    actor="human:maintainer",
                    driver=WorkflowAFixtureDriver(),
                )
            )
            approve_requirement(session_path=session, actor="human:maintainer")

            with self.assertRaises(AlignmentSessionError) as raised:
                asyncio.run(
                    draft_request(
                        session_path=session,
                        request_draft_path=request_draft,
                        approval_path=None,
                        driver=HangingDriver(),
                        timeout_seconds=0.01,
                    )
                )

            self.assertEqual(raised.exception.code, "agent_driver_timeout")
            self.assertEqual(raised.exception.to_dict()["data"]["expectedOutput"], ACCEPTANCE_DRAFT_OUTPUT)
            self.assertFalse(request_draft.exists())

            snapshot = read_snapshot(session_path=session)["snapshot"]
            self.assertEqual(snapshot["stage"], "frozen")
            self.assertEqual(snapshot["turns"][-1]["actor"], "agent:error")
            self.assertEqual(snapshot["turns"][-1]["error"]["code"], "agent_driver_timeout")


class HangingDriver:
    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        await asyncio.Event().wait()
        raise AssertionError(f"unexpected completion for {request.expected_output}")


class InvalidBudgetDriver(WorkflowAFixtureDriver):
    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        result = await super().run(request)
        if request.expected_output != REQUIREMENT_DRAFT_OUTPUT:
            return result
        output = copy.deepcopy(result.output)
        output["planDraft"]["spec"]["nodes"][1]["budgetRequest"]["maxToolCalls"] = 0
        return AgentRunResult(
            output=output,
            raw_output=result.raw_output,
            trace_ref=result.trace_ref,
            evidence_refs=result.evidence_refs,
        )


if __name__ == "__main__":
    unittest.main()
