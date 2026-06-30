from __future__ import annotations

import unittest
from pathlib import Path

from ahra.alignment_engine import AlignmentError, AlignmentWorkflowEngine, RequestDraft
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
        self.assertEqual(draft.producer_actor, "agent:producer")
        self.assertEqual(draft.plan_draft.goal_ref, draft.goal_ref)
        self.assertIn("filesystem.write", draft.allowed_capabilities)
        self.assertFalse(hasattr(draft, "to_goal_execution_request_mapping"))
        self.assertEqual(draft.to_mapping()["kind"], "RequestDraft")

    def test_dialogue_variation_converges_to_same_request_draft(self) -> None:
        engine = AlignmentWorkflowEngine()
        first = engine.start(_intent())
        second = engine.start(_intent())
        for actor, message in (
            ("human:maintainer", "Keep the scope local."),
            ("agent:alignment", "Draft claims now."),
            ("agent:alignment", "Draft plan now."),
        ):
            first = engine.advance(first, actor=actor, message=message)
        for actor, message in (
            ("human:maintainer", "Same intent, different wording."),
            ("agent:alignment", "A different dialogue transcript."),
            ("agent:alignment", "Still ready to freeze the deterministic draft."),
        ):
            second = engine.advance(second, actor=actor, message=message)

        first_draft = engine.draft_request(first, producer_actor="agent:producer")
        second_draft = engine.draft_request(second, producer_actor="agent:producer")

        self.assertNotEqual(first.to_mapping()["turns"], second.to_mapping()["turns"])
        self.assertEqual(first_draft.request_id, second_draft.request_id)
        self.assertEqual(first_draft.to_mapping(), second_draft.to_mapping())

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
