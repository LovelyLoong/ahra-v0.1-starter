from __future__ import annotations

import asyncio
import unittest
from pathlib import Path

from ahra.alignment_session import (
    ACCEPTANCE_DRAFT_OUTPUT,
    ALIGNMENT_DECISION_OUTPUT,
    REQUIREMENT_DRAFT_OUTPUT,
    AlignmentSessionError,
    AlignmentSessionManager,
    AlignmentSessionSnapshot,
)
from ahra.approval_service import ApprovalService
from ahra.goal_operations import GoalExecutionRequest
from ahra.intent_draft import IntentDraft
from ahra.ports import AgentRunRequest, AgentRunResult
from ahra.request_admission import RequestDraftAdmission
from ahra.request_draft import RequestDraft
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

        self.assertEqual(resumed.stage, "awaiting_requirement_approval")
        self.assertEqual(len(resumed.turns), 4)
        self.assertEqual(resumed.turns[0].message, "Keep scope local.")
        self.assertEqual(
            resumed.frozen_requirement,
            "Write one governed deterministic summary artifact in the local workspace.",
        )
        approved = manager.approve_requirement(resumed, actor="human:maintainer")
        self.assertEqual(approved.stage, "frozen")
        self.assertEqual(approved.requirement_approved_by, "human:maintainer")

    def test_convergence_outputs_untrusted_request_draft(self) -> None:
        driver = FakeAlignmentDriver()
        manager = AlignmentSessionManager(driver)
        snapshot = manager.start(_intent())
        snapshot = asyncio.run(manager.advance(snapshot, "Keep scope local."))
        snapshot = asyncio.run(manager.advance(snapshot, "Freeze that boundary."))
        snapshot = manager.approve_requirement(snapshot, actor="human:maintainer")

        result = asyncio.run(manager.draft_request(snapshot))

        self.assertIsInstance(result.request_draft, RequestDraft)
        self.assertNotIsInstance(result.request_draft, GoalExecutionRequest)
        self.assertEqual(result.request_draft.to_mapping()["kind"], "RequestDraft")
        self.assertIn(REQUIREMENT_DRAFT_OUTPUT, [call.expected_output for call in driver.calls])
        self.assertIn(ACCEPTANCE_DRAFT_OUTPUT, [call.expected_output for call in driver.calls])
        self.assertFalse(hasattr(result.request_draft, "to_goal_execution_request_mapping"))

    def test_run_emits_request_draft_after_explicit_requirement_approval(self) -> None:
        driver = FakeAlignmentDriver()
        manager = AlignmentSessionManager(driver)

        result = asyncio.run(
            manager.run(
                _intent(),
                ["Keep scope local.", "Freeze that boundary."],
                requirement_approval_actor="human:maintainer",
            )
        )

        self.assertIsInstance(result.request_draft, RequestDraft)
        self.assertNotIsInstance(result.request_draft, GoalExecutionRequest)
        self.assertEqual(result.snapshot.stage, "request_drafted")
        self.assertEqual(result.snapshot.requirement_approved_by, "human:maintainer")

    def test_request_draft_passes_admission(self) -> None:
        driver = FakeAlignmentDriver()
        manager = AlignmentSessionManager(driver)
        snapshot = manager.start(_intent())
        snapshot = asyncio.run(manager.advance(snapshot, "Keep scope local."))
        snapshot = asyncio.run(manager.advance(snapshot, "Requirement boundary complete."))
        snapshot = manager.approve_requirement(snapshot, actor="human:maintainer")

        result = asyncio.run(manager.draft_request(snapshot))
        admission = RequestDraftAdmission().evaluate(result.request_draft)

        self.assertTrue(admission.accepted, [rejection.to_dict() for rejection in admission.rejections])
        self.assertTrue(admission.plan_digest)

    def test_draft_request_requires_human_requirement_approval(self) -> None:
        driver = FakeAlignmentDriver()
        manager = AlignmentSessionManager(driver)
        snapshot = manager.start(_intent())
        snapshot = asyncio.run(manager.advance(snapshot, "Keep scope local."))
        snapshot = asyncio.run(manager.advance(snapshot, "Requirement boundary complete."))

        with self.assertRaises(AlignmentSessionError) as raised:
            asyncio.run(manager.draft_request(snapshot))

        self.assertEqual(raised.exception.code, "requirement_not_approved")

    def test_requirement_approval_requires_human_actor(self) -> None:
        driver = FakeAlignmentDriver()
        manager = AlignmentSessionManager(driver)
        snapshot = manager.start(_intent())
        snapshot = asyncio.run(manager.advance(snapshot, "Keep scope local."))
        snapshot = asyncio.run(manager.advance(snapshot, "Requirement boundary complete."))

        with self.assertRaises(AlignmentSessionError) as raised:
            manager.approve_requirement(snapshot, actor="agent:alignment")

        self.assertEqual(raised.exception.code, "requirement_approval_requires_human")

    def test_draft_request_requests_contract_authorization(self) -> None:
        driver = FakeAlignmentDriver()
        manager = AlignmentSessionManager(driver)
        approval_service = ApprovalService()
        snapshot = _frozen_snapshot(manager)

        result = asyncio.run(manager.draft_request(snapshot, approval_service=approval_service))

        self.assertIsNotNone(result.approval_record)
        assert result.approval_record is not None
        self.assertEqual(result.approval_record.status, "waiting_auth")
        with self.assertRaisesRegex(ValueError, "before approval"):
            approval_service.freeze(result.request_draft, approval_id=result.approval_record.approval_id)
        with self.assertRaisesRegex(ValueError, "self-authorize"):
            approval_service.approve(result.approval_record.approval_id, actor=result.request_draft.producer_actor)
        approval_service.approve(result.approval_record.approval_id, actor="human:maintainer")
        self.assertIsInstance(
            approval_service.freeze(result.request_draft, approval_id=result.approval_record.approval_id),
            GoalExecutionRequest,
        )

    def test_requirement_agent_without_plan_draft_fails_closed(self) -> None:
        driver = FakeAlignmentDriver(requirement_output={"summary": "No explicit plan."})
        manager = AlignmentSessionManager(driver)
        snapshot = _frozen_snapshot(manager)

        with self.assertRaises(AlignmentSessionError) as raised:
            asyncio.run(manager.draft_request(snapshot))

        self.assertEqual(raised.exception.code, "missing_plan_draft")
        self.assertEqual(raised.exception.ref, "agentOutput.planDraft")

    def test_acceptance_agent_without_claim_graph_fails_closed(self) -> None:
        driver = FakeAlignmentDriver(acceptance_output={"summary": "No explicit claims."})
        manager = AlignmentSessionManager(driver)
        snapshot = _frozen_snapshot(manager)

        with self.assertRaises(AlignmentSessionError) as raised:
            asyncio.run(manager.draft_request(snapshot))

        self.assertEqual(raised.exception.code, "missing_claim_graph")
        self.assertEqual(raised.exception.ref, "agentOutput.claimGraph")

    def test_hanging_agent_timeout_records_resumable_snapshot(self) -> None:
        manager = AlignmentSessionManager(HangingAlignmentDriver(), agent_timeout_seconds=0.01)
        snapshot = manager.start(_intent())

        with self.assertRaises(AlignmentSessionError) as raised:
            asyncio.run(manager.advance(snapshot, "This driver will not finish."))

        self.assertEqual(raised.exception.code, "agent_driver_timeout")
        self.assertEqual(raised.exception.to_dict()["data"]["expectedOutput"], ALIGNMENT_DECISION_OUTPUT)
        timed_out = raised.exception.snapshot
        self.assertIsInstance(timed_out, AlignmentSessionSnapshot)
        assert isinstance(timed_out, AlignmentSessionSnapshot)
        self.assertEqual(timed_out.stage, "awaiting_user")
        self.assertEqual(timed_out.turns[-1].actor, "agent:error")
        self.assertEqual(timed_out.turns[-1].error["code"], "agent_driver_timeout")

        resumed = asyncio.run(AlignmentSessionManager(FakeAlignmentDriver()).advance(timed_out, "Try again."))

        self.assertEqual(resumed.stage, "awaiting_user")


class HangingAlignmentDriver:
    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        await asyncio.Event().wait()
        raise AssertionError(f"unexpected completion for {request.expected_output}")


class FakeAlignmentDriver:
    def __init__(
        self,
        *,
        requirement_output: dict[str, object] | None = None,
        acceptance_output: dict[str, object] | None = None,
    ) -> None:
        self.calls: list[AgentRunRequest] = []
        self.alignment_turns = 0
        self.requirement_output = requirement_output
        self.acceptance_output = acceptance_output

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
            return AgentRunResult(output=self.requirement_output or _requirement_output())
        if request.expected_output == ACCEPTANCE_DRAFT_OUTPUT:
            return AgentRunResult(output=self.acceptance_output or _acceptance_output())
        raise AssertionError(f"unexpected expected_output {request.expected_output}")


def _frozen_snapshot(manager: AlignmentSessionManager) -> AlignmentSessionSnapshot:
    snapshot = manager.start(_intent())
    snapshot = asyncio.run(manager.advance(snapshot, "Keep scope local."))
    snapshot = asyncio.run(manager.advance(snapshot, "Done means summary artifact exists."))
    return manager.approve_requirement(snapshot, actor="human:maintainer")


def _requirement_output() -> dict[str, object]:
    return {
        "summary": "Write one governed deterministic summary artifact in the local workspace.",
        "planDraft": {
            "apiVersion": "ahra.dev/v1alpha1",
            "kind": "PlanDraft",
            "metadata": {
                "goalId": "GOAL-PHASE1-EXAMPLE-ALIGNED",
                "proposedBy": "planner/alignment-session-test",
            },
            "spec": {
                "rationale": "Single bounded node writes the requested summary artifact.",
                "nodes": [
                    {
                        "id": "NODE-write-summary",
                        "nodeType": "bounded_task",
                        "objective": "Write the governed deterministic summary artifact.",
                        "claimRefs": ["CLAIM-summary-artifact"],
                        "dependsOn": [],
                        "inputRefs": [],
                        "expectedOutputs": [
                            {
                                "name": "summary-artifact",
                                "schemaRef": "ahra/artifact/text/0.1",
                                "consumerNodeRefs": ["NODE-goal-verification"],
                                "artifactRequired": True,
                            }
                        ],
                        "capabilityRequests": [
                            {
                                "capability": "filesystem.write",
                                "resources": ["outputs/summary.txt"],
                                "riskLevel": "R1",
                            }
                        ],
                        "gateRefs": ["GATE-alignment-objective"],
                        "runtimeRef": "runtime/local-goal@sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
                        "budgetRequest": {
                            "maxModelCalls": 1,
                            "maxToolCalls": 2,
                            "maxSpawnedNodes": 0,
                            "maxWallSeconds": 60,
                            "maxCostUsd": 0.0,
                        },
                        "retryPolicy": {
                            "maxAttempts": 1,
                            "retryableFailureClasses": [],
                            "idempotencyKeyRequired": False,
                        },
                        "timeoutSeconds": 60,
                        "sideEffect": "idempotent",
                    },
                    {
                        "id": "NODE-goal-verification",
                        "nodeType": "goal_verification",
                        "objective": "Verify the summary artifact satisfies the frozen requirement.",
                        "claimRefs": ["CLAIM-summary-artifact"],
                        "dependsOn": ["NODE-write-summary"],
                        "inputRefs": ["NODE-write-summary"],
                        "expectedOutputs": [],
                        "capabilityRequests": [],
                        "gateRefs": ["GATE-alignment-complete"],
                        "runtimeRef": "runtime/local-goal@sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
                        "budgetRequest": {
                            "maxModelCalls": 1,
                            "maxToolCalls": 1,
                            "maxSpawnedNodes": 0,
                            "maxWallSeconds": 30,
                            "maxCostUsd": 0.0,
                        },
                        "retryPolicy": {
                            "maxAttempts": 1,
                            "retryableFailureClasses": [],
                            "idempotencyKeyRequired": False,
                        },
                        "timeoutSeconds": 30,
                        "sideEffect": "idempotent",
                        "terminalGoalVerification": True,
                    }
                ],
            },
        },
    }


def _acceptance_output() -> dict[str, object]:
    return {
        "summary": "Acceptance requires governed evidence for the deterministic summary artifact.",
        "claimGraph": {
            "apiVersion": "ahra.dev/v1alpha1",
            "kind": "ClaimGraph",
            "metadata": {
                "name": "alignment-session-test-claims",
                "goalId": "GOAL-PHASE1-EXAMPLE-ALIGNED",
                "version": 1,
            },
            "spec": {
                "goalRef": "GOAL-PHASE1-EXAMPLE-ALIGNED",
                "claims": [
                    {
                        "id": "CLAIM-summary-artifact",
                        "type": "functional",
                        "statement": "A deterministic summary artifact is produced in the local workspace.",
                        "criterionRefs": ["CRIT-summary-artifact"],
                        "dependsOn": [],
                        "riskLevel": "R1",
                        "required": True,
                        "requiredEvidenceKinds": ["artifact"],
                        "gateRefs": ["GATE-alignment-objective"],
                    }
                ],
            },
        },
    }


def _intent() -> IntentDraft:
    return IntentDraft.from_mapping(load_document(EXAMPLE))


if __name__ == "__main__":
    unittest.main()
