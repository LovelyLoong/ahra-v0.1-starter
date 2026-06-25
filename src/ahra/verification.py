from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Mapping

from .acceptance_contracts import Claim, ClaimGraph, ClaimType, GateDefinition, GatePlan, RiskLevel
from .evidence_v2 import (
    EvidenceInvalidationTrigger,
    EvidenceRegistry,
    EvidenceResult,
    EvidenceV2,
    EvidenceValidityState,
)


class GateLevel(StrEnum):
    L0 = "L0"
    L1 = "L1"
    L2 = "L2"


class DefectStatus(StrEnum):
    OPEN = "open"
    TRIAGED = "triaged"
    REPAIR_PLANNED = "repair_planned"
    REPAIRING = "repairing"
    REVERIFYING = "reverifying"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class VerificationTrigger:
    changed_refs: Mapping[str, str] = field(default_factory=dict)
    failed_gate_refs: frozenset[str] = frozenset()
    changed_claim_refs: frozenset[str] = frozenset()
    changed_gate_refs: frozenset[str] = frozenset()
    policy_digest: str | None = None
    runtime_profile_digest: str | None = None
    test_definition_digest: str | None = None
    verifier_release_digest: str | None = None
    now: datetime | None = None
    revoked_evidence_refs: frozenset[str] = frozenset()
    contradicted_evidence_refs: frozenset[str] = frozenset()

    def to_evidence_trigger(self) -> EvidenceInvalidationTrigger:
        return EvidenceInvalidationTrigger(
            changed_refs=self.changed_refs,
            changed_claim_refs=self.changed_claim_refs,
            changed_gate_refs=self.changed_gate_refs,
            policy_digest=self.policy_digest,
            runtime_profile_digest=self.runtime_profile_digest,
            test_definition_digest=self.test_definition_digest,
            verifier_release_digest=self.verifier_release_digest,
            now=self.now,
            revoked_evidence_refs=self.revoked_evidence_refs,
            contradicted_evidence_refs=self.contradicted_evidence_refs,
        )


@dataclass(frozen=True, slots=True)
class VerificationPolicy:
    mandatory_gate_refs: frozenset[str] = frozenset()
    mandatory_claim_types: frozenset[ClaimType] = frozenset({ClaimType.SECURITY, ClaimType.GOVERNANCE})
    integration_boundary_level: GateLevel = GateLevel.L1


@dataclass(frozen=True, slots=True)
class VerificationGate:
    gate_ref: str
    level: GateLevel
    claim_refs: tuple[str, ...]
    evidence_kind: str
    risk_level: RiskLevel

    @classmethod
    def from_definition(cls, definition: GateDefinition, claim_refs: tuple[str, ...]) -> "VerificationGate":
        level = GateLevel(definition.level)
        gate_cls: type[VerificationGate]
        if level == GateLevel.L0:
            gate_cls = L0Gate
        elif level == GateLevel.L1:
            gate_cls = L1Gate
        else:
            gate_cls = L2Gate
        return gate_cls(
            gate_ref=definition.gate_id,
            level=level,
            claim_refs=tuple(sorted(claim_refs)),
            evidence_kind=definition.evidence_kind,
            risk_level=definition.risk_level,
        )


class L0Gate(VerificationGate):
    pass


class L1Gate(VerificationGate):
    pass


class L2Gate(VerificationGate):
    pass


@dataclass(frozen=True, slots=True)
class VerificationSelection:
    selected_gate_refs: tuple[str, ...]
    full_gate_refs: tuple[str, ...]
    affected_claim_refs: tuple[str, ...]
    reused_evidence_refs: tuple[str, ...]
    stale_evidence_refs: tuple[str, ...]
    rationale: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "selectedGateRefs": list(self.selected_gate_refs),
            "fullGateRefs": list(self.full_gate_refs),
            "affectedClaimRefs": list(self.affected_claim_refs),
            "reusedEvidenceRefs": list(self.reused_evidence_refs),
            "staleEvidenceRefs": list(self.stale_evidence_refs),
            "rationale": list(self.rationale),
        }


@dataclass(frozen=True, slots=True)
class VerificationResult:
    gate_ref: str
    claim_refs: tuple[str, ...]
    result: EvidenceResult
    expected: str
    actual: str
    refs: tuple[str, ...] = ()
    evidence_ref: str | None = None


@dataclass(frozen=True, slots=True)
class DefectRecord:
    defect_id: str
    claim_ref: str
    gate_ref: str
    expected: str
    actual: str
    refs: tuple[str, ...]
    repair_boundary: str
    status: DefectStatus = DefectStatus.OPEN
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, object]:
        return {
            "apiVersion": "ahra.dev/v1alpha1",
            "kind": "DefectRecord",
            "metadata": {
                "defectId": self.defect_id,
                "createdAt": self.created_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            },
            "spec": {
                "claimRef": self.claim_ref,
                "gateRef": self.gate_ref,
                "expected": self.expected,
                "actual": self.actual,
                "refs": list(self.refs),
                "repairBoundary": self.repair_boundary,
                "status": self.status.value,
            },
        }


@dataclass(frozen=True, slots=True)
class CompletionGateResult:
    complete: bool
    missing_claim_refs: tuple[str, ...] = ()
    non_current_evidence_refs: tuple[str, ...] = ()
    uncovered_claim_refs: tuple[str, ...] = ()
    open_defect_refs: tuple[str, ...] = ()


def select_gates(
    *,
    graph: ClaimGraph,
    gate_definitions: tuple[GateDefinition, ...],
    gate_plan: GatePlan,
    evidence_records: tuple[EvidenceV2, ...],
    trigger: VerificationTrigger,
    policy: VerificationPolicy | None = None,
) -> VerificationSelection:
    policy = policy or VerificationPolicy()
    claims_by_id = {claim.claim_id: claim for claim in graph.claims}
    gates = _materialize_gates(gate_definitions, gate_plan)
    gate_by_ref = {gate.gate_ref: gate for gate in gates}
    evidence_inspections = EvidenceRegistry(evidence_records).inspect_all(trigger.to_evidence_trigger())

    direct_claims = set(trigger.changed_claim_refs)
    stale_evidence_refs: set[str] = set()
    reused_evidence_refs: set[str] = set()
    rationale: set[str] = set()
    for evidence in evidence_records:
        inspection = evidence_inspections[evidence.evidence_id]
        if inspection.current and evidence.result == EvidenceResult.PASSED and _stored_fingerprint_matches(evidence):
            reused_evidence_refs.add(evidence.evidence_id)
        else:
            stale_evidence_refs.add(evidence.evidence_id)
            direct_claims.update(evidence.claim_refs)
            if inspection.current and evidence.result == EvidenceResult.PASSED:
                rationale.add(f"fingerprint_not_matched:{evidence.evidence_id}")

    affected_claims = _reverse_dependency_closure(graph, direct_claims)
    selected_gate_refs: set[str] = set()

    for claim_ref in sorted(affected_claims):
        claim = claims_by_id.get(claim_ref)
        if not claim:
            continue
        for gate_ref in claim.gate_refs:
            if gate_ref in gate_by_ref:
                selected_gate_refs.add(gate_ref)
                rationale.add(f"affected_claim:{claim_ref}->{gate_ref}")

    for gate_ref in sorted(trigger.failed_gate_refs):
        if gate_ref in gate_by_ref:
            selected_gate_refs.add(gate_ref)
            rationale.add(f"failed_gate:{gate_ref}")

    for gate in gates:
        if gate.level == policy.integration_boundary_level and set(gate.claim_refs) & affected_claims:
            selected_gate_refs.add(gate.gate_ref)
            rationale.add(f"integration_boundary:{gate.gate_ref}")

    for gate_ref in sorted(policy.mandatory_gate_refs):
        if gate_ref in gate_by_ref:
            selected_gate_refs.add(gate_ref)
            rationale.add(f"mandatory_policy_gate:{gate_ref}")

    for claim in graph.claims:
        if claim.claim_type in policy.mandatory_claim_types and claim.required:
            for gate_ref in claim.gate_refs:
                if gate_ref in gate_by_ref:
                    selected_gate_refs.add(gate_ref)
                    rationale.add(f"mandatory_safety_claim:{claim.claim_id}->{gate_ref}")

    return VerificationSelection(
        selected_gate_refs=tuple(sorted(selected_gate_refs)),
        full_gate_refs=tuple(sorted(gate.gate_ref for gate in gates)),
        affected_claim_refs=tuple(sorted(affected_claims)),
        reused_evidence_refs=tuple(sorted(reused_evidence_refs - stale_evidence_refs)),
        stale_evidence_refs=tuple(sorted(stale_evidence_refs)),
        rationale=tuple(sorted(rationale)),
    )


def evaluate_completion(
    *,
    graph: ClaimGraph,
    evidence_records: tuple[EvidenceV2, ...],
    trigger: VerificationTrigger | None = None,
    open_defects: tuple[DefectRecord, ...] = (),
) -> CompletionGateResult:
    trigger = trigger or VerificationTrigger()
    inspections = EvidenceRegistry(evidence_records).inspect_all(trigger.to_evidence_trigger())
    evidence_by_claim: dict[str, list[EvidenceV2]] = {}
    for evidence in evidence_records:
        for claim_ref in evidence.claim_refs:
            evidence_by_claim.setdefault(claim_ref, []).append(evidence)

    missing: list[str] = []
    non_current: list[str] = []
    uncovered: list[str] = []
    for claim in graph.claims:
        if not claim.required:
            continue
        records = evidence_by_claim.get(claim.claim_id, [])
        if not records:
            missing.append(claim.claim_id)
            continue
        current_passed = False
        for record in records:
            inspection = inspections[record.evidence_id]
            if inspection.current and record.result == EvidenceResult.PASSED:
                current_passed = True
            else:
                non_current.append(record.evidence_id)
        if not current_passed:
            uncovered.append(claim.claim_id)

    open_defect_refs = tuple(sorted(defect.defect_id for defect in open_defects if defect.status != DefectStatus.RESOLVED))
    return CompletionGateResult(
        complete=not missing and not non_current and not uncovered and not open_defect_refs,
        missing_claim_refs=tuple(sorted(missing)),
        non_current_evidence_refs=tuple(sorted(set(non_current))),
        uncovered_claim_refs=tuple(sorted(uncovered)),
        open_defect_refs=open_defect_refs,
    )


def defect_from_result(
    *,
    defect_id: str,
    result: VerificationResult,
    repair_boundary: str,
    created_at: datetime | None = None,
) -> DefectRecord:
    if result.result == EvidenceResult.PASSED:
        raise ValueError("passed gate result does not create a defect")
    if not result.claim_refs:
        raise ValueError("failed gate result must name at least one claim")
    return DefectRecord(
        defect_id=defect_id,
        claim_ref=result.claim_refs[0],
        gate_ref=result.gate_ref,
        expected=result.expected,
        actual=result.actual,
        refs=result.refs,
        repair_boundary=repair_boundary,
        created_at=created_at or datetime.now(UTC),
    )


def _materialize_gates(
    gate_definitions: tuple[GateDefinition, ...],
    gate_plan: GatePlan,
) -> tuple[VerificationGate, ...]:
    definition_by_id = {definition.gate_id: definition for definition in gate_definitions}
    gates: list[VerificationGate] = []
    for entry in sorted(gate_plan.gates, key=lambda item: item.gate_ref):
        definition = definition_by_id.get(entry.gate_ref)
        if definition is None:
            continue
        gates.append(VerificationGate.from_definition(definition, entry.claim_refs))
    return tuple(gates)


def _stored_fingerprint_matches(evidence: EvidenceV2) -> bool:
    return evidence.stored_fingerprint is not None and evidence.stored_fingerprint == evidence.fingerprint()


def _reverse_dependency_closure(graph: ClaimGraph, direct_claim_refs: set[str]) -> set[str]:
    reverse: dict[str, set[str]] = {}
    for claim in graph.claims:
        for dependency in claim.depends_on:
            reverse.setdefault(dependency, set()).add(claim.claim_id)
    affected = set(direct_claim_refs)
    pending = list(sorted(direct_claim_refs))
    while pending:
        claim_ref = pending.pop(0)
        for dependant in sorted(reverse.get(claim_ref, ())):
            if dependant not in affected:
                affected.add(dependant)
                pending.append(dependant)
    return affected
