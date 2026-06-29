from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping


SUPPORTED_API_VERSION = "ahra.dev/v1alpha1"
SECURITY_GOVERNANCE_TYPES = {"security", "governance"}
FORBIDDEN_DOWNGRADE_KEYS = {
    "approvalRequired",
    "criterionRefs",
    "dependsOn",
    "gateRefs",
    "required",
    "requiredEvidenceKinds",
    "riskLevel",
    "type",
}


class ClaimType(StrEnum):
    FUNCTIONAL = "functional"
    STRUCTURAL = "structural"
    QUALITY = "quality"
    SECURITY = "security"
    OPERATIONAL = "operational"
    GOVERNANCE = "governance"


class RiskLevel(StrEnum):
    R0 = "R0"
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"


@dataclass(frozen=True, slots=True)
class ContractViolation:
    code: str
    message: str
    ref: str

    def format(self) -> str:
        return f"{self.code} at {self.ref}: {self.message}"


class AcceptanceContractError(ValueError):
    def __init__(self, violations: list[ContractViolation]) -> None:
        self.violations = violations
        super().__init__("\n".join(violation.format() for violation in violations))


@dataclass(frozen=True, slots=True)
class GoalCriterion:
    criterion_id: str
    statement: str
    required: bool = True

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "GoalCriterion":
        return cls(
            criterion_id=str(data["id"]),
            statement=str(data["statement"]),
            required=bool(data.get("required", True)),
        )


@dataclass(frozen=True, slots=True)
class GoalContract:
    goal_id: str
    version: int
    objective: str
    criteria: tuple[GoalCriterion, ...]
    mandatory_claim_types: tuple[ClaimType, ...]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "GoalContract":
        _require_api_version(data, "GoalContract")
        metadata = _mapping(data["metadata"])
        spec = _mapping(data["spec"])
        return cls(
            goal_id=str(metadata["goalId"]),
            version=int(metadata["version"]),
            objective=str(spec["objective"]),
            criteria=tuple(GoalCriterion.from_mapping(_mapping(item)) for item in spec["criteria"]),
            mandatory_claim_types=tuple(ClaimType(str(item)) for item in spec["mandatoryClaimTypes"]),
        )


@dataclass(frozen=True, slots=True)
class Claim:
    claim_id: str
    claim_type: ClaimType
    statement: str
    criterion_refs: tuple[str, ...]
    depends_on: tuple[str, ...]
    risk_level: RiskLevel
    required_evidence_kinds: tuple[str, ...]
    gate_refs: tuple[str, ...]
    approval_required: bool = False
    required: bool = True
    extensions: Mapping[str, Any] | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "Claim":
        return cls(
            claim_id=str(data["id"]),
            claim_type=ClaimType(str(data["type"])),
            statement=str(data["statement"]),
            criterion_refs=tuple(str(item) for item in data["criterionRefs"]),
            depends_on=tuple(str(item) for item in data.get("dependsOn", ())),
            risk_level=RiskLevel(str(data["riskLevel"])),
            required=bool(data.get("required", True)),
            required_evidence_kinds=tuple(str(item) for item in data["requiredEvidenceKinds"]),
            gate_refs=tuple(str(item) for item in data.get("gateRefs", ())),
            approval_required=bool(data.get("approvalRequired", False)),
            extensions=_extensions(data),
        )


@dataclass(frozen=True, slots=True)
class ClaimGraph:
    goal_ref: str
    version: int
    claims: tuple[Claim, ...]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ClaimGraph":
        _require_api_version(data, "ClaimGraph")
        metadata = _mapping(data["metadata"])
        spec = _mapping(data["spec"])
        return cls(
            goal_ref=str(spec["goalRef"]),
            version=int(metadata["version"]),
            claims=tuple(Claim.from_mapping(_mapping(item)) for item in spec["claims"]),
        )


@dataclass(frozen=True, slots=True)
class CommandOutputMatch:
    stream: str
    contains: str

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "CommandOutputMatch":
        return cls(
            stream=str(data["stream"]),
            contains=str(data["contains"]),
        )

    def to_mapping(self) -> dict[str, str]:
        return {
            "stream": self.stream,
            "contains": self.contains,
        }


@dataclass(frozen=True, slots=True)
class CommandExpectation:
    expected_exit_code: int
    output_match: CommandOutputMatch | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "CommandExpectation":
        return cls(
            expected_exit_code=int(data["expectedExitCode"]),
            output_match=(
                CommandOutputMatch.from_mapping(_mapping(data["outputMatch"]))
                if data.get("outputMatch") is not None
                else None
            ),
        )

    def to_mapping(self) -> dict[str, Any]:
        result: dict[str, Any] = {"expectedExitCode": self.expected_exit_code}
        if self.output_match is not None:
            result["outputMatch"] = self.output_match.to_mapping()
        return result


@dataclass(frozen=True, slots=True)
class GateDefinition:
    gate_id: str
    version: int
    level: str
    evidence_kind: str
    verifier_mode: str
    risk_level: RiskLevel
    name: str = ""
    subject_kinds: tuple[str, ...] = ()
    command: tuple[str, ...] = ()
    expectation: CommandExpectation | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "GateDefinition":
        _require_api_version(data, "GateDefinition")
        metadata = _mapping(data["metadata"])
        spec = _mapping(data["spec"])
        return cls(
            gate_id=str(metadata["gateId"]),
            version=int(metadata["version"]),
            level=str(spec["level"]),
            evidence_kind=str(spec["evidenceKind"]),
            verifier_mode=str(spec["verifierMode"]),
            risk_level=RiskLevel(str(spec["riskLevel"])),
            name=str(metadata.get("name") or ""),
            subject_kinds=tuple(str(item) for item in spec.get("subjectKinds", ())),
            command=tuple(str(item) for item in spec.get("command", ())),
            expectation=(
                CommandExpectation.from_mapping(_mapping(spec["expectation"]))
                if spec.get("expectation") is not None
                else None
            ),
        )

    def to_mapping(self) -> dict[str, Any]:
        spec: dict[str, Any] = {
            "level": self.level,
            "evidenceKind": self.evidence_kind,
            "verifierMode": self.verifier_mode,
            "riskLevel": self.risk_level.value,
        }
        if self.subject_kinds:
            spec["subjectKinds"] = list(self.subject_kinds)
        if self.command:
            spec["command"] = list(self.command)
        if self.expectation is not None:
            spec["expectation"] = self.expectation.to_mapping()
        return {
            "apiVersion": SUPPORTED_API_VERSION,
            "kind": "GateDefinition",
            "metadata": {
                "name": self.name,
                "gateId": self.gate_id,
                "version": self.version,
            },
            "spec": spec,
        }


@dataclass(frozen=True, slots=True)
class GatePlanEntry:
    gate_ref: str
    claim_refs: tuple[str, ...]
    evidence_kind: str

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "GatePlanEntry":
        return cls(
            gate_ref=str(data["gateRef"]),
            claim_refs=tuple(str(item) for item in data["claimRefs"]),
            evidence_kind=str(data["evidenceKind"]),
        )


@dataclass(frozen=True, slots=True)
class GatePlan:
    goal_ref: str
    claim_graph_ref: str
    version: int
    gates: tuple[GatePlanEntry, ...]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "GatePlan":
        _require_api_version(data, "GatePlan")
        metadata = _mapping(data["metadata"])
        spec = _mapping(data["spec"])
        return cls(
            goal_ref=str(spec["goalRef"]),
            claim_graph_ref=str(spec["claimGraphRef"]),
            version=int(metadata["version"]),
            gates=tuple(GatePlanEntry.from_mapping(_mapping(item)) for item in spec["gates"]),
        )


def validate_acceptance_contracts(
    goal: GoalContract,
    graph: ClaimGraph,
    gate_definitions: tuple[GateDefinition, ...],
    gate_plan: GatePlan,
) -> list[ContractViolation]:
    violations: list[ContractViolation] = []
    violations.extend(_unique("criterion", [item.criterion_id for item in goal.criteria], "GoalContract.spec.criteria"))
    violations.extend(_unique("claim", [item.claim_id for item in graph.claims], "ClaimGraph.spec.claims"))
    violations.extend(_unique("gate", [item.gate_id for item in gate_definitions], "GateDefinition"))
    violations.extend(_unique("gate-plan-entry", [item.gate_ref for item in gate_plan.gates], "GatePlan.spec.gates"))

    if goal.goal_id != graph.goal_ref:
        violations.append(ContractViolation("goal-ref-mismatch", "ClaimGraph goalRef does not match GoalContract goalId", "ClaimGraph.spec.goalRef"))
    if goal.goal_id != gate_plan.goal_ref:
        violations.append(ContractViolation("goal-ref-mismatch", "GatePlan goalRef does not match GoalContract goalId", "GatePlan.spec.goalRef"))

    criterion_ids = {item.criterion_id for item in goal.criteria}
    claim_by_id = {item.claim_id: item for item in graph.claims}
    gate_by_id = {item.gate_id: item for item in gate_definitions}
    gate_claims = _gate_claims(gate_plan)

    covered_criteria: set[str] = set()
    for claim in graph.claims:
        for criterion_ref in claim.criterion_refs:
            if criterion_ref not in criterion_ids:
                violations.append(ContractViolation("unknown-criterion-ref", f"{claim.claim_id} references unknown criterion {criterion_ref}", claim.claim_id))
            else:
                covered_criteria.add(criterion_ref)
        for dependency in claim.depends_on:
            if dependency not in claim_by_id:
                violations.append(ContractViolation("missing-claim-dependency", f"{claim.claim_id} depends on unknown claim {dependency}", claim.claim_id))
        for gate_ref in claim.gate_refs:
            if gate_ref not in gate_by_id:
                violations.append(ContractViolation("unregistered-gate", f"{claim.claim_id} references unregistered gate {gate_ref}", claim.claim_id))
        if claim.required and not claim.gate_refs and not claim.approval_required:
            violations.append(ContractViolation("required-claim-without-gate", "required claim has neither gateRefs nor approvalRequired", claim.claim_id))
        if claim.required and claim.gate_refs and not (set(claim.gate_refs) & gate_claims.get(claim.claim_id, set())):
            violations.append(ContractViolation("required-claim-not-in-gate-plan", "required claim gateRefs are not mapped by GatePlan", claim.claim_id))
        if claim.claim_type.value in SECURITY_GOVERNANCE_TYPES:
            violations.extend(_validate_security_governance_claim(claim))

    for criterion_id in sorted(criterion_ids - covered_criteria):
        violations.append(ContractViolation("uncovered-criterion", f"goal criterion {criterion_id} has no Claim coverage", criterion_id))

    for claim_type in goal.mandatory_claim_types:
        matches = [claim for claim in graph.claims if claim.claim_type == claim_type and claim.required]
        if not matches:
            violations.append(ContractViolation("missing-mandatory-claim", f"mandatory claim type {claim_type.value} has no required Claim", "GoalContract.spec.mandatoryClaimTypes"))

    violations.extend(_validate_gate_plan(gate_plan, claim_by_id, gate_by_id))
    violations.extend(_validate_acyclic(graph.claims))
    return violations


def ensure_acceptance_contracts(
    goal: GoalContract,
    graph: ClaimGraph,
    gate_definitions: tuple[GateDefinition, ...],
    gate_plan: GatePlan,
) -> None:
    violations = validate_acceptance_contracts(goal, graph, gate_definitions, gate_plan)
    if violations:
        raise AcceptanceContractError(violations)


def _validate_security_governance_claim(claim: Claim) -> list[ContractViolation]:
    violations: list[ContractViolation] = []
    if not claim.required:
        violations.append(ContractViolation("forbidden-security-governance-downgrade", f"{claim.claim_type.value} claim cannot be optional", claim.claim_id))
    for path in _forbidden_extension_paths(claim.extensions or {}):
        violations.append(
            ContractViolation(
                "forbidden-security-governance-downgrade",
                f"{claim.claim_type.value} claim extension attempts to override {path}",
                claim.claim_id,
            )
        )
    return violations


def _validate_gate_plan(
    gate_plan: GatePlan,
    claim_by_id: Mapping[str, Claim],
    gate_by_id: Mapping[str, GateDefinition],
) -> list[ContractViolation]:
    violations: list[ContractViolation] = []
    for entry in gate_plan.gates:
        gate = gate_by_id.get(entry.gate_ref)
        if gate is None:
            violations.append(ContractViolation("unregistered-gate", f"GatePlan references unregistered gate {entry.gate_ref}", entry.gate_ref))
            continue
        if entry.evidence_kind != gate.evidence_kind:
            violations.append(ContractViolation("evidence-kind-mismatch", f"GatePlan evidence kind {entry.evidence_kind} does not match GateDefinition {gate.evidence_kind}", entry.gate_ref))
        for claim_ref in entry.claim_refs:
            claim = claim_by_id.get(claim_ref)
            if claim is None:
                violations.append(ContractViolation("unknown-claim-ref", f"GatePlan references unknown claim {claim_ref}", entry.gate_ref))
            elif entry.gate_ref not in claim.gate_refs:
                violations.append(ContractViolation("claim-gate-mismatch", f"GatePlan maps {entry.gate_ref} to {claim_ref}, but the Claim does not list that gate", claim_ref))
    return violations


def _validate_acyclic(claims: tuple[Claim, ...]) -> list[ContractViolation]:
    claim_by_id = {claim.claim_id: claim for claim in claims}
    visiting: set[str] = set()
    visited: set[str] = set()
    violations: list[ContractViolation] = []

    def visit(claim_id: str, path: tuple[str, ...]) -> None:
        if claim_id in visiting:
            cycle = " -> ".join((*path, claim_id))
            violations.append(ContractViolation("cyclic-claim-dependency", f"claim dependency cycle detected: {cycle}", claim_id))
            return
        if claim_id in visited:
            return
        claim = claim_by_id.get(claim_id)
        if claim is None:
            return
        visiting.add(claim_id)
        for dependency in claim.depends_on:
            visit(dependency, (*path, claim_id))
        visiting.remove(claim_id)
        visited.add(claim_id)

    for claim in claims:
        visit(claim.claim_id, ())
    return violations


def _unique(kind: str, values: list[str], ref: str) -> list[ContractViolation]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return [ContractViolation(f"duplicate-{kind}-id", f"duplicate {kind} id {value}", ref) for value in sorted(duplicates)]


def _gate_claims(gate_plan: GatePlan) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for entry in gate_plan.gates:
        for claim_ref in entry.claim_refs:
            result.setdefault(claim_ref, set()).add(entry.gate_ref)
    return result


def _forbidden_extension_paths(value: Any, prefix: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(value, Mapping):
        for key, nested in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if key in FORBIDDEN_DOWNGRADE_KEYS:
                paths.append(path)
            paths.extend(_forbidden_extension_paths(nested, path))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            paths.extend(_forbidden_extension_paths(nested, f"{prefix}[{index}]"))
    return paths


def _extensions(data: Mapping[str, Any]) -> Mapping[str, Any]:
    return {str(key): value for key, value in data.items() if str(key).startswith("x-")}


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("expected mapping")
    return value


def _require_api_version(data: Mapping[str, Any], kind: str) -> None:
    if data.get("apiVersion") != SUPPORTED_API_VERSION:
        raise ValueError(f"{kind} apiVersion must be {SUPPORTED_API_VERSION}")
    if data.get("kind") != kind:
        raise ValueError(f"expected kind {kind}")
