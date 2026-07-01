from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path

from ahra.approval_service import ApprovalService
from ahra.goal_operations import GoalExecutionRequest
from ahra.intent_draft import IntentDraft
from ahra.ports import ApprovalService as ApprovalServicePort
from ahra.request_admission import RequestDraftAdmission
from ahra.validation import load_document
from tests.phase1_helpers import request_draft_from_intent


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "intents" / "phase1-example-intent.yaml"
NOW = datetime(2026, 6, 30, 10, 0, tzinfo=UTC)


class ApprovalServiceTests(unittest.TestCase):
    def test_implements_approval_service_port(self) -> None:
        draft = _accepted_draft()
        service = ApprovalService(clock=lambda: NOW)

        port: ApprovalServicePort = service
        approval = port.request_authorization(draft, actor="agent:producer")

        self.assertIsInstance(service, ApprovalServicePort)
        self.assertEqual(port.status(approval.approval_id), "waiting_auth")

        port.approve(approval.approval_id, actor="human:maintainer")
        self.assertIsInstance(port.freeze(draft, approval_id=approval.approval_id), GoalExecutionRequest)

    def test_waiting_auth_approval_freezes_goal_execution_request(self) -> None:
        draft = _accepted_draft()
        service = ApprovalService(clock=lambda: NOW)
        approval = service.request_authorization(draft, actor="agent:producer")

        self.assertEqual(approval.status, "waiting_auth")
        with self.assertRaisesRegex(ValueError, "before approval"):
            service.freeze(draft, approval_id=approval.approval_id)

        approved = service.approve(approval.approval_id, actor="human:maintainer")
        frozen = service.freeze(draft, approval_id=approval.approval_id)

        self.assertEqual(approved.status, "approved")
        self.assertIsInstance(frozen, GoalExecutionRequest)
        self.assertEqual(frozen.goal_ref, draft.goal_ref)
        self.assertEqual([event.event_type for event in service.events], ["approval_requested", "approval_granted"])
        self.assertEqual(service.events[-1].actor, "human:maintainer")
        self.assertEqual(service.events[-1].occurred_at, NOW)

    def test_producer_cannot_self_authorize(self) -> None:
        draft = _accepted_draft()
        service = ApprovalService(clock=lambda: NOW)
        approval = service.request_authorization(draft, actor="agent:producer")

        with self.assertRaisesRegex(ValueError, "self-authorize"):
            service.approve(approval.approval_id, actor="agent:producer")


def _accepted_draft():
    intent = IntentDraft.from_mapping(load_document(EXAMPLE))
    draft = request_draft_from_intent(ROOT / ".tmp-phase1-approval", intent)
    RequestDraftAdmission().require_accepted(draft)
    return draft


if __name__ == "__main__":
    unittest.main()
