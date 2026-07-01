from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path

from ahra.acceptance_contracts import ClaimGraph
from ahra.intent_draft import IntentCapabilityNeed, IntentDraft
from ahra.request_admission import RequestDraftAdmission
from ahra.validation import load_document
from tests.phase1_helpers import request_draft_from_intent


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "intents" / "phase1-example-intent.yaml"


class RequestDraftAdmissionTests(unittest.TestCase):
    def test_valid_request_draft_is_accepted_with_plan_digest(self) -> None:
        draft = _draft(_intent())

        result = RequestDraftAdmission().evaluate(draft)

        self.assertTrue(result.accepted)
        self.assertTrue(result.plan_digest and result.plan_digest.startswith("sha256:"))
        self.assertEqual(result.rejections, ())

    def test_unknown_digest_is_rejected(self) -> None:
        draft = replace(_draft(_intent()), runtime_digest="sha256:not-a-digest")

        result = RequestDraftAdmission().evaluate(draft)

        self.assertFalse(result.accepted)
        self.assertIn("invalid_digest", {rejection.code for rejection in result.rejections})

    def test_untrusted_registry_digest_is_rejected(self) -> None:
        draft = _draft(_intent())
        forged = replace(
            draft,
            registered_node_types={**draft.registered_node_types, "bounded_task": "sha256:" + "9" * 64},
            registered_gate_refs={**draft.registered_gate_refs, "GATE-alignment-complete": "sha256:" + "8" * 64},
        )

        result = RequestDraftAdmission().evaluate(forged)

        self.assertFalse(result.accepted)
        codes = {rejection.code for rejection in result.rejections}
        self.assertIn("node_digest_mismatch", codes)
        self.assertIn("gate_digest_mismatch", codes)
        self.assertIsNone(result.plan_digest)

    def test_high_risk_capability_without_policy_is_rejected(self) -> None:
        intent = replace(
            _intent(),
            capability_needs=(
                IntentCapabilityNeed(
                    action="network.access",
                    resources=("https://example.invalid/status",),
                    risk_level="R2",
                ),
            ),
        )

        result = RequestDraftAdmission().evaluate(_draft(intent))

        self.assertFalse(result.accepted)
        self.assertIn("high_risk_capability_requires_policy", {rejection.code for rejection in result.rejections})

    def test_cyclic_claim_graph_is_rejected(self) -> None:
        draft = _draft(_intent())
        first, second = draft.claim_graph.claims
        cyclic_graph = ClaimGraph(
            goal_ref=draft.goal_ref,
            version=1,
            claims=(
                replace(first, depends_on=(second.claim_id,)),
                replace(second, depends_on=(first.claim_id,)),
            ),
        )

        result = RequestDraftAdmission().evaluate(replace(draft, claim_graph=cyclic_graph))

        self.assertFalse(result.accepted)
        self.assertIn("cyclic_claim_graph", {rejection.code for rejection in result.rejections})


def _intent() -> IntentDraft:
    return IntentDraft.from_mapping(load_document(EXAMPLE))


def _draft(intent: IntentDraft):
    return request_draft_from_intent(ROOT / ".tmp-phase1-request-admission", intent)


if __name__ == "__main__":
    unittest.main()
