from __future__ import annotations

import copy
import unittest

from ahra.acceptance_contracts import ClaimGraph
from ahra.boundary_contract import BoundaryContract
from ahra.cross_alignment import validate_cross_alignment
from ahra.plan_ir import PlanDraft


class CrossAlignmentValidatorTests(unittest.TestCase):
    def test_valid_cross_alignment_is_accepted(self) -> None:
        report = validate_cross_alignment(
            boundary_contract=_boundary_contract(),
            claim_graph=_claim_graph(),
            plan=_plan(),
        )

        self.assertTrue(report.accepted)
        self.assertEqual(report.to_mapping()["spec"]["result"], "accepted")
        self.assertEqual(report.to_mapping()["spec"]["mismatches"], [])

    def test_boundary_must_must_not_and_completion_signal_require_claim_coverage(self) -> None:
        claim_graph = _claim_graph(criterion_refs=["BCE-MUST-SUMMARY", "BCE-COMPLETE-SUMMARY"])

        report = validate_cross_alignment(
            boundary_contract=_boundary_contract(),
            claim_graph=claim_graph,
            plan=_plan(),
        )

        mismatch = _mismatch(report, "uncovered-boundary-entry")
        self.assertEqual(mismatch["refs"], ["BCE-MUST-NOT-OUTSIDE-WORKSPACE"])

    def test_claim_must_not_reference_free_zone(self) -> None:
        claim_graph = _claim_graph(
            criterion_refs=[
                "BCE-COMPLETE-SUMMARY",
                "BCE-FREE-INTERNAL-STEPS",
                "BCE-MUST-NOT-OUTSIDE-WORKSPACE",
                "BCE-MUST-SUMMARY",
            ]
        )

        report = validate_cross_alignment(
            boundary_contract=_boundary_contract(),
            claim_graph=claim_graph,
            plan=_plan(),
        )

        mismatch = _mismatch(report, "free-zone-criterion-ref")
        self.assertEqual(mismatch["refs"], ["BCE-FREE-INTERNAL-STEPS"])

    def test_claim_criterion_refs_must_resolve_to_boundary_entries(self) -> None:
        claim_graph = _claim_graph(
            criterion_refs=[
                "BCE-COMPLETE-SUMMARY",
                "BCE-MUST-NOT-OUTSIDE-WORKSPACE",
                "BCE-MUST-SUMMARY",
                "BCE-UNKNOWN",
            ]
        )

        report = validate_cross_alignment(
            boundary_contract=_boundary_contract(),
            claim_graph=claim_graph,
            plan=_plan(),
        )

        mismatch = _mismatch(report, "unknown-boundary-criterion-ref")
        self.assertEqual(mismatch["refs"], ["BCE-UNKNOWN"])

    def test_required_claim_requires_plan_node_coverage(self) -> None:
        report = validate_cross_alignment(
            boundary_contract=_boundary_contract(),
            claim_graph=_claim_graph(),
            plan=_plan(claim_refs=[]),
        )

        mismatch = _mismatch(report, "uncovered-required-claim")
        self.assertEqual(mismatch["refs"], ["CLAIM-summary-artifact"])

    def test_plan_node_claim_refs_must_resolve_in_claim_graph(self) -> None:
        report = validate_cross_alignment(
            boundary_contract=_boundary_contract(),
            claim_graph=_claim_graph(),
            plan=_plan(claim_refs=["CLAIM-missing"]),
        )

        mismatch = _mismatch(report, "unknown-plan-claim-ref")
        self.assertEqual(mismatch["refs"], ["CLAIM-missing"])

    def test_open_question_entries_reject_cross_alignment(self) -> None:
        report = validate_cross_alignment(
            boundary_contract=_boundary_contract(include_open_question=True),
            claim_graph=_claim_graph(),
            plan=_plan(),
        )

        mismatch = _mismatch(report, "open-question-boundary-entry")
        self.assertEqual(mismatch["refs"], ["BCE-QUESTION-SCOPE"])


def _mismatch(report, code: str) -> dict[str, object]:
    matches = [
        item
        for item in report.to_mapping()["spec"]["mismatches"]
        if item["code"] == code
    ]
    assert matches, report.to_mapping()
    return matches[0]


def _boundary_contract(*, include_open_question: bool = False) -> BoundaryContract:
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
    return BoundaryContract.from_mapping(
        {
            "apiVersion": "ahra.dev/v1alpha1",
            "kind": "BoundaryContract",
            "metadata": {
                "name": "cross-alignment-test-boundary",
                "version": 1,
            },
            "spec": {
                "entries": entries,
            },
        }
    )


def _claim_graph(criterion_refs: list[str] | None = None) -> ClaimGraph:
    payload = copy.deepcopy(_claim_graph_payload())
    if criterion_refs is not None:
        payload["spec"]["claims"][0]["criterionRefs"] = criterion_refs
    return ClaimGraph.from_mapping(payload)


def _claim_graph_payload() -> dict[str, object]:
    return {
        "apiVersion": "ahra.dev/v1alpha1",
        "kind": "ClaimGraph",
        "metadata": {
            "name": "cross-alignment-test-claims",
            "goalId": "GOAL-CROSS-ALIGNMENT",
            "version": 1,
        },
        "spec": {
            "goalRef": "GOAL-CROSS-ALIGNMENT",
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
    }


def _plan(claim_refs: list[str] | None = None) -> PlanDraft:
    payload = copy.deepcopy(_plan_payload())
    if claim_refs is not None:
        payload["spec"]["nodes"][0]["claimRefs"] = claim_refs
    return PlanDraft.from_mapping(payload)


def _plan_payload() -> dict[str, object]:
    return {
        "apiVersion": "ahra.dev/v1alpha1",
        "kind": "PlanDraft",
        "metadata": {
            "goalId": "GOAL-CROSS-ALIGNMENT",
            "proposedBy": "planner/cross-alignment-test",
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
                            "consumerNodeRefs": [],
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
                }
            ],
        },
    }


if __name__ == "__main__":
    unittest.main()
