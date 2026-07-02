from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from ahra.alignment_session import AlignmentSessionError, REQUIREMENT_DRAFT_OUTPUT
from ahra.ports import AgentRunRequest, AgentRunResult
from ahra.workflow_a_cli import (
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
            self.assertEqual(raised.exception.to_dict()["data"]["expectedOutput"], REQUIREMENT_DRAFT_OUTPUT)
            self.assertFalse(request_draft.exists())

            snapshot = read_snapshot(session_path=session)["snapshot"]
            self.assertEqual(snapshot["stage"], "frozen")
            self.assertEqual(snapshot["turns"][-1]["actor"], "agent:error")
            self.assertEqual(snapshot["turns"][-1]["error"]["code"], "agent_driver_timeout")


class HangingDriver:
    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        await asyncio.Event().wait()
        raise AssertionError(f"unexpected completion for {request.expected_output}")


if __name__ == "__main__":
    unittest.main()
