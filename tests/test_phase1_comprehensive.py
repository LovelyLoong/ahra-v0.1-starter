from __future__ import annotations

import asyncio
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from ahra.alignment_session import AlignmentSessionError, AlignmentSessionManager
from ahra.approval_service import ApprovalService
from ahra.evidence_v2 import DigestRef, EvidenceEnvironment
from ahra.intent_draft import IntentCapabilityNeed
from ahra.request_admission import RequestDraftAdmission
from ahra.verification import GateExecutionRequest, GateExecutionStatus, GateLevel, SemanticReviewGateRunner, SubjectiveGateDecision
from tests.phase1_helpers import _Phase1AlignmentDriver, example_intent, network_intent_with_policy, request_draft_from_intent, start_goal


D1 = "sha256:" + "1" * 64
D2 = "sha256:" + "2" * 64
D3 = "sha256:" + "3" * 64
D4 = "sha256:" + "4" * 64
ROOT = Path(__file__).resolve().parents[1]


class Phase1ComprehensiveTests(unittest.TestCase):
    def test_scenario_1_objective_goal_passes_command_gate_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            result = start_goal(Path(temp))

        self.assertEqual(result["goalStatus"], "succeeded")
        self.assertEqual(result["planStatus"], "succeeded")
        self.assertTrue(result["completion"]["complete"])

    def test_scenario_2_network_goal_has_governed_admission_audit_and_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            result = start_goal(Path(temp), network_intent_with_policy())

        self.assertEqual(result["goalStatus"], "succeeded")
        self.assertGreaterEqual(result["inspect"]["metrics"]["capabilityGrantRefCount"], 2)
        network_audits = [
            audit
            for record in result["inspect"]["idempotencyRecords"]
            for audit in record["result"]["spec"]["details"].get("networkAccessAudits", [])
        ]

        self.assertTrue(network_audits)
        self.assertEqual(
            sorted({scope for audit in network_audits for scope in audit["spec"].get("resourceScope", [])}),
            ["https://example.invalid/status"],
        )
        self.assertTrue(all(audit["spec"]["action"] == "network.access" for audit in network_audits))
        self.assertTrue(all(audit["spec"]["allowed"] for audit in network_audits))
        self.assertTrue(all(audit["spec"]["policyDecisionId"] for audit in network_audits))

    def test_network_goal_outside_runtime_egress_policy_fails_admission(self) -> None:
        intent = example_intent(
            capability_needs=(
                IntentCapabilityNeed(
                    action="network.access",
                    resources=("https://blocked.invalid/status",),
                    reason="Probe an egress target outside the local runtime policy.",
                    risk_level="R2",
                    policy_refs=("POLICY-network-test",),
                ),
                IntentCapabilityNeed(
                    action="filesystem.write",
                    resources=("outputs/summary.txt",),
                    reason="Persist the governed network summary.",
                    risk_level="R1",
                ),
            ),
            risk_hint="R2",
        )

        with tempfile.TemporaryDirectory() as temp:
            result = start_goal(Path(temp), intent)

        self.assertEqual(result["goalStatus"], "failed")
        self.assertEqual(result["planStatus"], "failed")
        failed_nodes = [node for node in result["inspect"]["nodeRuns"] if node["status"] == "failed"]
        self.assertEqual(len(failed_nodes), 1)
        self.assertEqual(failed_nodes[0]["failure_class"], "capability_admission_denied")
        self.assertIn("runtime_egress_not_allowed", failed_nodes[0]["message"])

    def test_scenario_3_subjective_goal_records_semantic_review_lineage(self) -> None:
        runner = SemanticReviewGateRunner(
            lambda request: SubjectiveGateDecision(
                verdict="pass",
                confidence=0.95,
                rationale=f"{request.gate_ref} passed fixture semantic review.",
                verifier_identity="agent:judge",
                trace_ref="trace://phase1-semantic",
            ),
            verifier_identity="agent:judge",
        )

        result = asyncio.run(runner.run(_subjective_request()))

        self.assertEqual(result.status, GateExecutionStatus.PASSED)
        self.assertIn("verifier:agent:judge", result.artifact_refs)
        self.assertEqual(result.raw_output_ref, "trace://phase1-semantic")

    def test_scenario_4_authorization_boundary_rejects_unapproved_and_self_authorized_freeze(self) -> None:
        draft = _draft(example_intent())
        RequestDraftAdmission().require_accepted(draft)
        approvals = ApprovalService()
        approval = approvals.request_authorization(draft, actor="agent:producer")

        with self.assertRaisesRegex(ValueError, "before approval"):
            approvals.freeze(draft, approval_id=approval.approval_id)
        with self.assertRaisesRegex(ValueError, "self-authorize"):
            approvals.approve(approval.approval_id, actor="agent:producer")

    def test_scenario_5_multi_turn_alignment_refines_and_rejects_out_of_envelope_request(self) -> None:
        manager = AlignmentSessionManager(_Phase1AlignmentDriver(example_intent()))

        with self.assertRaises(AlignmentSessionError):
            manager.start(example_intent(), profile_ref="profile/out-of-envelope@sha256:" + "9" * 64)

        risky_intent = replace(
            example_intent(),
            capability_needs=(
                IntentCapabilityNeed(
                    action="network.access",
                    resources=("https://example.invalid/status",),
                    risk_level="R2",
                ),
            ),
            risk_hint="R2",
        )
        result = RequestDraftAdmission().evaluate(_draft(risky_intent))
        self.assertFalse(result.accepted)
        self.assertIn("high_risk_capability_requires_policy", {rejection.code for rejection in result.rejections})


def _draft(intent):
    return request_draft_from_intent(ROOT / ".tmp-phase1-comprehensive", intent)


def _subjective_request() -> GateExecutionRequest:
    return GateExecutionRequest(
        goal_execution_id="GOAL-phase1-subjective",
        plan_execution_id="PEX-phase1-subjective",
        node_run_id="NRUN-phase1-subjective",
        gate_ref="GATE-phase1-semantic",
        gate_kind="semantic_review",
        runner_release_ref="semantic-review-fixture",
        gate_definition_digest=D1,
        claim_refs=("CLAIM-phase1-subjective",),
        level=GateLevel.L2,
        evidence_kind="semantic_review",
        subjects=(DigestRef("ART-phase1-subjective", D2),),
        dependency_evidence=(),
        environment=EvidenceEnvironment(
            runtime_profile_digest=D1,
            policy_digest=D2,
            verifier_release_digest=D3,
            test_definition_digest=D4,
        ),
        workspace_ref=None,
        idempotency_key="phase1-subjective",
        metadata={"producerIdentity": "agent:producer"},
    )


if __name__ == "__main__":
    unittest.main()
