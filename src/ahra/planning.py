from __future__ import annotations

import json
from dataclasses import replace
from typing import Any, Mapping

from .acceptance_contracts import ClaimGraph, GateDefinition, GatePlan, RiskLevel
from .agent_contracts import validate_agent_output
from .context import ContextBuilder, ContextSource
from .evidence_v2 import canonical_fingerprint
from .plan_ir import (
    PlanCompilationResult,
    PlanCompilerConfig,
    PlanDraft,
    PlanIR,
    PlanNodeIR,
    PlanPatchDraft,
    PlanValidationError,
    PlanValidationReport,
    compile_plan_draft,
    compile_plan_patch,
)
from .planner_contracts import (
    AcceptancePlanningRequest,
    AcceptancePlanningResult,
    ExecutionPlanningRequest,
    ExecutionPlanningResult,
    PlanApprovalRequirement,
    PlannerArtifact,
    PlannerBudgetLimits,
    PlannerContextBundle,
    PlannerContextRequest,
    PlannerFailure,
    PlannerRiskPolicy,
    PlannerValidationResult,
    PlannerValidationStatus,
    RepairPlanningRequest,
    RepairPlanningResult,
    ReplanTriggerType,
)
from .ports import (
    AgentDriver,
    AgentDriverRegistry,
    AgentOutputContract,
    AgentOutputContractError,
    AgentRole,
    AgentRunRequest,
    AgentRuntimeProfile,
)
from .verification import DefectRecord, DefectStatus


PLANNER_ADMISSION_VERSION = "ahra-planner-admission/0.1"
PLANNER_CONTEXT_KIND = "planner-context-input"
PLAN_DRAFT_KIND = "planner-plan-draft"
PLAN_PATCH_KIND = "planner-plan-patch"
ACCEPTANCE_DRAFT_KIND = "planner-acceptance-draft"
WRITE_CAPABILITIES = {
    "filesystem.write",
    "process.exec",
    "spawn.agent",
    "network.access",
    "secret.read",
    "external.write",
    "production.deploy",
}


class PlannerRuntimeBoundaryError(ValueError):
    pass


class PlannerAdapterError(RuntimeError):
    def __init__(self, failure: PlannerFailure) -> None:
        self.failure = failure
        super().__init__(f"{failure.code}: {failure.message}")


class PlannerContextBuilder:
    def __init__(self, context_builder: ContextBuilder | None = None) -> None:
        self.context_builder = context_builder or ContextBuilder()

    def build(self, request: PlannerContextRequest) -> PlannerContextBundle:
        payload = request.to_payload()
        sources = (
            ContextSource(
                kind="policy",
                ref=request.policy_ref,
                content=_json_bytes({"policyDigest": request.policy_digest, "policyRef": request.policy_ref}),
                trust="project-authoritative",
                priority=100,
            ),
            ContextSource(
                kind="agent_release",
                ref=request.agent_release_digest,
                content=_json_bytes({"agentReleaseDigest": request.agent_release_digest}),
                trust="system-authoritative",
                priority=100,
            ),
            ContextSource(
                kind="task",
                ref=request.goal_ref,
                content=_json_bytes({"goalRef": request.goal_ref, "goalDigest": request.goal_digest}),
                trust="project-authoritative",
                priority=100,
            ),
            ContextSource(
                kind="run_state",
                ref=request.run_id,
                content=_json_bytes(
                    {
                        "budgetLimits": request.budget_limits.to_dict(),
                        "defectRefs": [defect.defect_id for defect in request.defects],
                    }
                ),
                trust="system-authoritative",
                priority=100,
            ),
            ContextSource(
                kind="tool_schema",
                ref="planner-available-node-gate-runtime-types",
                content=_json_bytes(
                    {
                        "registeredNodeTypes": dict(sorted(request.registered_node_types.items())),
                        "registeredGateRefs": dict(sorted(request.registered_gate_refs.items())),
                        "registeredRuntimeRefs": dict(sorted(request.registered_runtime_refs.items())),
                    }
                ),
                trust="project-authoritative",
                priority=80,
            ),
            ContextSource(
                kind="output_contract",
                ref="planner-output-contracts",
                content=_json_bytes(
                    {
                        "planDraftKind": "PlanDraft",
                        "planPatchKind": "PlanPatchDraft",
                        "claimRefs": sorted(request.claim_refs),
                    }
                ),
                trust="system-authoritative",
                priority=100,
            ),
        )
        manifest = self.context_builder.build(
            run_id=request.run_id,
            agent_release_digest=request.agent_release_digest,
            sources=sources,
            token_budget=request.token_budget,
        )
        input_artifact = make_planner_artifact(
            kind=PLANNER_CONTEXT_KIND,
            payload=payload,
            release_digest=request.agent_release_digest,
            context_manifest=manifest,
            refs=(
                request.goal_ref,
                request.policy_ref,
                *sorted(request.claim_refs),
                *(defect.defect_id for defect in sorted(request.defects, key=lambda item: item.defect_id)),
            ),
        )
        return PlannerContextBundle(context_manifest=manifest, input_artifact=input_artifact)


def planner_read_only_runtime_profile(profile_ref: str = "planner/read-only") -> AgentRuntimeProfile:
    return AgentRuntimeProfile(profile_ref=profile_ref, sandbox="read_only", capabilities=())


def ensure_planner_runtime_profile(profile: AgentRuntimeProfile) -> None:
    if profile.sandbox != "read_only":
        raise PlannerRuntimeBoundaryError("planner runtime profile must use read_only sandbox")
    requested = set(profile.capabilities)
    denied = requested & WRITE_CAPABILITIES
    if denied:
        raise PlannerRuntimeBoundaryError(
            "planner runtime profile cannot include project write or tool execution grants: "
            + ", ".join(sorted(denied))
        )


def make_planner_artifact(
    *,
    kind: str,
    payload: Mapping[str, Any],
    release_digest: str,
    context_manifest: Any,
    refs: tuple[str, ...] = (),
    media_type: str = "application/json",
) -> PlannerArtifact:
    context_digest = context_manifest.sha256
    context_ref = context_manifest.context_manifest_id
    fingerprint_payload = {
        "kind": kind,
        "payload": payload,
        "releaseDigest": release_digest,
        "contextManifestDigest": context_digest,
        "contextManifestRef": context_ref,
        "refs": sorted(refs),
    }
    digest = canonical_fingerprint(fingerprint_payload)
    return PlannerArtifact(
        artifact_id=f"PLART-{digest.removeprefix('sha256:')[:24]}",
        kind=kind,
        sha256=digest,
        release_digest=release_digest,
        context_manifest_digest=context_digest,
        context_manifest_ref=context_ref,
        media_type=media_type,
        payload=payload,
        refs=tuple(sorted(refs)),
    )


class FixtureExecutionPlanner:
    def __init__(self, draft_mapping: Mapping[str, Any]) -> None:
        self._draft_mapping = _copy_mapping(draft_mapping)

    async def propose_plan(self, request: ExecutionPlanningRequest) -> ExecutionPlanningResult:
        draft = PlanDraft.from_mapping(self._draft_mapping)
        artifact = make_planner_artifact(
            kind=PLAN_DRAFT_KIND,
            payload=draft.to_dict(),
            release_digest=request.context_manifest.agent_release_digest,
            context_manifest=request.context_manifest,
            refs=(request.goal_ref, request.input_artifact.artifact_id),
        )
        return ExecutionPlanningResult(draft=draft, output_artifact=artifact)


class FixtureRepairPlanner:
    def __init__(self, patch_mapping: Mapping[str, Any]) -> None:
        self._patch_mapping = _copy_mapping(patch_mapping)

    async def propose_patch(self, request: RepairPlanningRequest) -> RepairPlanningResult:
        patch = PlanPatchDraft.from_mapping(self._patch_mapping)
        artifact = make_planner_artifact(
            kind=PLAN_PATCH_KIND,
            payload=patch.to_dict(),
            release_digest=request.context_manifest.agent_release_digest,
            context_manifest=request.context_manifest,
            refs=(
                request.parent_plan.plan_id,
                request.input_artifact.artifact_id,
                *patch.defect_refs,
                *patch.reused_evidence_refs,
            ),
        )
        return RepairPlanningResult(patch=patch, output_artifact=artifact)


class AgentDriverExecutionPlannerAdapter:
    def __init__(
        self,
        registry: AgentDriverRegistry,
        driver_ref: str,
        *,
        runtime_profile: AgentRuntimeProfile | None = None,
    ) -> None:
        self.registry = registry
        self.driver_ref = driver_ref
        self.runtime_profile = runtime_profile or planner_read_only_runtime_profile("planner/agent-driver")

    async def propose_plan(self, request: ExecutionPlanningRequest) -> ExecutionPlanningResult:
        ensure_planner_runtime_profile(self.runtime_profile)
        driver = _resolve_driver(self.registry, self.driver_ref)
        run_request = AgentRunRequest(
            role=AgentRole.PLANNER,
            run_id=request.context_manifest.run_id,
            expected_output="PlanDraft",
            payload=_planner_driver_payload(request.context_manifest, request.input_artifact),
            workspace_ref=None,
            output_contract=plan_draft_output_contract(),
            runtime_profile=self.runtime_profile,
            metadata={"driverRef": self.driver_ref, "plannerAdapter": "execution"},
        )
        result = await _run_driver(driver, run_request)
        draft = _coerce_plan_draft(result.output)
        artifact = make_planner_artifact(
            kind=PLAN_DRAFT_KIND,
            payload=draft.to_dict(),
            release_digest=request.context_manifest.agent_release_digest,
            context_manifest=request.context_manifest,
            refs=(request.goal_ref, request.input_artifact.artifact_id),
        )
        return ExecutionPlanningResult(draft=draft, output_artifact=artifact)


class AgentDriverRepairPlannerAdapter:
    def __init__(
        self,
        registry: AgentDriverRegistry,
        driver_ref: str,
        *,
        runtime_profile: AgentRuntimeProfile | None = None,
    ) -> None:
        self.registry = registry
        self.driver_ref = driver_ref
        self.runtime_profile = runtime_profile or planner_read_only_runtime_profile("planner/agent-driver")

    async def propose_patch(self, request: RepairPlanningRequest) -> RepairPlanningResult:
        ensure_planner_runtime_profile(self.runtime_profile)
        driver = _resolve_driver(self.registry, self.driver_ref)
        payload = _planner_driver_payload(request.context_manifest, request.input_artifact)
        payload["parentPlan"] = request.parent_plan.to_dict()
        payload["defects"] = [defect.to_dict() for defect in request.defects]
        payload["triggerType"] = request.trigger_type.value
        payload["repairCycle"] = request.repair_cycle
        run_request = AgentRunRequest(
            role=AgentRole.PLANNER,
            run_id=request.context_manifest.run_id,
            expected_output="PlanPatchDraft",
            payload=payload,
            workspace_ref=None,
            output_contract=plan_patch_output_contract(),
            runtime_profile=self.runtime_profile,
            metadata={"driverRef": self.driver_ref, "plannerAdapter": "repair"},
        )
        result = await _run_driver(driver, run_request)
        patch = _coerce_plan_patch(result.output)
        artifact = make_planner_artifact(
            kind=PLAN_PATCH_KIND,
            payload=patch.to_dict(),
            release_digest=request.context_manifest.agent_release_digest,
            context_manifest=request.context_manifest,
            refs=(
                request.parent_plan.plan_id,
                request.input_artifact.artifact_id,
                *patch.defect_refs,
                *patch.reused_evidence_refs,
            ),
        )
        return RepairPlanningResult(patch=patch, output_artifact=artifact)


class AgentDriverAcceptancePlannerAdapter:
    def __init__(
        self,
        registry: AgentDriverRegistry,
        driver_ref: str,
        *,
        runtime_profile: AgentRuntimeProfile | None = None,
    ) -> None:
        self.registry = registry
        self.driver_ref = driver_ref
        self.runtime_profile = runtime_profile or planner_read_only_runtime_profile("planner/agent-driver")

    async def propose_acceptance(self, request: AcceptancePlanningRequest) -> AcceptancePlanningResult:
        ensure_planner_runtime_profile(self.runtime_profile)
        driver = _resolve_driver(self.registry, self.driver_ref)
        payload = _planner_driver_payload(request.context_manifest, request.input_artifact)
        payload["goal"] = {
            "goalId": request.goal.goal_id,
            "version": request.goal.version,
            "objective": request.goal.objective,
            "criteria": [
                {
                    "id": criterion.criterion_id,
                    "statement": criterion.statement,
                    "required": criterion.required,
                }
                for criterion in request.goal.criteria
            ],
        }
        run_request = AgentRunRequest(
            role=AgentRole.PLANNER,
            run_id=request.context_manifest.run_id,
            expected_output="AcceptanceDraft",
            payload=payload,
            workspace_ref=None,
            output_contract=acceptance_output_contract(),
            runtime_profile=self.runtime_profile,
            metadata={"driverRef": self.driver_ref, "plannerAdapter": "acceptance"},
        )
        result = await _run_driver(driver, run_request)
        output = result.output
        if not isinstance(output, Mapping):
            raise PlannerAdapterError(
                PlannerFailure("planner-output-invalid", "Acceptance planner output must be a mapping")
            )
        try:
            claim_graph = ClaimGraph.from_mapping(_mapping(output["claimGraph"]))
            gate_definitions = tuple(
                GateDefinition.from_mapping(_mapping(item)) for item in output["gateDefinitions"]
            )
            gate_plan = GatePlan.from_mapping(_mapping(output["gatePlan"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise PlannerAdapterError(
                PlannerFailure("planner-output-invalid", str(exc), details=(str(exc),))
            ) from exc
        artifact = make_planner_artifact(
            kind=ACCEPTANCE_DRAFT_KIND,
            payload=dict(output),
            release_digest=request.context_manifest.agent_release_digest,
            context_manifest=request.context_manifest,
            refs=(request.goal.goal_id, request.input_artifact.artifact_id),
        )
        return AcceptancePlanningResult(
            claim_graph=claim_graph,
            gate_definitions=gate_definitions,
            gate_plan=gate_plan,
            output_artifact=artifact,
        )


class PlannerOutputValidator:
    def __init__(self, risk_policy: PlannerRiskPolicy | None = None) -> None:
        self.risk_policy = risk_policy or PlannerRiskPolicy()

    def validate_execution_draft(
        self,
        *,
        draft: PlanDraft,
        config: PlanCompilerConfig,
        context_manifest: Any,
        budget_limits: PlannerBudgetLimits,
        risk_level: str | RiskLevel = "R1",
        approval_refs: tuple[str, ...] = (),
        review_refs: tuple[str, ...] = (),
    ) -> PlannerValidationResult:
        tuned_config = replace(config, max_fan_out=budget_limits.max_fan_out)
        output_artifact = make_planner_artifact(
            kind=PLAN_DRAFT_KIND,
            payload=draft.to_dict(),
            release_digest=context_manifest.agent_release_digest,
            context_manifest=context_manifest,
            refs=(draft.goal_ref,),
        )
        compilation = compile_plan_draft(draft, tuned_config)
        errors = list(compilation.report.errors)
        if compilation.plan is not None:
            errors.extend(_budget_limit_errors(compilation.plan.nodes, budget_limits, "PlanDraft"))
        approval_requirement = _approval_requirement(
            _risk_value(risk_level),
            self.risk_policy,
            approval_refs=approval_refs,
            review_refs=review_refs,
        )
        if approval_requirement is not None:
            errors.append(
                PlanValidationError(
                    "planner-approval-required",
                    "plan risk class requires plan review or human approval before execution",
                    "PlanDraft.metadata",
                )
            )
        if errors:
            status = (
                PlannerValidationStatus.APPROVAL_REQUIRED
                if approval_requirement is not None
                else PlannerValidationStatus.REJECTED
            )
            return PlannerValidationResult(
                status=status,
                plan=None,
                report=_planner_report(
                    subject_ref=output_artifact.artifact_id,
                    subject_digest=output_artifact.sha256,
                    errors=errors,
                    refs=(
                        output_artifact.artifact_id,
                        context_manifest.context_manifest_id,
                        *approval_refs,
                        *review_refs,
                    ),
                ),
                output_artifact=output_artifact,
                approval_requirement=approval_requirement,
            )
        assert compilation.plan is not None
        return PlannerValidationResult(
            status=PlannerValidationStatus.ACCEPTED,
            plan=compilation.plan,
            report=_planner_report(
                subject_ref=output_artifact.artifact_id,
                subject_digest=output_artifact.sha256,
                errors=[],
                refs=(output_artifact.artifact_id, context_manifest.context_manifest_id, compilation.report.report_id),
            ),
            output_artifact=output_artifact,
        )

    def validate_repair_patch(
        self,
        *,
        parent: PlanIR,
        patch: PlanPatchDraft,
        config: PlanCompilerConfig,
        context_manifest: Any,
        budget_limits: PlannerBudgetLimits,
        defects: tuple[DefectRecord, ...],
        trigger_type: str | ReplanTriggerType,
        repair_cycle: int,
        allowed_triggers: tuple[ReplanTriggerType, ...] = tuple(ReplanTriggerType),
    ) -> PlannerValidationResult:
        output_artifact = make_planner_artifact(
            kind=PLAN_PATCH_KIND,
            payload=patch.to_dict(),
            release_digest=context_manifest.agent_release_digest,
            context_manifest=context_manifest,
            refs=(parent.plan_id, *patch.defect_refs, *patch.reused_evidence_refs),
        )
        errors = _repair_preflight_errors(
            patch=patch,
            defects=defects,
            trigger_type=trigger_type,
            repair_cycle=repair_cycle,
            budget_limits=budget_limits,
            allowed_triggers=allowed_triggers,
        )
        compilation: PlanCompilationResult | None = None
        if not errors:
            tuned_config = replace(config, max_fan_out=budget_limits.max_fan_out)
            compilation = compile_plan_patch(parent, patch, tuned_config)
            errors.extend(compilation.report.errors)
            if compilation.plan is not None:
                errors.extend(_budget_limit_errors(compilation.plan.nodes, budget_limits, "PlanPatchDraft"))
        if errors:
            return PlannerValidationResult(
                status=PlannerValidationStatus.REJECTED,
                plan=None,
                report=_planner_report(
                    subject_ref=output_artifact.artifact_id,
                    subject_digest=output_artifact.sha256,
                    errors=errors,
                    refs=(
                        output_artifact.artifact_id,
                        context_manifest.context_manifest_id,
                        parent.digest(),
                        *patch.defect_refs,
                        *patch.reused_evidence_refs,
                    ),
                ),
                output_artifact=output_artifact,
            )
        assert compilation is not None
        assert compilation.plan is not None
        return PlannerValidationResult(
            status=PlannerValidationStatus.ACCEPTED,
            plan=compilation.plan,
            report=_planner_report(
                subject_ref=output_artifact.artifact_id,
                subject_digest=output_artifact.sha256,
                errors=[],
                refs=(
                    output_artifact.artifact_id,
                    context_manifest.context_manifest_id,
                    parent.digest(),
                    compilation.report.report_id,
                    *patch.defect_refs,
                    *patch.reused_evidence_refs,
                ),
            ),
            output_artifact=output_artifact,
        )


def plan_draft_output_contract() -> AgentOutputContract:
    return AgentOutputContract(
        name="PlanDraft",
        schema={
            "type": "object",
            "required": ["apiVersion", "kind", "metadata", "spec"],
            "properties": {
                "apiVersion": {"const": "ahra.dev/v1alpha1"},
                "kind": {"const": "PlanDraft"},
                "metadata": {"type": "object"},
                "spec": {"type": "object"},
            },
        },
    )


def plan_patch_output_contract() -> AgentOutputContract:
    return AgentOutputContract(
        name="PlanPatchDraft",
        schema={
            "type": "object",
            "required": ["apiVersion", "kind", "metadata", "spec"],
            "properties": {
                "apiVersion": {"const": "ahra.dev/v1alpha1"},
                "kind": {"const": "PlanPatchDraft"},
                "metadata": {"type": "object"},
                "spec": {"type": "object"},
            },
        },
    )


def acceptance_output_contract() -> AgentOutputContract:
    return AgentOutputContract(
        name="AcceptanceDraft",
        schema={
            "type": "object",
            "required": ["claimGraph", "gateDefinitions", "gatePlan"],
            "properties": {
                "claimGraph": {"type": "object"},
                "gateDefinitions": {"type": "array", "items": {"type": "object"}},
                "gatePlan": {"type": "object"},
            },
        },
    )


def _repair_preflight_errors(
    *,
    patch: PlanPatchDraft,
    defects: tuple[DefectRecord, ...],
    trigger_type: str | ReplanTriggerType,
    repair_cycle: int,
    budget_limits: PlannerBudgetLimits,
    allowed_triggers: tuple[ReplanTriggerType, ...],
) -> list[PlanValidationError]:
    errors: list[PlanValidationError] = []
    try:
        trigger = trigger_type if isinstance(trigger_type, ReplanTriggerType) else ReplanTriggerType(str(trigger_type))
    except ValueError:
        errors.append(
            PlanValidationError("invalid-replan-trigger", "replan trigger is not one of the validated trigger types", "triggerType")
        )
        trigger = None
    if trigger is not None and trigger not in set(allowed_triggers):
        errors.append(
            PlanValidationError("invalid-replan-trigger", f"replan trigger {trigger.value} is not allowed here", "triggerType")
        )
    if repair_cycle >= budget_limits.max_repair_cycles:
        errors.append(
            PlanValidationError("repair-cycle-limit-exceeded", "repair cycle budget is exhausted", "repairCycle")
        )
    if trigger == ReplanTriggerType.DEFECT and not patch.defect_refs:
        errors.append(
            PlanValidationError("missing-defect-ref", "defect-triggered repair must reference at least one Defect", "PlanPatchDraft.spec.defectRefs")
        )
    open_defects = {
        defect.defect_id: defect
        for defect in defects
        if defect.status not in {DefectStatus.RESOLVED, DefectStatus.REJECTED}
    }
    for defect_ref in patch.defect_refs:
        if defect_ref not in open_defects:
            errors.append(PlanValidationError("unknown-defect-ref", f"patch references inactive or unknown Defect {defect_ref}", defect_ref))
    if patch.unchanged_node_refs and not patch.reused_evidence_refs:
        errors.append(
            PlanValidationError(
                "missing-reused-evidence-ref",
                "repair patch must reference reusable Evidence when unchanged nodes are retained",
                "PlanPatchDraft.spec.reusedEvidenceRefs",
            )
        )
    if patch.reused_evidence_refs and not patch.unchanged_node_refs:
        errors.append(
            PlanValidationError(
                "reused-evidence-without-unchanged-node",
                "reused Evidence must be tied to at least one unchanged Plan node",
                "PlanPatchDraft.spec.unchangedNodeRefs",
            )
        )
    return errors


def _budget_limit_errors(
    nodes: tuple[PlanNodeIR, ...],
    limits: PlannerBudgetLimits,
    ref: str,
) -> list[PlanValidationError]:
    errors: list[PlanValidationError] = []
    if len(nodes) > limits.max_plan_nodes:
        errors.append(PlanValidationError("planner-node-limit-exceeded", "Plan node count exceeds planner limit", ref))
    depth = _plan_depth({node.node_id: node.depends_on for node in nodes})
    if depth > limits.max_plan_depth:
        errors.append(PlanValidationError("planner-depth-limit-exceeded", "Plan dependency depth exceeds planner limit", ref))
    model_calls = sum(node.budget.max_model_calls for node in nodes)
    if model_calls > limits.max_model_calls:
        errors.append(PlanValidationError("planner-total-model-calls-exceeded", "Plan maxModelCalls exceeds planner limit", ref))
    tool_calls = sum(node.budget.max_tool_calls for node in nodes)
    if tool_calls > limits.max_tool_calls:
        errors.append(PlanValidationError("planner-total-tool-calls-exceeded", "Plan maxToolCalls exceeds planner limit", ref))
    spawned_nodes = sum(node.budget.max_spawned_nodes for node in nodes)
    if spawned_nodes > limits.max_spawned_nodes:
        errors.append(PlanValidationError("planner-total-spawned-nodes-exceeded", "Plan maxSpawnedNodes exceeds planner limit", ref))
    if limits.max_wall_seconds is not None:
        wall_values = [node.budget.max_wall_seconds for node in nodes]
        if any(value is None for value in wall_values):
            errors.append(PlanValidationError("planner-missing-wall-budget", "Every Plan node must declare maxWallSeconds", ref))
        elif sum(value for value in wall_values if value is not None) > limits.max_wall_seconds:
            errors.append(PlanValidationError("planner-total-wall-budget-exceeded", "Plan maxWallSeconds exceeds planner limit", ref))
    if limits.max_cost_usd is not None:
        cost_values = [node.budget.max_cost_usd for node in nodes]
        if any(value is None for value in cost_values):
            errors.append(PlanValidationError("planner-missing-cost-budget", "Every Plan node must declare maxCostUsd", ref))
        elif sum(value for value in cost_values if value is not None) > limits.max_cost_usd:
            errors.append(PlanValidationError("planner-total-cost-exceeded", "Plan maxCostUsd exceeds planner limit", ref))
    return errors


def _plan_depth(dependencies: Mapping[str, tuple[str, ...]]) -> int:
    memo: dict[str, int] = {}
    visiting: set[str] = set()

    def depth(node_id: str) -> int:
        if node_id in memo:
            return memo[node_id]
        if node_id in visiting:
            return 0
        visiting.add(node_id)
        parent_depth = max((depth(dep) for dep in dependencies.get(node_id, ()) if dep in dependencies), default=0)
        visiting.remove(node_id)
        memo[node_id] = parent_depth + 1
        return memo[node_id]

    return max((depth(node_id) for node_id in dependencies), default=0)


def _approval_requirement(
    risk_level: str,
    policy: PlannerRiskPolicy,
    *,
    approval_refs: tuple[str, ...],
    review_refs: tuple[str, ...],
) -> PlanApprovalRequirement | None:
    required_refs: list[str] = []
    reason_codes: list[str] = []
    if risk_level in set(policy.approval_required_risk_levels) and not approval_refs:
        required_refs.append("approval")
        reason_codes.append("human_approval_required")
    if risk_level in set(policy.plan_review_required_risk_levels) and not review_refs:
        required_refs.append("plan_review")
        reason_codes.append("plan_review_required")
    if not required_refs:
        return None
    return PlanApprovalRequirement(
        risk_level=risk_level,
        reason_code="+".join(reason_codes),
        required_refs=tuple(required_refs),
    )


def _risk_value(value: str | RiskLevel) -> str:
    return value.value if isinstance(value, RiskLevel) else str(value)


def _planner_report(
    *,
    subject_ref: str,
    subject_digest: str,
    errors: list[PlanValidationError],
    refs: tuple[str, ...],
) -> PlanValidationReport:
    digest = canonical_fingerprint(
        {
            "createdBy": PLANNER_ADMISSION_VERSION,
            "errors": [error.to_dict() for error in errors],
            "refs": sorted(refs),
            "subjectDigest": subject_digest,
            "subjectRef": subject_ref,
        }
    ).removeprefix("sha256:")[:16]
    return PlanValidationReport(
        report_id=f"PLANVAL-{digest}",
        subject_ref=subject_ref,
        subject_digest=subject_digest,
        errors=tuple(errors),
        created_by=PLANNER_ADMISSION_VERSION,
        refs=tuple(sorted(refs)),
    )


def _resolve_driver(registry: AgentDriverRegistry, driver_ref: str) -> AgentDriver:
    try:
        return registry.get(driver_ref)
    except ValueError as exc:
        raise PlannerAdapterError(
            PlannerFailure("planner-driver-unavailable", str(exc), retryable=False, details=(driver_ref,))
        ) from exc


async def _run_driver(driver: AgentDriver, request: AgentRunRequest) -> Any:
    try:
        return await driver.run(request)
    except PlannerAdapterError:
        raise
    except AgentOutputContractError as exc:
        raise PlannerAdapterError(
            PlannerFailure("planner-output-contract-failed", exc.message, retryable=False, details=exc.details)
        ) from exc
    except Exception as exc:
        raise PlannerAdapterError(
            PlannerFailure("planner-driver-failed", str(exc), retryable=True, details=(type(exc).__name__,))
        ) from exc


def _coerce_plan_draft(value: Any) -> PlanDraft:
    if isinstance(value, PlanDraft):
        return value
    if isinstance(value, Mapping):
        try:
            validate_agent_output(plan_draft_output_contract(), dict(value), raw_output=value)
            return PlanDraft.from_mapping(value)
        except (AgentOutputContractError, TypeError, ValueError) as exc:
            raise PlannerAdapterError(
                PlannerFailure("planner-output-invalid", str(exc), retryable=False, details=(str(exc),))
            ) from exc
    raise PlannerAdapterError(
        PlannerFailure("planner-output-invalid", "Planner output must be a PlanDraft or mapping", retryable=False)
    )


def _coerce_plan_patch(value: Any) -> PlanPatchDraft:
    if isinstance(value, PlanPatchDraft):
        return value
    if isinstance(value, Mapping):
        try:
            validate_agent_output(plan_patch_output_contract(), dict(value), raw_output=value)
            return PlanPatchDraft.from_mapping(value)
        except (AgentOutputContractError, TypeError, ValueError) as exc:
            raise PlannerAdapterError(
                PlannerFailure("planner-output-invalid", str(exc), retryable=False, details=(str(exc),))
            ) from exc
    raise PlannerAdapterError(
        PlannerFailure("planner-output-invalid", "Planner output must be a PlanPatchDraft or mapping", retryable=False)
    )


def _planner_driver_payload(context_manifest: Any, input_artifact: PlannerArtifact) -> dict[str, Any]:
    return {
        "contextManifest": context_manifest.to_dict(),
        "plannerInputArtifact": input_artifact.to_dict(),
    }


def _copy_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True))


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("expected mapping")
    return value
