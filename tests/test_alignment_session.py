from __future__ import annotations

import asyncio
import unittest
from pathlib import Path

from ahra.alignment_engine import RequestDraft
from ahra.alignment_session import (
    ACCEPTANCE_DRAFT_OUTPUT,
    ALIGNMENT_DECISION_OUTPUT,
    REQUIREMENT_DRAFT_OUTPUT,
    AlignmentSessionError,
    AlignmentSessionManager,
    AlignmentSessionSnapshot,
)
from ahra.goal_operations import GoalExecutionRequest
from ahra.intent_draft import IntentDraft
from ahra.ports import AgentRunRequest, AgentRunResult
from ahra.request_admission import RequestDraftAdmission
from ahra.validation import load_document


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "intents" / "phase1-example-intent.yaml"


class AlignmentSessionManagerTests(unittest.TestCase):
    def test_agent_driven_dialogue_is_invoked(self) -> None:
        driver = FakeAlignmentDriver()
        manager = AlignmentSessionManager(driver)
        snapshot = manager.start(_intent())

        snapshot = asyncio.run(manager.advance(snapshot, "Keep scope local."))

        self.assertEqual(driver.calls[0].expected_output, ALIGNMENT_DECISION_OUTPUT)
        self.assertEqual(driver.calls[0].payload["userMessage"], "Keep scope local.")
        self.assertEqual(snapshot.turns[-1].actor, "agent:alignment")
        self.assertEqual(snapshot.stage, "awaiting_user")

    def test_unknown_digest_is_rejected_before_agent_invocation(self) -> None:
        driver = FakeAlignmentDriver()
        manager = AlignmentSessionManager(driver)

        with self.assertRaises(AlignmentSessionError) as raised:
            manager.start(_intent(), runtime_digest="sha256:" + "9" * 64)

        self.assertEqual(raised.exception.code, "runtime_digest_mismatch")
        self.assertEqual(driver.calls, [])

    def test_resume_from_snapshot_works(self) -> None:
        driver = FakeAlignmentDriver()
        manager = AlignmentSessionManager(driver)
        snapshot = manager.start(_intent())
        snapshot = asyncio.run(manager.advance(snapshot, "Keep scope local."))
        restored = AlignmentSessionSnapshot.from_mapping(snapshot.to_mapping())

        resumed = asyncio.run(manager.advance(restored, "Freeze that boundary."))

        self.assertEqual(resumed.stage, "frozen")
        self.assertEqual(len(resumed.turns), 4)
        self.assertEqual(resumed.turns[0].message, "Keep scope local.")
        self.assertEqual(resumed.frozen_requirement, "Write one governed deterministic summary artifact in the local workspace.")

    def test_convergence_outputs_untrusted_request_draft(self) -> None:
        driver = FakeAlignmentDriver()
        manager = AlignmentSessionManager(driver)
        snapshot = manager.start(_intent())
        snapshot = asyncio.run(manager.advance(snapshot, "Keep scope local."))
        snapshot = asyncio.run(manager.advance(snapshot, "Freeze that boundary."))

        result = asyncio.run(manager.draft_request(snapshot))

        self.assertIsInstance(result.request_draft, RequestDraft)
        self.assertNotIsInstance(result.request_draft, GoalExecutionRequest)
        self.assertEqual(result.request_draft.to_mapping()["kind"], "RequestDraft")
        self.assertIn(REQUIREMENT_DRAFT_OUTPUT, [call.expected_output for call in driver.calls])
        self.assertIn(ACCEPTANCE_DRAFT_OUTPUT, [call.expected_output for call in driver.calls])
        self.assertFalse(hasattr(result.request_draft, "to_goal_execution_request_mapping"))

    def test_request_draft_passes_admission(self) -> None:
        driver = FakeAlignmentDriver()
        manager = AlignmentSessionManager(driver)
        snapshot = manager.start(_intent())
        snapshot = asyncio.run(manager.advance(snapshot, "Keep scope local."))
        snapshot = asyncio.run(manager.advance(snapshot, "Requirement boundary complete."))

        result = asyncio.run(manager.draft_request(snapshot))
        admission = RequestDraftAdmission().evaluate(result.request_draft)

        self.assertTrue(admission.accepted, [rejection.to_dict() for rejection in admission.rejections])
        self.assertTrue(admission.plan_digest)


class FakeAlignmentDriver:
    def __init__(self) -> None:
        self.calls: list[AgentRunRequest] = []
        self.alignment_turns = 0

    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        self.calls.append(request)
        if request.expected_output == ALIGNMENT_DECISION_OUTPUT:
            self.alignment_turns += 1
            if self.alignment_turns == 1:
                return AgentRunResult(
                    output={
                        "message": "Need the completion signal before freezing.",
                        "converged": False,
                        "missingDimensions": ["completion signal"],
                    }
                )
            return AgentRunResult(
                output={
                    "message": "Requirement boundary frozen.",
                    "converged": True,
                    "frozenRequirement": "Write one governed deterministic summary artifact in the local workspace.",
                    "missingDimensions": [],
                }
            )
        if request.expected_output == REQUIREMENT_DRAFT_OUTPUT:
            return AgentRunResult(
                output={
                    "summary": "Write one governed deterministic summary artifact in the local workspace.",
                }
            )
        if request.expected_output == ACCEPTANCE_DRAFT_OUTPUT:
            return AgentRunResult(
                output={
                    "summary": "Acceptance requires governed evidence for the deterministic summary artifact.",
                }
            )
        raise AssertionError(f"unexpected expected_output {request.expected_output}")


def _intent() -> IntentDraft:
    return IntentDraft.from_mapping(load_document(EXAMPLE))


if __name__ == "__main__":
    unittest.main()
