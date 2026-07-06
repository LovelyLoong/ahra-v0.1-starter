from __future__ import annotations

import asyncio
import copy
import unittest
from pathlib import Path

from ahra.alignment_session import (
    ACCEPTANCE_DRAFT_OUTPUT,
    ALIGNMENT_DECISION_OUTPUT,
    CROSS_ALIGNMENT_REPORT_OUTPUT,
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
        self.assertIsNotNone(resumed.boundary_contract)
        self.assertEqual(resumed.boundary_contract_digest, resumed.boundary_contract.digest())
        self.assertEqual(
            resumed.to_mapping()["boundaryContract"]["spec"]["entries"][0]["kind"],
            "must",
        )
        approved = manager.approve_requirement(resumed, actor="human:maintainer")
        self.assertEqual(approved.stage, "frozen")
        self.assertEqual(approved.requirement_approved_by, "human:maintainer")
        self.assertEqual(approved.boundary_contract_digest, approved.boundary_contract.digest())

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
        requirement_call = next(call for call in driver.calls if call.expected_output == REQUIREMENT_DRAFT_OUTPUT)
        self.assertEqual(requirement_call.payload["boundaryContractDigest"], snapshot.boundary_contract_digest)
        self.assertEqual(
            requirement_call.payload["requirementTrace"]["frozenRequirement"],
            "Write one governed deterministic summary artifact in the local workspace.",
        )

    def test_draft_request_runs_acceptance_first_and_freezes_claim_graph_for_requirement(self) -> None:
        driver = FakeAlignmentDriver()
        manager = AlignmentSessionManager(driver)
        snapshot = _frozen_snapshot(manager)

        result = asyncio.run(manager.draft_request(snapshot))

        draft_calls = [
            call.expected_output
            for call in driver.calls
            if call.expected_output in {ACCEPTANCE_DRAFT_OUTPUT, REQUIREMENT_DRAFT_OUTPUT}
        ]
        self.assertEqual(draft_calls, [ACCEPTANCE_DRAFT_OUTPUT, REQUIREMENT_DRAFT_OUTPUT])
        acceptance_call = next(call for call in driver.calls if call.expected_output == ACCEPTANCE_DRAFT_OUTPUT)
        self.assertEqual(
            set(acceptance_call.payload),
            {
                "phase",
                "boundaryContract",
                "boundaryContractDigest",
                "redraftAttempt",
                "previousCrossAlignmentReport",
            },
        )
        self.assertEqual(acceptance_call.payload["boundaryContractDigest"], snapshot.boundary_contract_digest)
        self.assertEqual(acceptance_call.payload["redraftAttempt"], 0)
        self.assertIsNone(acceptance_call.payload["previousCrossAlignmentReport"])

        requirement_call = next(call for call in driver.calls if call.expected_output == REQUIREMENT_DRAFT_OUTPUT)
        frozen_claim_graph = result.request_draft.to_mapping()["spec"]["claimGraph"]
        self.assertEqual(requirement_call.payload["frozenClaimGraph"], frozen_claim_graph)
        self.assertEqual(requirement_call.payload["frozenClaimGraphDigest"], result.request_draft.claim_graph_digest)
        self.assertEqual(requirement_call.payload["readOnlyInputs"]["claimGraph"], frozen_claim_graph)
        self.assertEqual(result.snapshot.frozen_claim_graph_digest, result.request_draft.claim_graph_digest)

        restored = AlignmentSessionSnapshot.from_mapping(result.snapshot.to_mapping())
        self.assertEqual(restored.frozen_claim_graph_digest, result.snapshot.frozen_claim_graph_digest)

    def test_acceptance_claim_criterion_refs_must_resolve_to_boundary_entries(self) -> None:
        acceptance_output = copy.deepcopy(_acceptance_output())
        acceptance_output["claimGraph"]["spec"]["claims"][0]["criterionRefs"] = ["CRIT-summary-artifact"]
        driver = FakeAlignmentDriver(acceptance_output=acceptance_output)
        manager = AlignmentSessionManager(driver, max_cross_alignment_redrafts=0)
        snapshot = _frozen_snapshot(manager)

        with self.assertRaises(AlignmentSessionError) as raised:
            asyncio.run(manager.draft_request(snapshot))

        self.assertEqual(raised.exception.code, "cross_alignment_redraft_exhausted")
        failed = raised.exception.snapshot
        self.assertIsInstance(failed, AlignmentSessionSnapshot)
        assert isinstance(failed, AlignmentSessionSnapshot)
        report = failed.to_mapping()["crossAlignmentReport"]
        self.assertEqual(report["kind"], "CrossAlignmentReport")
        codes = {item["code"] for item in report["spec"]["mismatches"]}
        self.assertIn("unknown-boundary-criterion-ref", codes)
        self.assertIn("uncovered-boundary-entry", codes)

    def test_requirement_output_falsey_present_claim_graph_divergence_is_rejected(self) -> None:
        requirement_output = copy.deepcopy(_requirement_output())
        requirement_output["claimGraph"] = {}
        driver = FakeAlignmentDriver(requirement_output=requirement_output)
        manager = AlignmentSessionManager(driver)
        snapshot = _frozen_snapshot(manager)

        with self.assertRaises(AlignmentSessionError) as raised:
            asyncio.run(manager.draft_request(snapshot))

        self.assertEqual(raised.exception.code, "frozen_claim_graph_digest_mismatch")
        self.assertEqual(raised.exception.ref, "RequirementDraft.claimGraph")
        self.assertEqual(
            raised.exception.data["actualClaimGraphDigest"],
            "sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
        )

    def test_plan_draft_claim_ref_must_resolve_to_frozen_claim_graph(self) -> None:
        requirement_output = copy.deepcopy(_requirement_output())
        requirement_output["planDraft"]["spec"]["nodes"][0]["claimRefs"] = ["CLAIM-missing"]
        driver = FakeAlignmentDriver(requirement_output=requirement_output)
        manager = AlignmentSessionManager(driver, max_cross_alignment_redrafts=0)
        snapshot = _frozen_snapshot(manager)

        with self.assertRaises(AlignmentSessionError) as raised:
            asyncio.run(manager.draft_request(snapshot))

        self.assertEqual(raised.exception.code, "cross_alignment_redraft_exhausted")
        failed = raised.exception.snapshot
        self.assertIsInstance(failed, AlignmentSessionSnapshot)
        assert isinstance(failed, AlignmentSessionSnapshot)
        report = failed.to_mapping()["crossAlignmentReport"]
        codes = {item["code"] for item in report["spec"]["mismatches"]}
        self.assertIn("unknown-plan-claim-ref", codes)

    def test_cross_alignment_failure_records_snapshot_before_human_gate_2(self) -> None:
        acceptance_output = copy.deepcopy(_acceptance_output())
        acceptance_output["claimGraph"]["spec"]["claims"][0]["criterionRefs"] = ["BCE-FREE-INTERNAL-STEPS"]
        driver = FakeAlignmentDriver(acceptance_output=acceptance_output)
        manager = AlignmentSessionManager(driver, max_cross_alignment_redrafts=0)
        approval_service = RecordingApprovalService()
        snapshot = _frozen_snapshot(manager)

        with self.assertRaises(AlignmentSessionError) as raised:
            asyncio.run(manager.draft_request(snapshot, approval_service=approval_service))

        self.assertFalse(approval_service.called)
        self.assertEqual(raised.exception.code, "cross_alignment_redraft_exhausted")
        failed = raised.exception.snapshot
        self.assertIsInstance(failed, AlignmentSessionSnapshot)
        assert isinstance(failed, AlignmentSessionSnapshot)
        self.assertEqual(failed.stage, "failed")
        self.assertEqual(failed.turns[-1].actor, "agent:cross-alignment")
        self.assertEqual(failed.turns[-1].expected_output, CROSS_ALIGNMENT_REPORT_OUTPUT)
        report = failed.to_mapping()["crossAlignmentReport"]
        codes = {item["code"] for item in report["spec"]["mismatches"]}
        self.assertIn("free-zone-criterion-ref", codes)
        self.assertIn("uncovered-boundary-entry", codes)

    def test_cross_alignment_redraft_is_bounded_and_can_recover(self) -> None:
        invalid_acceptance = copy.deepcopy(_acceptance_output())
        invalid_acceptance["claimGraph"]["spec"]["claims"][0]["criterionRefs"] = ["BCE-COMPLETE-SUMMARY"]
        driver = FakeAlignmentDriver(acceptance_outputs=[invalid_acceptance, _acceptance_output()])
        manager = AlignmentSessionManager(driver, max_cross_alignment_redrafts=1)
        snapshot = _frozen_snapshot(manager)

        result = asyncio.run(manager.draft_request(snapshot))

        self.assertEqual(result.snapshot.stage, "request_drafted")
        self.assertEqual(result.snapshot.cross_alignment_redraft_attempts, 1)
        self.assertEqual(result.snapshot.to_mapping()["crossAlignmentReport"]["spec"]["result"], "accepted")
        draft_calls = [
            call.expected_output
            for call in driver.calls
            if call.expected_output in {ACCEPTANCE_DRAFT_OUTPUT, REQUIREMENT_DRAFT_OUTPUT}
        ]
        self.assertEqual(
            draft_calls,
            [ACCEPTANCE_DRAFT_OUTPUT, REQUIREMENT_DRAFT_OUTPUT, ACCEPTANCE_DRAFT_OUTPUT, REQUIREMENT_DRAFT_OUTPUT],
        )
        second_acceptance = [
            call for call in driver.calls if call.expected_output == ACCEPTANCE_DRAFT_OUTPUT
        ][1]
        self.assertEqual(second_acceptance.payload["redraftAttempt"], 1)
        self.assertEqual(
            second_acceptance.payload["previousCrossAlignmentReport"]["spec"]["result"],
            "rejected",
        )

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

    def test_converged_boundary_contract_rejects_open_questions(self) -> None:
        driver = FakeAlignmentDriver(boundary_contract_output=_boundary_contract_output(include_open_question=True))
        manager = AlignmentSessionManager(driver)
        snapshot = manager.start(_intent())
        snapshot = asyncio.run(manager.advance(snapshot, "Keep scope local."))

        with self.assertRaises(AlignmentSessionError) as raised:
            asyncio.run(manager.advance(snapshot, "Freeze with an unresolved question."))

        self.assertEqual(raised.exception.code, "open_question_not_freezable")

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

    def test_draft_contract_requires_nested_apiversion_for_plan_and_claim(self) -> None:
        """Regression: contract must explicitly require apiVersion/kind for nested objects.

        Before this fix, the output contracts for REQUIREMENT_DRAFT_OUTPUT and
        ACCEPTANCE_DRAFT_OUTPUT declared planDraft and claimGraph as {"type": "object"}
        without specifying required fields like apiVersion, kind, metadata, spec.
        This meant real Agents were never told to include those fields, but the
        parser required them, causing deterministic failures.

        This test verifies the contracts now explicitly require the nested structure.
        """
        from ahra.alignment_session import _output_contract, REQUIREMENT_DRAFT_OUTPUT, ACCEPTANCE_DRAFT_OUTPUT

        # Verify REQUIREMENT_DRAFT_OUTPUT contract requires nested apiVersion
        req_contract = _output_contract(REQUIREMENT_DRAFT_OUTPUT)
        plan_schema = req_contract.schema["properties"]["planDraft"]
        self.assertEqual(plan_schema["type"], "object")
        self.assertIn("apiVersion", plan_schema["required"])
        self.assertIn("kind", plan_schema["required"])
        self.assertIn("metadata", plan_schema["required"])
        self.assertIn("spec", plan_schema["required"])
        self.assertEqual(plan_schema["properties"]["apiVersion"]["const"], "ahra.dev/v1alpha1")
        self.assertEqual(plan_schema["properties"]["kind"]["const"], "PlanDraft")

        # Verify ACCEPTANCE_DRAFT_OUTPUT contract requires nested apiVersion
        acc_contract = _output_contract(ACCEPTANCE_DRAFT_OUTPUT)
        claim_schema = acc_contract.schema["properties"]["claimGraph"]
        self.assertEqual(claim_schema["type"], "object")
        self.assertIn("apiVersion", claim_schema["required"])
        self.assertIn("kind", claim_schema["required"])
        self.assertIn("metadata", claim_schema["required"])
        self.assertIn("spec", claim_schema["required"])
        self.assertEqual(claim_schema["properties"]["apiVersion"]["const"], "ahra.dev/v1alpha1")
        self.assertEqual(claim_schema["properties"]["kind"]["const"], "ClaimGraph")


class HangingAlignmentDriver:
    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        await asyncio.Event().wait()
        raise AssertionError(f"unexpected completion for {request.expected_output}")


class RecordingApprovalService:
    def __init__(self) -> None:
        self.called = False

    def request_authorization(self, request_draft: RequestDraft, *, actor: str):
        self.called = True
        raise AssertionError("cross-alignment failures must not reach Human Gate 2 authorization")


class FakeAlignmentDriver:
    def __init__(
        self,
        *,
        requirement_output: dict[str, object] | None = None,
        requirement_outputs: list[dict[str, object]] | None = None,
        acceptance_output: dict[str, object] | None = None,
        acceptance_outputs: list[dict[str, object]] | None = None,
        boundary_contract_output: dict[str, object] | None = None,
    ) -> None:
        self.calls: list[AgentRunRequest] = []
        self.alignment_turns = 0
        self.requirement_output = requirement_output
        self.requirement_outputs = list(requirement_outputs or [])
        self.acceptance_output = acceptance_output
        self.acceptance_outputs = list(acceptance_outputs or [])
        self.boundary_contract_output = boundary_contract_output

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
                    "boundaryContract": self.boundary_contract_output or _boundary_contract_output(),
                    "missingDimensions": [],
                }
            )
        if request.expected_output == REQUIREMENT_DRAFT_OUTPUT:
            return AgentRunResult(output=self._next_requirement_output())
        if request.expected_output == ACCEPTANCE_DRAFT_OUTPUT:
            return AgentRunResult(output=self._next_acceptance_output())
        raise AssertionError(f"unexpected expected_output {request.expected_output}")

    def _next_requirement_output(self) -> dict[str, object]:
        if self.requirement_outputs:
            return self.requirement_outputs.pop(0)
        return self.requirement_output or _requirement_output()

    def _next_acceptance_output(self) -> dict[str, object]:
        if self.acceptance_outputs:
            return self.acceptance_outputs.pop(0)
        return self.acceptance_output or _acceptance_output()


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
                        "criterionRefs": [
                            "BCE-COMPLETE-SUMMARY",
                            "BCE-MUST-NOT-OUTSIDE-WORKSPACE",
                            "BCE-MUST-SUMMARY",
                        ],
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


def _boundary_contract_output(*, include_open_question: bool = False) -> dict[str, object]:
    entries: list[dict[str, object]] = [
        {
            "id": "BCE-MUST-SUMMARY",
            "kind": "must",
            "statement": "Write one governed deterministic summary artifact in the local workspace.",
        },
        {
            "id": "BCE-MUST-NOT-OUTSIDE-WORKSPACE",
            "kind": "must_not",
            "statement": "Do not write outside the configured local workspace.",
        },
        {
            "id": "BCE-COMPLETE-SUMMARY",
            "kind": "completion_signal",
            "statement": "The governed deterministic summary artifact exists.",
        },
        {
            "id": "BCE-FREE-INTERNAL-STEPS",
            "kind": "free_zone",
            "statement": "Internal implementation steps may vary within the bounded task contract.",
        },
    ]
    if include_open_question:
        entries.append(
            {
                "id": "BCE-QUESTION-SCOPE",
                "kind": "open_question",
                "statement": "The artifact location remains unresolved.",
            }
        )
    return {
        "apiVersion": "ahra.dev/v1alpha1",
        "kind": "BoundaryContract",
        "metadata": {
            "name": "alignment-session-test-boundary",
            "version": 1,
        },
        "spec": {
            "entries": entries,
        },
    }


def _intent() -> IntentDraft:
    return IntentDraft.from_mapping(load_document(EXAMPLE))


if __name__ == "__main__":
    unittest.main()
