from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping

from .evidence_v2 import canonical_fingerprint


SUPPORTED_API_VERSION = "ahra.dev/v1alpha1"
COMPILER_VERSION = "ahra-plan-compiler/0.1"


class PlanNodeType(StrEnum):
    BOUNDED_TASK = "bounded_task"
    GATE_VERIFICATION = "gate_verification"
    GOAL_VERIFICATION = "goal_verification"
    REPAIR = "repair"


@dataclass(frozen=True, slots=True)
class PlanValidationError:
    code: str
    message: str
    ref: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "ref": self.ref}


@dataclass(frozen=True, slots=True)
class PlanValidationReport:
    report_id: str
    subject_ref: str
    subject_digest: str | None
    errors: tuple[PlanValidationError, ...]
    created_by: str = "ahra-plan-compiler"
    refs: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "apiVersion": SUPPORTED_API_VERSION,
            "kind": "PlanValidationReport",
            "metadata": {
                "reportId": self.report_id,
                "createdBy": self.created_by,
            },
            "spec": {
                "subjectRef": self.subject_ref,
                "subjectDigest": self.subject_digest,
                "result": "passed" if self.valid else "failed",
                "errors": [error.to_dict() for error in self.errors],
                "refs": list(self.refs),
            },
        }


@dataclass(frozen=True, slots=True)
class PlanBudget:
    max_model_calls: int
    max_tool_calls: int
    max_spawned_nodes: int = 0
    max_wall_seconds: int | None = None
    max_cost_usd: float | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> "PlanBudget":
        data = data or {}
        return cls(
            max_model_calls=int(data.get("maxModelCalls", 0)),
            max_tool_calls=int(data.get("maxToolCalls", 0)),
            max_spawned_nodes=int(data.get("maxSpawnedNodes", 0)),
            max_wall_seconds=_optional_int(data.get("maxWallSeconds")),
            max_cost_usd=_optional_float(data.get("maxCostUsd")),
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "maxModelCalls": self.max_model_calls,
            "maxToolCalls": self.max_tool_calls,
            "maxSpawnedNodes": self.max_spawned_nodes,
        }
        if self.max_wall_seconds is not None:
            data["maxWallSeconds"] = self.max_wall_seconds
        if self.max_cost_usd is not None:
            data["maxCostUsd"] = self.max_cost_usd
        return data


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 1
    retryable_failure_classes: tuple[str, ...] = ()
    idempotency_key_required: bool = False

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> "RetryPolicy":
        data = data or {}
        return cls(
            max_attempts=int(data.get("maxAttempts", 1)),
            retryable_failure_classes=tuple(sorted(str(item) for item in data.get("retryableFailureClasses", ()))),
            idempotency_key_required=bool(data.get("idempotencyKeyRequired", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "maxAttempts": self.max_attempts,
            "retryableFailureClasses": list(self.retryable_failure_classes),
            "idempotencyKeyRequired": self.idempotency_key_required,
        }


@dataclass(frozen=True, slots=True)
class CapabilityRequest:
    capability: str
    resources: tuple[str, ...]
    risk_level: str = "R1"
    approval_refs: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "CapabilityRequest":
        return cls(
            capability=str(data["capability"]),
            resources=tuple(sorted(str(item) for item in data.get("resources", ()))),
            risk_level=str(data.get("riskLevel", "R1")),
            approval_refs=tuple(sorted(str(item) for item in data.get("approvalRefs", ()))),
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"capability": self.capability, "resources": list(self.resources)}
        if self.risk_level != "R1":
            data["riskLevel"] = self.risk_level
        if self.approval_refs:
            data["approvalRefs"] = list(self.approval_refs)
        return data


@dataclass(frozen=True, slots=True)
class CapabilityGrant:
    capability: str
    resources: tuple[str, ...]
    grant_digest: str
    risk_level: str = "R1"
    approval_refs: tuple[str, ...] = ()

    @classmethod
    def from_request(cls, request: CapabilityRequest) -> "CapabilityGrant":
        payload = {
            "approvalRefs": list(request.approval_refs),
            "capability": request.capability,
            "resources": list(request.resources),
            "riskLevel": request.risk_level,
        }
        return cls(
            capability=request.capability,
            resources=request.resources,
            grant_digest=canonical_fingerprint(payload),
            risk_level=request.risk_level,
            approval_refs=request.approval_refs,
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "capability": self.capability,
            "resources": list(self.resources),
            "grantDigest": self.grant_digest,
        }
        if self.risk_level != "R1":
            data["riskLevel"] = self.risk_level
        if self.approval_refs:
            data["approvalRefs"] = list(self.approval_refs)
        return data


@dataclass(frozen=True, slots=True)
class PlanOutputContract:
    name: str
    schema_ref: str
    consumer_node_refs: tuple[str, ...] = ()
    delivery_role: str | None = None
    artifact_required: bool = True

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "PlanOutputContract":
        return cls(
            name=str(data["name"]),
            schema_ref=str(data.get("schemaRef") or ""),
            consumer_node_refs=tuple(sorted(str(item) for item in data.get("consumerNodeRefs", ()))),
            delivery_role=str(data["deliveryRole"]) if data.get("deliveryRole") else None,
            artifact_required=bool(data.get("artifactRequired", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name,
            "schemaRef": self.schema_ref,
            "consumerNodeRefs": list(self.consumer_node_refs),
            "artifactRequired": self.artifact_required,
        }
        if self.delivery_role:
            data["deliveryRole"] = self.delivery_role
        return data


@dataclass(frozen=True, slots=True)
class PlanNodeDraft:
    node_id: str
    node_type: str
    objective: str
    claim_refs: tuple[str, ...]
    depends_on: tuple[str, ...]
    input_refs: tuple[str, ...]
    expected_outputs: tuple[PlanOutputContract, ...]
    capability_requests: tuple[CapabilityRequest, ...]
    gate_refs: tuple[str, ...]
    runtime_ref: str | None
    budget: PlanBudget
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    timeout_seconds: int | None = None
    compensation_ref: str | None = None
    side_effect: str = "idempotent"
    terminal_goal_verification: bool = False

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "PlanNodeDraft":
        return cls(
            node_id=str(data["id"]),
            node_type=str(data["nodeType"]),
            objective=str(data["objective"]),
            claim_refs=tuple(sorted(str(item) for item in data.get("claimRefs", ()))),
            depends_on=tuple(sorted(str(item) for item in data.get("dependsOn", ()))),
            input_refs=tuple(sorted(str(item) for item in data.get("inputRefs", ()))),
            expected_outputs=tuple(PlanOutputContract.from_mapping(_mapping(item)) for item in data.get("expectedOutputs", ())),
            capability_requests=tuple(CapabilityRequest.from_mapping(_mapping(item)) for item in data.get("capabilityRequests", ())),
            gate_refs=tuple(sorted(str(item) for item in data.get("gateRefs", ()))),
            runtime_ref=str(data["runtimeRef"]) if data.get("runtimeRef") else None,
            budget=PlanBudget.from_mapping(_mapping(data["budgetRequest"]) if data.get("budgetRequest") else None),
            retry_policy=RetryPolicy.from_mapping(_mapping(data["retryPolicy"]) if data.get("retryPolicy") else None),
            timeout_seconds=_optional_int(data.get("timeoutSeconds")),
            compensation_ref=str(data["compensationRef"]) if data.get("compensationRef") else None,
            side_effect=str(data.get("sideEffect", "idempotent")),
            terminal_goal_verification=bool(data.get("terminalGoalVerification", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.node_id,
            "nodeType": self.node_type,
            "objective": self.objective,
            "claimRefs": list(self.claim_refs),
            "dependsOn": list(self.depends_on),
            "inputRefs": list(self.input_refs),
            "expectedOutputs": [item.to_dict() for item in self.expected_outputs],
            "capabilityRequests": [item.to_dict() for item in self.capability_requests],
            "gateRefs": list(self.gate_refs),
            "budgetRequest": self.budget.to_dict(),
            "retryPolicy": self.retry_policy.to_dict(),
            "sideEffect": self.side_effect,
            "terminalGoalVerification": self.terminal_goal_verification,
        }
        if self.runtime_ref:
            data["runtimeRef"] = self.runtime_ref
        if self.timeout_seconds is not None:
            data["timeoutSeconds"] = self.timeout_seconds
        if self.compensation_ref:
            data["compensationRef"] = self.compensation_ref
        return data


@dataclass(frozen=True, slots=True)
class PlanDraft:
    goal_ref: str
    proposed_by: str
    nodes: tuple[PlanNodeDraft, ...]
    rationale: str = ""

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "PlanDraft":
        _require_api_version(data, "PlanDraft")
        metadata = _mapping(data["metadata"])
        spec = _mapping(data["spec"])
        return cls(
            goal_ref=str(metadata["goalId"]),
            proposed_by=str(metadata["proposedBy"]),
            rationale=str(spec.get("rationale", "")),
            nodes=tuple(PlanNodeDraft.from_mapping(_mapping(item)) for item in spec["nodes"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "apiVersion": SUPPORTED_API_VERSION,
            "kind": "PlanDraft",
            "metadata": {"goalId": self.goal_ref, "proposedBy": self.proposed_by},
            "spec": {
                "rationale": self.rationale,
                "nodes": [node.to_dict() for node in self.nodes],
            },
        }


@dataclass(frozen=True, slots=True)
class PlanEdge:
    source_node_ref: str
    target_node_ref: str

    def to_dict(self) -> dict[str, str]:
        return {"sourceNodeRef": self.source_node_ref, "targetNodeRef": self.target_node_ref}


@dataclass(frozen=True, slots=True)
class PlanNodeIR:
    node_id: str
    node_type: str
    objective: str
    claim_refs: tuple[str, ...]
    depends_on: tuple[str, ...]
    input_refs: tuple[str, ...]
    expected_outputs: tuple[PlanOutputContract, ...]
    capability_grants: tuple[CapabilityGrant, ...]
    gate_refs: tuple[str, ...]
    gate_digests: tuple[str, ...]
    runtime_ref: str
    runtime_digest: str
    budget: PlanBudget
    retry_policy: RetryPolicy
    timeout_seconds: int | None
    compensation_ref: str | None
    side_effect: str
    terminal_goal_verification: bool
    canonical_order: int

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.node_id,
            "nodeType": self.node_type,
            "objective": self.objective,
            "claimRefs": list(self.claim_refs),
            "dependsOn": list(self.depends_on),
            "inputRefs": list(self.input_refs),
            "expectedOutputs": [item.to_dict() for item in self.expected_outputs],
            "capabilityGrants": [item.to_dict() for item in self.capability_grants],
            "gateRefs": list(self.gate_refs),
            "gateDigests": list(self.gate_digests),
            "runtimeRef": self.runtime_ref,
            "runtimeDigest": self.runtime_digest,
            "budget": self.budget.to_dict(),
            "retryPolicy": self.retry_policy.to_dict(),
            "sideEffect": self.side_effect,
            "terminalGoalVerification": self.terminal_goal_verification,
            "canonicalOrder": self.canonical_order,
        }
        if self.timeout_seconds is not None:
            data["timeoutSeconds"] = self.timeout_seconds
        if self.compensation_ref:
            data["compensationRef"] = self.compensation_ref
        return data


@dataclass(frozen=True, slots=True)
class PlanIR:
    plan_id: str
    version: int
    goal_ref: str
    goal_digest: str
    claim_graph_digest: str
    nodes: tuple[PlanNodeIR, ...]
    edges: tuple[PlanEdge, ...]
    compiler_version: str
    parent_plan_digest: str | None = None
    validation_report_ref: str | None = None

    def fingerprint_payload(self) -> dict[str, Any]:
        return {
            "claimGraphDigest": self.claim_graph_digest,
            "compilerVersion": self.compiler_version,
            "edges": [edge.to_dict() for edge in self.edges],
            "goalDigest": self.goal_digest,
            "goalRef": self.goal_ref,
            "nodes": [node.to_dict() for node in self.nodes],
            "parentPlanDigest": self.parent_plan_digest,
            "planId": self.plan_id,
            "version": self.version,
        }

    def digest(self) -> str:
        return canonical_fingerprint(self.fingerprint_payload())

    def to_dict(self) -> dict[str, Any]:
        spec: dict[str, Any] = {
            "goalRef": self.goal_ref,
            "goalDigest": self.goal_digest,
            "claimGraphDigest": self.claim_graph_digest,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "compilerVersion": self.compiler_version,
        }
        if self.parent_plan_digest:
            spec["parentPlanDigest"] = self.parent_plan_digest
        if self.validation_report_ref:
            spec["validationReportRef"] = self.validation_report_ref
        return {
            "apiVersion": SUPPORTED_API_VERSION,
            "kind": "PlanIR",
            "metadata": {
                "planId": self.plan_id,
                "version": self.version,
                "digest": self.digest(),
            },
            "spec": spec,
        }


@dataclass(frozen=True, slots=True)
class PlanPatchDraft:
    parent_plan_digest: str
    defect_refs: tuple[str, ...]
    supersede_node_refs: tuple[str, ...]
    add_nodes: tuple[PlanNodeDraft, ...]
    unchanged_node_refs: tuple[str, ...] = ()
    reused_evidence_refs: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "PlanPatchDraft":
        _require_api_version(data, "PlanPatchDraft")
        spec = _mapping(data["spec"])
        return cls(
            parent_plan_digest=str(spec["parentPlanDigest"]),
            defect_refs=tuple(sorted(str(item) for item in spec.get("defectRefs", ()))),
            supersede_node_refs=tuple(sorted(str(item) for item in spec.get("supersedeNodeRefs", ()))),
            unchanged_node_refs=tuple(sorted(str(item) for item in spec.get("unchangedNodeRefs", ()))),
            reused_evidence_refs=tuple(sorted(str(item) for item in spec.get("reusedEvidenceRefs", ()))),
            add_nodes=tuple(PlanNodeDraft.from_mapping(_mapping(item)) for item in spec.get("addNodes", ())),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "apiVersion": SUPPORTED_API_VERSION,
            "kind": "PlanPatchDraft",
            "metadata": {"parentPlanDigest": self.parent_plan_digest},
            "spec": {
                "parentPlanDigest": self.parent_plan_digest,
                "defectRefs": list(self.defect_refs),
                "supersedeNodeRefs": list(self.supersede_node_refs),
                "unchangedNodeRefs": list(self.unchanged_node_refs),
                "reusedEvidenceRefs": list(self.reused_evidence_refs),
                "addNodes": [node.to_dict() for node in self.add_nodes],
            },
        }


@dataclass(frozen=True, slots=True)
class PlanCompilerConfig:
    goal_ref: str
    goal_digest: str
    claim_graph_digest: str
    required_claim_refs: frozenset[str]
    registered_node_types: Mapping[str, str]
    registered_gate_refs: Mapping[str, str]
    registered_runtime_refs: Mapping[str, str]
    allowed_capabilities: frozenset[str]
    default_runtime_ref: str
    max_fan_out: int = 4
    compiler_version: str = COMPILER_VERSION


@dataclass(frozen=True, slots=True)
class PlanCompilationResult:
    plan: PlanIR | None
    report: PlanValidationReport


def compile_plan_draft(draft: PlanDraft, config: PlanCompilerConfig) -> PlanCompilationResult:
    return _compile_nodes(
        draft=draft,
        config=config,
        version=1,
        parent_plan_digest=None,
        plan_id_override=None,
    )


def compile_plan_patch(parent: PlanIR, patch: PlanPatchDraft, config: PlanCompilerConfig) -> PlanCompilationResult:
    errors: list[PlanValidationError] = []
    parent_digest = parent.digest()
    if patch.parent_plan_digest != parent_digest:
        errors.append(PlanValidationError("parent-plan-digest-mismatch", "PlanPatchDraft parent digest does not match parent PlanIR", "PlanPatchDraft.spec.parentPlanDigest"))

    parent_node_ids = {node.node_id for node in parent.nodes}
    for node_ref in patch.supersede_node_refs:
        if node_ref not in parent_node_ids:
            errors.append(PlanValidationError("unknown-supersede-node", f"patch supersedes unknown node {node_ref}", node_ref))

    unchanged = [node for node in parent.nodes if node.node_id not in set(patch.supersede_node_refs)]
    if patch.unchanged_node_refs:
        actual_unchanged = {node.node_id for node in unchanged}
        for node_ref in patch.unchanged_node_refs:
            if node_ref not in actual_unchanged:
                errors.append(PlanValidationError("unknown-unchanged-node", f"patch marks unknown or superseded node {node_ref} unchanged", node_ref))

    add_node_ids = [node.node_id for node in patch.add_nodes]
    for duplicate in _duplicates(add_node_ids):
        errors.append(PlanValidationError("duplicate-node-id", f"duplicate patch node id {duplicate}", duplicate))
    unchanged_ids = {node.node_id for node in unchanged}
    for node in patch.add_nodes:
        if node.node_id in unchanged_ids:
            errors.append(PlanValidationError("patch-mutates-parent-node", f"patch add node reuses unchanged parent node id {node.node_id}", node.node_id))

    if errors:
        return PlanCompilationResult(
            plan=None,
            report=_report(
                "PLANPATCH-invalid",
                "PlanPatchDraft",
                None,
                errors,
                refs=tuple(sorted((*patch.defect_refs, *patch.reused_evidence_refs))),
            ),
        )

    draft = PlanDraft(
        goal_ref=parent.goal_ref,
        proposed_by="plan-patch-compiler",
        rationale="Compiled from PlanPatchDraft without mutating parent PlanIR.",
        nodes=tuple(_draft_from_ir_node(node) for node in unchanged) + patch.add_nodes,
    )
    return _compile_nodes(
        draft=draft,
        config=config,
        version=parent.version + 1,
        parent_plan_digest=parent_digest,
        plan_id_override=parent.plan_id,
        report_refs=tuple(sorted((*patch.defect_refs, *patch.reused_evidence_refs))),
    )


def validate_plan_ir(plan: PlanIR, config: PlanCompilerConfig) -> PlanValidationReport:
    errors = _validate_ir(plan, config)
    return _report(plan.plan_id, f"{plan.plan_id}@v{plan.version}", plan.digest(), errors, refs=(plan.plan_id,))


def _compile_nodes(
    *,
    draft: PlanDraft,
    config: PlanCompilerConfig,
    version: int,
    parent_plan_digest: str | None,
    plan_id_override: str | None,
    report_refs: tuple[str, ...] = (),
) -> PlanCompilationResult:
    draft_errors = _validate_draft(draft, config)
    if draft_errors:
        return PlanCompilationResult(
            plan=None,
            report=_report("PLANDRAFT-invalid", "PlanDraft", None, draft_errors, refs=report_refs),
        )

    ordered = _canonical_node_order(draft.nodes)
    node_by_id = {node.node_id: node for node in ordered}
    edges = tuple(
        PlanEdge(source_node_ref=dependency, target_node_ref=node.node_id)
        for node in ordered
        for dependency in node.depends_on
    )
    plan_id = plan_id_override or _plan_id(draft, config)
    nodes: list[PlanNodeIR] = []
    for index, node in enumerate(ordered):
        runtime_ref = node.runtime_ref or config.default_runtime_ref
        nodes.append(
            PlanNodeIR(
                node_id=node.node_id,
                node_type=node.node_type,
                objective=node.objective,
                claim_refs=node.claim_refs,
                depends_on=tuple(dep for dep in node.depends_on if dep in node_by_id),
                input_refs=node.input_refs,
                expected_outputs=node.expected_outputs,
                capability_grants=tuple(CapabilityGrant.from_request(request) for request in node.capability_requests),
                gate_refs=node.gate_refs,
                gate_digests=tuple(config.registered_gate_refs[gate_ref] for gate_ref in node.gate_refs),
                runtime_ref=runtime_ref,
                runtime_digest=config.registered_runtime_refs[runtime_ref],
                budget=node.budget,
                retry_policy=node.retry_policy,
                timeout_seconds=node.timeout_seconds,
                compensation_ref=node.compensation_ref,
                side_effect=node.side_effect,
                terminal_goal_verification=node.terminal_goal_verification or node.node_type == PlanNodeType.GOAL_VERIFICATION.value,
                canonical_order=index,
            )
        )
    plan = PlanIR(
        plan_id=plan_id,
        version=version,
        goal_ref=draft.goal_ref,
        goal_digest=config.goal_digest,
        claim_graph_digest=config.claim_graph_digest,
        nodes=tuple(nodes),
        edges=edges,
        compiler_version=config.compiler_version,
        parent_plan_digest=parent_plan_digest,
    )
    report = validate_plan_ir(plan, config)
    if not report.valid:
        return PlanCompilationResult(plan=None, report=report)
    return PlanCompilationResult(plan=plan, report=report)


def _validate_draft(draft: PlanDraft, config: PlanCompilerConfig) -> list[PlanValidationError]:
    errors: list[PlanValidationError] = []
    if draft.goal_ref != config.goal_ref:
        errors.append(PlanValidationError("goal-ref-mismatch", "PlanDraft goalId does not match compiler GoalContract", "PlanDraft.metadata.goalId"))
    if not draft.nodes:
        errors.append(PlanValidationError("empty-plan", "PlanDraft must contain at least one node", "PlanDraft.spec.nodes"))

    node_ids = [node.node_id for node in draft.nodes]
    for duplicate in _duplicates(node_ids):
        errors.append(PlanValidationError("duplicate-node-id", f"duplicate PlanNode id {duplicate}", duplicate))
    node_id_set = set(node_ids)

    for node in draft.nodes:
        errors.extend(_validate_node_common(node, node_id_set, config))

    errors.extend(_validate_acyclic(tuple(node.node_id for node in draft.nodes), {node.node_id: node.depends_on for node in draft.nodes}))
    errors.extend(_validate_claim_coverage({claim for node in draft.nodes for claim in node.claim_refs}, config))
    errors.extend(_validate_terminal_goal_node(draft.nodes, {node.node_id: node.depends_on for node in draft.nodes}))
    errors.extend(_validate_fan_out(tuple(node.node_id for node in draft.nodes), {node.node_id: node.depends_on for node in draft.nodes}, config.max_fan_out))
    return errors


def _validate_ir(plan: PlanIR, config: PlanCompilerConfig) -> list[PlanValidationError]:
    errors: list[PlanValidationError] = []
    if plan.goal_ref != config.goal_ref:
        errors.append(PlanValidationError("goal-ref-mismatch", "PlanIR goalRef does not match compiler GoalContract", "PlanIR.spec.goalRef"))
    if plan.goal_digest != config.goal_digest:
        errors.append(PlanValidationError("goal-digest-mismatch", "PlanIR goalDigest does not match compiler config", "PlanIR.spec.goalDigest"))
    if plan.claim_graph_digest != config.claim_graph_digest:
        errors.append(PlanValidationError("claim-graph-digest-mismatch", "PlanIR claimGraphDigest does not match compiler config", "PlanIR.spec.claimGraphDigest"))
    node_ids = [node.node_id for node in plan.nodes]
    for duplicate in _duplicates(node_ids):
        errors.append(PlanValidationError("duplicate-node-id", f"duplicate PlanNode id {duplicate}", duplicate))
    node_id_set = set(node_ids)
    for node in plan.nodes:
        draft_like = _draft_from_ir_node(node)
        errors.extend(_validate_node_common(draft_like, node_id_set, config))
        if node.runtime_digest != config.registered_runtime_refs.get(node.runtime_ref):
            errors.append(PlanValidationError("runtime-digest-mismatch", f"runtime {node.runtime_ref} digest does not match registry", node.node_id))
        expected_gate_digests = tuple(config.registered_gate_refs.get(gate_ref) for gate_ref in node.gate_refs)
        if node.gate_digests != expected_gate_digests:
            errors.append(PlanValidationError("gate-digest-mismatch", f"gate digests do not match registry for {node.node_id}", node.node_id))
    dependencies = {node.node_id: node.depends_on for node in plan.nodes}
    errors.extend(_validate_acyclic(tuple(node_ids), dependencies))
    errors.extend(_validate_claim_coverage({claim for node in plan.nodes for claim in node.claim_refs}, config))
    errors.extend(_validate_terminal_goal_node(tuple(_draft_from_ir_node(node) for node in plan.nodes), dependencies))
    errors.extend(_validate_fan_out(tuple(node_ids), dependencies, config.max_fan_out))
    return errors


def _validate_node_common(
    node: PlanNodeDraft,
    node_id_set: set[str],
    config: PlanCompilerConfig,
) -> list[PlanValidationError]:
    errors: list[PlanValidationError] = []
    if node.node_type not in config.registered_node_types:
        errors.append(PlanValidationError("unregistered-node-type", f"node type {node.node_type} is not registered", node.node_id))
    for dependency in node.depends_on:
        if dependency not in node_id_set:
            errors.append(PlanValidationError("missing-node-ref", f"{node.node_id} depends on unknown node {dependency}", node.node_id))
    for claim_ref in node.claim_refs:
        if claim_ref not in config.required_claim_refs:
            errors.append(PlanValidationError("unknown-claim-ref", f"{node.node_id} references unknown Claim {claim_ref}", node.node_id))
    if not node.gate_refs:
        errors.append(PlanValidationError("missing-gate-responsibility", f"{node.node_id} has no Gate responsibility", node.node_id))
    for gate_ref in node.gate_refs:
        if gate_ref not in config.registered_gate_refs:
            errors.append(PlanValidationError("unregistered-gate-ref", f"{node.node_id} references unregistered Gate {gate_ref}", node.node_id))
    runtime_ref = node.runtime_ref or config.default_runtime_ref
    if runtime_ref not in config.registered_runtime_refs:
        errors.append(PlanValidationError("unregistered-runtime-ref", f"{node.node_id} references unregistered runtime {runtime_ref}", node.node_id))
    for ref in (*node.input_refs, runtime_ref):
        if _is_mutable_ref(ref):
            errors.append(PlanValidationError("mutable-latest-ref", f"{node.node_id} uses mutable ref {ref}", node.node_id))
    for request in node.capability_requests:
        if request.capability not in config.allowed_capabilities:
            errors.append(PlanValidationError("capability-out-of-scope", f"{node.node_id} requests capability {request.capability} outside Goal scope", node.node_id))
    errors.extend(_validate_budget(node))
    errors.extend(_validate_outputs(node, node_id_set))
    errors.extend(_validate_retry(node))
    return errors


def _validate_budget(node: PlanNodeDraft) -> list[PlanValidationError]:
    errors: list[PlanValidationError] = []
    if node.budget.max_model_calls <= 0:
        errors.append(PlanValidationError("invalid-budget", "maxModelCalls must be positive", node.node_id))
    if node.budget.max_tool_calls <= 0:
        errors.append(PlanValidationError("invalid-budget", "maxToolCalls must be positive", node.node_id))
    if node.budget.max_spawned_nodes < 0:
        errors.append(PlanValidationError("invalid-budget", "maxSpawnedNodes must be finite and non-negative", node.node_id))
    if node.budget.max_wall_seconds is not None and node.budget.max_wall_seconds <= 0:
        errors.append(PlanValidationError("invalid-budget", "maxWallSeconds must be positive when present", node.node_id))
    if node.budget.max_cost_usd is not None and node.budget.max_cost_usd < 0:
        errors.append(PlanValidationError("invalid-budget", "maxCostUsd must be non-negative when present", node.node_id))
    if node.timeout_seconds is not None:
        if node.timeout_seconds <= 0:
            errors.append(PlanValidationError("invalid-timeout", "timeoutSeconds must be positive", node.node_id))
        if node.budget.max_wall_seconds is not None and node.timeout_seconds > node.budget.max_wall_seconds:
            errors.append(PlanValidationError("inconsistent-timeout", "timeoutSeconds cannot exceed maxWallSeconds", node.node_id))
    return errors


def _validate_outputs(node: PlanNodeDraft, node_id_set: set[str]) -> list[PlanValidationError]:
    errors: list[PlanValidationError] = []
    output_names = [output.name for output in node.expected_outputs]
    for duplicate in _duplicates(output_names):
        errors.append(PlanValidationError("duplicate-output-name", f"{node.node_id} has duplicate output {duplicate}", node.node_id))
    is_terminal = node.terminal_goal_verification or node.node_type == PlanNodeType.GOAL_VERIFICATION.value
    for output in node.expected_outputs:
        for consumer_ref in output.consumer_node_refs:
            if consumer_ref not in node_id_set:
                errors.append(PlanValidationError("missing-output-consumer", f"{output.name} references unknown consumer {consumer_ref}", node.node_id))
        if not is_terminal and not output.consumer_node_refs and not output.delivery_role:
            errors.append(PlanValidationError("unconsumed-output", f"{node.node_id} output {output.name} has no consumer or delivery role", node.node_id))
        if output.delivery_role == "evidence" and (not output.schema_ref or not output.artifact_required):
            errors.append(PlanValidationError("invalid-evidence-output", f"{node.node_id} evidence output {output.name} needs schema and immutable artifact", node.node_id))
    return errors


def _validate_retry(node: PlanNodeDraft) -> list[PlanValidationError]:
    errors: list[PlanValidationError] = []
    if node.retry_policy.max_attempts < 1:
        errors.append(PlanValidationError("invalid-retry-policy", "maxAttempts must be at least 1", node.node_id))
    if node.retry_policy.max_attempts > 1 and not node.retry_policy.retryable_failure_classes:
        errors.append(PlanValidationError("invalid-retry-policy", "retry requires classified retryable failures", node.node_id))
    if (
        node.side_effect == "non_idempotent"
        and node.retry_policy.max_attempts > 1
        and not node.retry_policy.idempotency_key_required
        and not node.compensation_ref
    ):
        errors.append(PlanValidationError("unsafe-non-idempotent-retry", "non-idempotent retries require idempotency or compensation", node.node_id))
    return errors


def _validate_claim_coverage(covered_claims: set[str], config: PlanCompilerConfig) -> list[PlanValidationError]:
    return [
        PlanValidationError("uncovered-claim", f"required Claim {claim_ref} is not assigned to any PlanNode", claim_ref)
        for claim_ref in sorted(config.required_claim_refs - covered_claims)
    ]


def _validate_terminal_goal_node(
    nodes: tuple[PlanNodeDraft, ...],
    dependencies: Mapping[str, tuple[str, ...]],
) -> list[PlanValidationError]:
    terminal_nodes = [
        node
        for node in nodes
        if node.terminal_goal_verification or node.node_type == PlanNodeType.GOAL_VERIFICATION.value
    ]
    if not terminal_nodes:
        return [PlanValidationError("missing-terminal-goal-verification", "plan has no terminal Goal verification node", "Plan.spec.nodes")]
    outgoing = _outgoing_counts(tuple(dependencies), dependencies)
    errors: list[PlanValidationError] = []
    for node in terminal_nodes:
        if outgoing.get(node.node_id, 0):
            errors.append(PlanValidationError("non-terminal-goal-verification", f"{node.node_id} has downstream consumers", node.node_id))
        if not node.gate_refs:
            errors.append(PlanValidationError("missing-gate-responsibility", f"{node.node_id} has no Gate responsibility", node.node_id))
    return errors


def _validate_fan_out(
    node_ids: tuple[str, ...],
    dependencies: Mapping[str, tuple[str, ...]],
    max_fan_out: int,
) -> list[PlanValidationError]:
    outgoing = _outgoing_counts(node_ids, dependencies)
    return [
        PlanValidationError("unbounded-fan-out", f"{node_id} fan-out {count} exceeds {max_fan_out}", node_id)
        for node_id, count in sorted(outgoing.items())
        if count > max_fan_out
    ]


def _validate_acyclic(
    node_ids: tuple[str, ...],
    dependencies: Mapping[str, tuple[str, ...]],
) -> list[PlanValidationError]:
    visiting: set[str] = set()
    visited: set[str] = set()
    errors: list[PlanValidationError] = []
    node_id_set = set(node_ids)

    def visit(node_id: str, path: tuple[str, ...]) -> None:
        if node_id in visiting:
            errors.append(PlanValidationError("cycle-detected", "cycle detected: " + " -> ".join((*path, node_id)), node_id))
            return
        if node_id in visited or node_id not in node_id_set:
            return
        visiting.add(node_id)
        for dependency in dependencies.get(node_id, ()):
            visit(dependency, (*path, node_id))
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in node_ids:
        visit(node_id, ())
    return errors


def _canonical_node_order(nodes: tuple[PlanNodeDraft, ...]) -> tuple[PlanNodeDraft, ...]:
    by_id = {node.node_id: node for node in nodes}
    indegree = {node.node_id: 0 for node in nodes}
    children: dict[str, list[str]] = {node.node_id: [] for node in nodes}
    for node in nodes:
        for dependency in node.depends_on:
            if dependency in by_id:
                indegree[node.node_id] += 1
                children[dependency].append(node.node_id)
    ready = sorted(node_id for node_id, count in indegree.items() if count == 0)
    ordered: list[str] = []
    while ready:
        node_id = ready.pop(0)
        ordered.append(node_id)
        for child in sorted(children[node_id]):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
                ready.sort()
    if len(ordered) != len(nodes):
        return tuple(sorted(nodes, key=lambda node: node.node_id))
    return tuple(by_id[node_id] for node_id in ordered)


def _outgoing_counts(node_ids: tuple[str, ...], dependencies: Mapping[str, tuple[str, ...]]) -> dict[str, int]:
    counts = {node_id: 0 for node_id in node_ids}
    for node_dependencies in dependencies.values():
        for dependency in node_dependencies:
            if dependency in counts:
                counts[dependency] += 1
    return counts


def _plan_id(draft: PlanDraft, config: PlanCompilerConfig) -> str:
    payload = {
        "claimGraphDigest": config.claim_graph_digest,
        "goalDigest": config.goal_digest,
        "goalRef": draft.goal_ref,
        "nodes": [node.to_dict() for node in _canonical_node_order(draft.nodes)],
    }
    return "PLAN-" + canonical_fingerprint(payload).removeprefix("sha256:")[:16]


def _draft_from_ir_node(node: PlanNodeIR) -> PlanNodeDraft:
    return PlanNodeDraft(
        node_id=node.node_id,
        node_type=node.node_type,
        objective=node.objective,
        claim_refs=node.claim_refs,
        depends_on=node.depends_on,
        input_refs=node.input_refs,
        expected_outputs=node.expected_outputs,
        capability_requests=tuple(
            CapabilityRequest(
                grant.capability,
                grant.resources,
                risk_level=grant.risk_level,
                approval_refs=grant.approval_refs,
            )
            for grant in node.capability_grants
        ),
        gate_refs=node.gate_refs,
        runtime_ref=node.runtime_ref,
        budget=node.budget,
        retry_policy=node.retry_policy,
        timeout_seconds=node.timeout_seconds,
        compensation_ref=node.compensation_ref,
        side_effect=node.side_effect,
        terminal_goal_verification=node.terminal_goal_verification,
    )


def _report(
    report_key: str,
    subject_ref: str,
    subject_digest: str | None,
    errors: list[PlanValidationError],
    *,
    refs: tuple[str, ...] = (),
) -> PlanValidationReport:
    digest_key = canonical_fingerprint(
        {
            "errors": [error.to_dict() for error in errors],
            "refs": list(refs),
            "subjectDigest": subject_digest,
            "subjectRef": subject_ref,
        }
    ).removeprefix("sha256:")[:16]
    return PlanValidationReport(
        report_id=f"PLANVAL-{digest_key}",
        subject_ref=subject_ref,
        subject_digest=subject_digest,
        errors=tuple(errors),
        refs=refs or (report_key,),
    )


def _duplicates(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def _is_mutable_ref(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized == "latest" or normalized.endswith(":latest") or normalized.endswith("@latest") or normalized.endswith("/latest")


def _optional_int(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    return int(value)


def _optional_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    return float(value)


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("expected mapping")
    return value


def _require_api_version(data: Mapping[str, Any], kind: str) -> None:
    if data.get("apiVersion") != SUPPORTED_API_VERSION:
        raise ValueError(f"{kind} apiVersion must be {SUPPORTED_API_VERSION}")
    if data.get("kind") != kind:
        raise ValueError(f"expected kind {kind}")
