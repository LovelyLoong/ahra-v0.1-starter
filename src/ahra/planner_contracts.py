from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping

from .acceptance_contracts import ClaimGraph, GateDefinition, GatePlan, GoalContract
from .domain import ContextManifest
from .plan_ir import PlanDraft, PlanIR, PlanPatchDraft, PlanValidationReport
from .verification import DefectRecord


class PlannerValidationStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    APPROVAL_REQUIRED = "approval_required"


class ReplanTriggerType(StrEnum):
    DEFECT = "defect"
    UNAVAILABLE_CAPABILITY = "unavailable_capability"
    APPROVED_INPUT = "approved_input"
    DEPENDENCY_ARTIFACT_CHANGE = "dependency_artifact_change"
    BUDGET_OR_POLICY_CHANGE = "budget_or_policy_change"
    EXPLICIT_SCOPE_CHANGE = "explicit_scope_change"


@dataclass(frozen=True, slots=True)
class PlannerBudgetLimits:
    max_plan_nodes: int = 20
    max_plan_depth: int = 8
    max_model_calls: int = 80
    max_tool_calls: int = 200
    max_spawned_nodes: int = 0
    max_repair_cycles: int = 1
    max_fan_out: int = 4
    max_wall_seconds: int | None = None
    max_cost_usd: float | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "max_plan_nodes",
            "max_plan_depth",
            "max_model_calls",
            "max_tool_calls",
            "max_repair_cycles",
            "max_fan_out",
        ):
            if getattr(self, field_name) <= 0:
                raise ValueError(f"{field_name} must be positive")
        if self.max_spawned_nodes < 0:
            raise ValueError("max_spawned_nodes must be non-negative")
        if self.max_wall_seconds is not None and self.max_wall_seconds <= 0:
            raise ValueError("max_wall_seconds must be positive when present")
        if self.max_cost_usd is not None and self.max_cost_usd < 0:
            raise ValueError("max_cost_usd must be non-negative when present")

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "maxPlanNodes": self.max_plan_nodes,
            "maxPlanDepth": self.max_plan_depth,
            "maxModelCalls": self.max_model_calls,
            "maxToolCalls": self.max_tool_calls,
            "maxSpawnedNodes": self.max_spawned_nodes,
            "maxRepairCycles": self.max_repair_cycles,
            "maxFanOut": self.max_fan_out,
        }
        if self.max_wall_seconds is not None:
            data["maxWallSeconds"] = self.max_wall_seconds
        if self.max_cost_usd is not None:
            data["maxCostUsd"] = self.max_cost_usd
        return data


@dataclass(frozen=True, slots=True)
class PlannerRiskPolicy:
    approval_required_risk_levels: tuple[str, ...] = ("R2", "R3")
    plan_review_required_risk_levels: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "approvalRequiredRiskLevels": list(self.approval_required_risk_levels),
            "planReviewRequiredRiskLevels": list(self.plan_review_required_risk_levels),
        }


@dataclass(frozen=True, slots=True)
class PlannerContextRequest:
    run_id: str
    agent_release_digest: str
    goal_ref: str
    goal_digest: str
    policy_ref: str
    policy_digest: str
    claim_refs: tuple[str, ...] = ()
    registered_node_types: Mapping[str, str] = field(default_factory=dict)
    registered_gate_refs: Mapping[str, str] = field(default_factory=dict)
    registered_runtime_refs: Mapping[str, str] = field(default_factory=dict)
    budget_limits: PlannerBudgetLimits = field(default_factory=PlannerBudgetLimits)
    defects: tuple[DefectRecord, ...] = ()
    token_budget: int = 4096

    def to_payload(self) -> dict[str, Any]:
        return {
            "runId": self.run_id,
            "agentReleaseDigest": self.agent_release_digest,
            "goalRef": self.goal_ref,
            "goalDigest": self.goal_digest,
            "policyRef": self.policy_ref,
            "policyDigest": self.policy_digest,
            "claimRefs": sorted(self.claim_refs),
            "registeredNodeTypes": dict(sorted(self.registered_node_types.items())),
            "registeredGateRefs": dict(sorted(self.registered_gate_refs.items())),
            "registeredRuntimeRefs": dict(sorted(self.registered_runtime_refs.items())),
            "budgetLimits": self.budget_limits.to_dict(),
            "defects": [defect.to_dict() for defect in sorted(self.defects, key=lambda item: item.defect_id)],
            "tokenBudget": self.token_budget,
        }


@dataclass(frozen=True, slots=True)
class PlannerArtifact:
    artifact_id: str
    kind: str
    sha256: str
    release_digest: str
    context_manifest_digest: str
    context_manifest_ref: str
    media_type: str
    payload: Mapping[str, Any]
    refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifactId": self.artifact_id,
            "kind": self.kind,
            "sha256": self.sha256,
            "releaseDigest": self.release_digest,
            "contextManifestDigest": self.context_manifest_digest,
            "contextManifestRef": self.context_manifest_ref,
            "mediaType": self.media_type,
            "payload": self.payload,
            "refs": list(self.refs),
        }


@dataclass(frozen=True, slots=True)
class PlannerContextBundle:
    context_manifest: ContextManifest
    input_artifact: PlannerArtifact


@dataclass(frozen=True, slots=True)
class PlannerFailure:
    code: str
    message: str
    retryable: bool = False
    details: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "details": list(self.details),
        }


@dataclass(frozen=True, slots=True)
class PlanApprovalRequirement:
    risk_level: str
    reason_code: str
    required_refs: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "riskLevel": self.risk_level,
            "reasonCode": self.reason_code,
            "requiredRefs": list(self.required_refs),
        }


@dataclass(frozen=True, slots=True)
class AcceptancePlanningRequest:
    goal: GoalContract
    context_manifest: ContextManifest
    input_artifact: PlannerArtifact


@dataclass(frozen=True, slots=True)
class AcceptancePlanningResult:
    claim_graph: ClaimGraph
    gate_definitions: tuple[GateDefinition, ...]
    gate_plan: GatePlan
    output_artifact: PlannerArtifact


@dataclass(frozen=True, slots=True)
class ExecutionPlanningRequest:
    goal_ref: str
    context_manifest: ContextManifest
    input_artifact: PlannerArtifact


@dataclass(frozen=True, slots=True)
class ExecutionPlanningResult:
    draft: PlanDraft
    output_artifact: PlannerArtifact


@dataclass(frozen=True, slots=True)
class RepairPlanningRequest:
    parent_plan: PlanIR
    defects: tuple[DefectRecord, ...]
    context_manifest: ContextManifest
    input_artifact: PlannerArtifact
    trigger_type: ReplanTriggerType
    repair_cycle: int = 0


@dataclass(frozen=True, slots=True)
class RepairPlanningResult:
    patch: PlanPatchDraft
    output_artifact: PlannerArtifact


@dataclass(frozen=True, slots=True)
class PlannerValidationResult:
    status: PlannerValidationStatus
    report: PlanValidationReport
    output_artifact: PlannerArtifact
    plan: PlanIR | None = None
    approval_requirement: PlanApprovalRequirement | None = None

    @property
    def accepted(self) -> bool:
        return self.status == PlannerValidationStatus.ACCEPTED and self.plan is not None
