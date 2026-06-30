from __future__ import annotations

import asyncio
import tempfile
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ahra.alignment_engine import AlignmentError, AlignmentWorkflowEngine
from ahra.approval_service import ApprovalService
from ahra.capabilities import CapabilityAdmissionService, CapabilityRequest, CapabilityScope, InMemoryAuditSink, LocalRuntimeGateway, RuntimeCapabilityProfile
from ahra.evidence_v2 import DigestRef, EvidenceEnvironment
from ahra.intent_draft import IntentCapabilityNeed
from ahra.request_admission import RequestDraftAdmission
from ahra.verification import GateExecutionRequest, GateExecutionStatus, GateLevel, SemanticReviewGateRunner, SubjectiveGateDecision
from tests.phase1_helpers import example_intent, network_intent_with_policy, start_goal


D1 = "sha256:" + "1" * 64
D2 = "sha256:" + "2" * 64
D3 = "sha256:" + "3" * 64
D4 = "sha256:" + "4" * 64


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

        now = datetime(2026, 6, 30, 10, 0, tzinfo=UTC)
        grant = CapabilityAdmissionService(
            goal_scope=CapabilityScope(
                allowed_actions={"network.access": ("https://example.invalid/status",)},
                allowed_roles_by_action={"network.access": ("executor",)},
            ),
            runtime_profile=RuntimeCapabilityProfile(
                runtime_ref="runtime/local-test",
                supported_actions=frozenset({"network.access"}),
            ),
        ).admit(
            CapabilityRequest(
                request_id="CREQ-phase1-network",
                plan_id="PLAN-phase1-network",
                node_id="NODE-phase1-network",
                requested_by="agent:test",
                role="executor",
                capability="network.access",
                action="network.access",
                resources=("https://example.invalid/status",),
                scope=("https://example.invalid/status",),
                risk_level="R2",
                expires_at=now + timedelta(minutes=5),
                approval_refs=("APR-network",),
            ),
            now=now,
        ).grant
        assert grant is not None
        audit = InMemoryAuditSink()
        record = LocalRuntimeGateway(Path("."), audit).record_network_access(
            grant,
            plan_id="PLAN-phase1-network",
            node_id="NODE-phase1-network",
            actor="executor",
            resource="https://example.invalid/status",
            request_summary={"method": "GET", "payload": "redacted"},
            response_summary={"status": 200, "bodyDigest": D4},
            now=now,
        )

        self.assertTrue(record.allowed)
        self.assertEqual(record.resource_scope, ("https://example.invalid/status",))
        self.assertIsNotNone(record.evidence_summary)

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
        engine = AlignmentWorkflowEngine()
        session = engine.start(example_intent())
        stages = []
        for message in ("refine scope", "draft claims", "draft plan"):
            stages.append(session.stage)
            session = engine.advance(session, actor="agent:alignment", message=message)
        self.assertEqual(stages, ["refining_scope", "drafting_claims", "drafting_plan"])
        self.assertEqual(session.stage, "ready")

        with self.assertRaises(AlignmentError):
            engine.draft_request(session, profile_ref="profile/out-of-envelope@sha256:" + "9" * 64)

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
    engine = AlignmentWorkflowEngine()
    session = engine.start(intent)
    for message in ("scope", "claims", "plan"):
        session = engine.advance(session, actor="agent:alignment", message=message)
    return engine.draft_request(session, producer_actor="agent:producer")


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
