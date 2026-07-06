from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .acceptance_contracts import ClaimGraph
from .boundary_contract import BoundaryContract, BoundaryEntryKind
from .evidence_v2 import SUPPORTED_API_VERSION, canonical_fingerprint
from .plan_ir import PlanDraft


CROSS_ALIGNMENT_VALIDATOR = "ahra-cross-alignment/0.1"
REQUIRED_BOUNDARY_KINDS = frozenset(
    {
        BoundaryEntryKind.MUST.value,
        BoundaryEntryKind.MUST_NOT.value,
        BoundaryEntryKind.COMPLETION_SIGNAL.value,
    }
)


@dataclass(frozen=True, slots=True)
class CrossAlignmentMismatch:
    code: str
    message: str
    ref: str
    refs: tuple[str, ...] = ()
    data: Mapping[str, Any] | None = None

    def to_mapping(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "ref": self.ref,
            "refs": list(self.refs or (self.ref,)),
        }
        if self.data:
            payload["data"] = dict(self.data)
        return payload


@dataclass(frozen=True, slots=True)
class CrossAlignmentReport:
    report_id: str
    boundary_contract_ref: str
    claim_graph_ref: str
    plan_ref: str
    mismatches: tuple[CrossAlignmentMismatch, ...]

    @property
    def accepted(self) -> bool:
        return not self.mismatches

    def to_mapping(self) -> dict[str, Any]:
        return {
            "apiVersion": SUPPORTED_API_VERSION,
            "kind": "CrossAlignmentReport",
            "metadata": {
                "reportId": self.report_id,
                "validator": CROSS_ALIGNMENT_VALIDATOR,
            },
            "spec": {
                "result": "accepted" if self.accepted else "rejected",
                "boundaryContractRef": self.boundary_contract_ref,
                "claimGraphRef": self.claim_graph_ref,
                "planRef": self.plan_ref,
                "mismatches": [mismatch.to_mapping() for mismatch in self.mismatches],
            },
        }


class CrossAlignmentError(ValueError):
    def __init__(self, report: CrossAlignmentReport) -> None:
        self.report = report
        codes = ", ".join(mismatch.code for mismatch in report.mismatches)
        super().__init__(f"cross-alignment rejected: {codes}")


def validate_cross_alignment(
    *,
    boundary_contract: BoundaryContract,
    claim_graph: ClaimGraph,
    plan: PlanDraft,
) -> CrossAlignmentReport:
    """Validate deterministic referential integrity across Workflow A outputs."""

    mismatches: list[CrossAlignmentMismatch] = []
    entries_by_id = {entry.entry_id: entry for entry in boundary_contract.entries}
    required_boundary_ids = {
        entry.entry_id
        for entry in boundary_contract.entries
        if entry.kind in REQUIRED_BOUNDARY_KINDS
    }
    free_zone_ids = {
        entry.entry_id
        for entry in boundary_contract.entries
        if entry.kind == BoundaryEntryKind.FREE_ZONE.value
    }
    open_question_ids = sorted(
        entry.entry_id
        for entry in boundary_contract.entries
        if entry.kind == BoundaryEntryKind.OPEN_QUESTION.value
    )

    if open_question_ids:
        mismatches.append(
            CrossAlignmentMismatch(
                code="open-question-boundary-entry",
                message="boundary contract still contains open_question entries",
                ref="boundaryContract.spec.entries[].kind",
                refs=tuple(open_question_ids),
            )
        )

    covered_boundary_ids = {
        criterion_ref
        for claim in claim_graph.claims
        for criterion_ref in claim.criterion_refs
        if criterion_ref in entries_by_id
    }
    uncovered_boundary_ids = sorted(required_boundary_ids - covered_boundary_ids)
    if uncovered_boundary_ids:
        mismatches.append(
            CrossAlignmentMismatch(
                code="uncovered-boundary-entry",
                message="must, must_not, and completion_signal boundary entries require Claim criterionRefs coverage",
                ref="boundaryContract.spec.entries",
                refs=tuple(uncovered_boundary_ids),
                data={
                    "uncoveredBoundaryEntries": uncovered_boundary_ids,
                    "requiredBoundaryKinds": sorted(REQUIRED_BOUNDARY_KINDS),
                },
            )
        )

    unknown_criterion_refs_by_claim: dict[str, list[str]] = {}
    free_zone_refs_by_claim: dict[str, list[str]] = {}
    for claim in claim_graph.claims:
        unknown_refs = sorted({ref for ref in claim.criterion_refs if ref not in entries_by_id})
        if unknown_refs:
            unknown_criterion_refs_by_claim[claim.claim_id] = unknown_refs
        free_zone_refs = sorted({ref for ref in claim.criterion_refs if ref in free_zone_ids})
        if free_zone_refs:
            free_zone_refs_by_claim[claim.claim_id] = free_zone_refs

    if unknown_criterion_refs_by_claim:
        unknown_refs = sorted({ref for refs in unknown_criterion_refs_by_claim.values() for ref in refs})
        mismatches.append(
            CrossAlignmentMismatch(
                code="unknown-boundary-criterion-ref",
                message="Claim criterionRefs must resolve to frozen boundary contract entries",
                ref="claimGraph.spec.claims[].criterionRefs",
                refs=tuple(unknown_refs),
                data={"claimCriterionRefs": unknown_criterion_refs_by_claim},
            )
        )

    if free_zone_refs_by_claim:
        free_zone_refs = sorted({ref for refs in free_zone_refs_by_claim.values() for ref in refs})
        mismatches.append(
            CrossAlignmentMismatch(
                code="free-zone-criterion-ref",
                message="Claims must not cite free_zone boundary entries as acceptance criteria",
                ref="claimGraph.spec.claims[].criterionRefs",
                refs=tuple(free_zone_refs),
                data={"claimCriterionRefs": free_zone_refs_by_claim},
            )
        )

    claim_ids = {claim.claim_id for claim in claim_graph.claims}
    required_claim_ids = {claim.claim_id for claim in claim_graph.claims if claim.required}
    plan_claim_refs = {claim_ref for node in plan.nodes for claim_ref in node.claim_refs}
    uncovered_required_claim_ids = sorted(required_claim_ids - plan_claim_refs)
    if uncovered_required_claim_ids:
        mismatches.append(
            CrossAlignmentMismatch(
                code="uncovered-required-claim",
                message="required Claims must be covered by at least one PlanNode claimRef",
                ref="claimGraph.spec.claims[].required",
                refs=tuple(uncovered_required_claim_ids),
            )
        )

    unknown_claim_refs_by_node: dict[str, list[str]] = {}
    for node in plan.nodes:
        unknown_refs = sorted({claim_ref for claim_ref in node.claim_refs if claim_ref not in claim_ids})
        if unknown_refs:
            unknown_claim_refs_by_node[node.node_id] = unknown_refs
    if unknown_claim_refs_by_node:
        unknown_refs = sorted({ref for refs in unknown_claim_refs_by_node.values() for ref in refs})
        mismatches.append(
            CrossAlignmentMismatch(
                code="unknown-plan-claim-ref",
                message="PlanNode claimRefs must resolve in the frozen ClaimGraph",
                ref="planDraft.spec.nodes[].claimRefs",
                refs=tuple(unknown_refs),
                data={"nodeClaimRefs": unknown_claim_refs_by_node},
            )
        )

    return CrossAlignmentReport(
        report_id=_report_id(boundary_contract, claim_graph, plan, tuple(mismatches)),
        boundary_contract_ref=boundary_contract.name,
        claim_graph_ref=claim_graph.goal_ref,
        plan_ref=plan.goal_ref,
        mismatches=tuple(mismatches),
    )


def ensure_cross_alignment(
    *,
    boundary_contract: BoundaryContract,
    claim_graph: ClaimGraph,
    plan: PlanDraft,
) -> CrossAlignmentReport:
    report = validate_cross_alignment(
        boundary_contract=boundary_contract,
        claim_graph=claim_graph,
        plan=plan,
    )
    if not report.accepted:
        raise CrossAlignmentError(report)
    return report


def _report_id(
    boundary_contract: BoundaryContract,
    claim_graph: ClaimGraph,
    plan: PlanDraft,
    mismatches: tuple[CrossAlignmentMismatch, ...],
) -> str:
    digest = canonical_fingerprint(
        {
            "boundaryContract": boundary_contract.to_mapping(),
            "claimGraphRef": claim_graph.goal_ref,
            "claimIds": sorted(claim.claim_id for claim in claim_graph.claims),
            "mismatches": [mismatch.to_mapping() for mismatch in mismatches],
            "planRef": plan.goal_ref,
            "planNodes": [
                {"id": node.node_id, "claimRefs": list(node.claim_refs)}
                for node in sorted(plan.nodes, key=lambda item: item.node_id)
            ],
            "validator": CROSS_ALIGNMENT_VALIDATOR,
        }
    ).removeprefix("sha256:")[:16]
    return "CROSSALIGN-" + digest


__all__ = [
    "CROSS_ALIGNMENT_VALIDATOR",
    "CrossAlignmentError",
    "CrossAlignmentMismatch",
    "CrossAlignmentReport",
    "ensure_cross_alignment",
    "validate_cross_alignment",
]
