from __future__ import annotations

import unittest
from pathlib import Path

from ahra.alignment_engine import AlignmentError, AlignmentWorkflowEngine, RequestDraft
from ahra.goal_operations import GoalExecutionRequest
from ahra.intent_draft import IntentDraft
from ahra.validation import load_document


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "intents" / "phase1-example-intent.yaml"


class AlignmentWorkflowEngineTests(unittest.TestCase):
    def test_multi_turn_alignment_emits_untrusted_request_draft(self) -> None:
        engine = AlignmentWorkflowEngine()
        session = engine.start(_intent())
        session = engine.advance(session, actor="human:maintainer", message="Keep the scope local.")
        session = engine.advance(session, actor="agent:alignment", message="Draft objective and governance claims.")
        session = engine.advance(session, actor="agent:alignment", message="Draft a deterministic PlanDraft.")

        draft = engine.draft_request(session, producer_actor="agent:producer")

        self.assertIsInstance(draft, RequestDraft)
        self.assertNotIsInstance(draft, GoalExecutionRequest)
        self.assertEqual(draft.producer_actor, "agent:producer")
        self.assertEqual(draft.plan_draft.goal_ref, draft.goal_ref)
        self.assertIn("filesystem.write", draft.allowed_capabilities)

    def test_unknown_profile_ref_is_rejected_instead_of_fabricating_digest(self) -> None:
        engine = AlignmentWorkflowEngine()
        session = engine.start(_intent())
        for message in ("scope", "claims", "plan"):
            session = engine.advance(session, actor="agent:alignment", message=message)

        with self.assertRaises(AlignmentError) as ctx:
            engine.draft_request(
                session,
                profile_ref="profile/unknown@sha256:" + "9" * 64,
            )

        self.assertEqual(ctx.exception.code, "unknown_profile_ref")


def _intent() -> IntentDraft:
    return IntentDraft.from_mapping(load_document(EXAMPLE))


if __name__ == "__main__":
    unittest.main()
