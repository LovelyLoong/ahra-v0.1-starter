from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Mapping

from .acceptance_contracts import Claim, ClaimGraph, ClaimType, RiskLevel
from .evidence_v2 import canonical_fingerprint
from .goal_operations import (
    DETERMINISTIC_EXECUTOR_REF,
    DETERMINISTIC_GATE_RUNNER_REF,
    INLINE_PLANNER_REF,
    LOCAL_GOAL_RUNTIME_DIGEST,
    LOCAL_GOAL_RUNTIME_REF,
    M1_PROFILE_REF,
    GoalOperationError,
    GoalOperationProfile,
    GoalOperationProfileRegistry,
)
from .intent_draft import IntentCapabilityNeed, IntentDraft
from .plan_ir import PlanBudget, PlanDraft, PlanNodeDraft, PlanOutputContract, RetryPolicy


NODE_BOUNDED_TASK_DIGEST = "sha256:" + "1" * 64
NODE_GOAL_VERIFICATION_DIGEST = "sha256:" + "2" * 64
GATE_ALIGNMENT_OBJECTIVE_DIGEST = "sha256:" + "3" * 64
GATE_ALIGNMENT_COMPLETION_DIGEST = "sha256:" + "4" * 64


class AlignmentError(ValueError):
    def __init__(self, code: str, message: str, *, refs: tuple[str, ...] = ()) -> None:
        self.code = code
        self.message = message
        self.refs = refs
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class AlignmentRegistry:
    profiles: GoalOperationProfileRegistry = field(default_factory=GoalOperationProfileRegistry)
    node_type_digests: Mapping[str, str] = field(
        default_factory=lambda: {
            "bounded_task": NODE_BOUNDED_TASK_DIGEST,
            "goal_verification": NODE_GOAL_VERIFICATION_DIGEST,
        }
    )
    gate_ref_digests: Mapping[str, str] = field(
        default_factory=lambda: {
            "GATE-alignment-objective": GATE_ALIGNMENT_OBJECTIVE_DIGEST,
            "GATE-alignment-complete": GATE_ALIGNMENT_COMPLETION_DIGEST,
        }
    )

    def resolve_profile(self, profile_ref: str) -> GoalOperationProfile:
        try:
            return self.profiles.get(profile_ref)
        except GoalOperationError as exc:
            raise AlignmentError("unknown_profile_ref", "Intent alignment selected an unknown profile ref", refs=(profile_ref,)) from exc


@dataclass(frozen=True, slots=True)
class AlignmentTurn:
    stage: str
    actor: str
    message: str

    def to_mapping(self) -> dict[str, str]:
        return {"stage": self.stage, "actor": self.actor, "message": self.message}


@dataclass(frozen=True, slots=True)
class AlignmentSession:
    intent: IntentDraft
    stage: str
    turns: tuple[AlignmentTurn, ...] = ()

    def to_mapping(self) -> dict[str, Any]:
        return {
            "intentId": self.intent.intent_id,
            "stage": self.stage,
            "turns": [turn.to_mapping() for turn in self.turns],
        }


@dataclass(frozen=True, slots=True)
class RequestDraft:
    request_id: str
    intent_id: str
    producer_actor: str
    name: str
    idempotency_key: str
    profile_ref: str
    workspace_ref: str
    artifact_dir: str
    store_kind: str
    store_path: str
    planner_adapter_ref: str
    executor_adapter_ref: str
    gate_runner_adapter_ref: str
    runtime_ref: str
    runtime_digest: str
    goal_ref: str
    goal_digest: str
    claim_graph: ClaimGraph
    claim_graph_digest: str
    required_claim_refs: tuple[str, ...]
    registered_node_types: Mapping[str, str]
    registered_gate_refs: Mapping[str, str]
    registered_runtime_refs: Mapping[str, str]
    allowed_capabilities: tuple[str, ...]
    capability_policies: Mapping[str, tuple[str, ...]]
    plan_draft: PlanDraft
    max_repair_cycles: int = 0
    max_concurrency: int = 1
    branch: str = "main"

    def to_mapping(self) -> dict[str, Any]:
        return {
            "apiVersion": "ahra.dev/v1alpha1",
            "kind": "RequestDraft",
            "metadata": {
                "requestId": self.request_id,
                "intentId": self.intent_id,
                "producerActor": self.producer_actor,
                "name": self.name,
                "idempotencyKey": self.idempotency_key,
            },
            "spec": {
                "profileRef": self.profile_ref,
                "workspaceRef": self.workspace_ref,
                "artifactDir": self.artifact_dir,
                "store": {"kind": self.store_kind, "path": self.store_path},
                "planner": {"adapterRef": self.planner_adapter_ref},
                "executor": {"adapterRef": self.executor_adapter_ref},
                "gateRunner": {"adapterRef": self.gate_runner_adapter_ref},
                "runtime": {"runtimeRef": self.runtime_ref, "digest": self.runtime_digest},
                "goal": {
                    "goalRef": self.goal_ref,
                    "goalDigest": self.goal_digest,
                    "claimGraphDigest": self.claim_graph_digest,
                    "requiredClaimRefs": list(self.required_claim_refs),
                },
                "claimGraph": _claim_graph_to_mapping(self.claim_graph),
                "registry": {
                    "nodeTypes": dict(sorted(self.registered_node_types.items())),
                    "gateRefs": dict(sorted(self.registered_gate_refs.items())),
                    "runtimeRefs": dict(sorted(self.registered_runtime_refs.items())),
                    "allowedCapabilities": list(self.allowed_capabilities),
                },
                "capabilityPolicies": {key: list(value) for key, value in sorted(self.capability_policies.items())},
                "execution": {
                    "maxRepairCycles": self.max_repair_cycles,
                    "maxConcurrency": self.max_concurrency,
                    "branch": self.branch,
                },
                "planDraft": self.plan_draft.to_dict(),
            },
        }

    def to_goal_execution_request_mapping(self) -> dict[str, Any]:
        draft = self.to_mapping()
        spec = dict(draft["spec"])
        spec.pop("claimGraph", None)
        spec.pop("capabilityPolicies", None)
        return {
            "apiVersion": "ahra.dev/v1alpha1",
            "kind": "GoalExecutionRequest",
            "metadata": {
                "name": self.name,
                "requestId": self.request_id,
                "idempotencyKey": self.idempotency_key,
            },
            "spec": spec,
        }


class AlignmentWorkflowEngine:
    def __init__(self, registry: AlignmentRegistry | None = None) -> None:
        self.registry = registry or AlignmentRegistry()

    def start(self, intent: IntentDraft) -> AlignmentSession:
        return AlignmentSession(intent=intent, stage="refining_scope")

    def advance(self, session: AlignmentSession, *, actor: str, message: str) -> AlignmentSession:
        if session.stage == "ready":
            raise AlignmentError("alignment_already_ready", "alignment session is already ready to draft a RequestDraft")
        turns = (*session.turns, AlignmentTurn(stage=session.stage, actor=actor, message=message))
        return replace(session, stage=_next_stage(session.stage), turns=turns)

    def draft_request(
        self,
        session: AlignmentSession,
        *,
        profile_ref: str = M1_PROFILE_REF,
        producer_actor: str = "agent:alignment-engine",
        workspace_ref: str = "workspace",
        artifact_dir: str = ".ahra/artifacts",
        store_path: str = ".ahra/goal-control.sqlite3",
    ) -> RequestDraft:
        if session.stage != "ready":
            raise AlignmentError("alignment_not_ready", "multi-turn alignment must reach ready before drafting a request")
        profile = self.registry.resolve_profile(profile_ref)
        goal_ref = _goal_ref_from_intent(session.intent.intent_id)
        claims = _claims_from_intent(goal_ref, session.intent)
        graph = ClaimGraph(goal_ref=goal_ref, version=1, claims=claims)
        required_claim_refs = tuple(claim.claim_id for claim in claims if claim.required)
        plan = _plan_from_intent(goal_ref, session.intent, required_claim_refs, profile.runtime_ref)
        allowed_capabilities = tuple(sorted({need.action for need in session.intent.capability_needs} | {"filesystem.write"}))
        capability_policies = {
            need.action: need.policy_refs
            for need in session.intent.capability_needs
            if need.policy_refs
        }
        return RequestDraft(
            request_id="REQ-" + canonical_fingerprint(session.to_mapping()).removeprefix("sha256:")[:16],
            intent_id=session.intent.intent_id,
            producer_actor=producer_actor,
            name=_request_name(session.intent.intent_id),
            idempotency_key=_request_name(session.intent.intent_id) + "-001",
            profile_ref=profile.profile_ref,
            workspace_ref=workspace_ref,
            artifact_dir=artifact_dir,
            store_kind="sqlite",
            store_path=store_path,
            planner_adapter_ref=profile.planner_adapter_ref,
            executor_adapter_ref=profile.executor_adapter_ref,
            gate_runner_adapter_ref=profile.gate_runner_adapter_ref,
            runtime_ref=profile.runtime_ref,
            runtime_digest=profile.runtime_digest,
            goal_ref=goal_ref,
            goal_digest=canonical_fingerprint({"goalRef": goal_ref, "abstractGoal": session.intent.abstract_goal}),
            claim_graph=graph,
            claim_graph_digest=canonical_fingerprint(_claim_graph_to_mapping(graph)),
            required_claim_refs=required_claim_refs,
            registered_node_types=dict(self.registry.node_type_digests),
            registered_gate_refs=dict(self.registry.gate_ref_digests),
            registered_runtime_refs={profile.runtime_ref: profile.runtime_digest},
            allowed_capabilities=allowed_capabilities,
            capability_policies=capability_policies,
            plan_draft=plan,
        )


def _next_stage(stage: str) -> str:
    order = {
        "refining_scope": "drafting_claims",
        "drafting_claims": "drafting_plan",
        "drafting_plan": "ready",
    }
    if stage not in order:
        raise AlignmentError("unknown_alignment_stage", f"unknown alignment stage: {stage}", refs=(stage,))
    return order[stage]


def _claims_from_intent(goal_ref: str, intent: IntentDraft) -> tuple[Claim, ...]:
    base_claim = Claim(
        claim_id="CLAIM-" + _id_tail(intent.intent_id, "OBJECTIVE"),
        claim_type=ClaimType.FUNCTIONAL,
        statement=intent.abstract_goal,
        criterion_refs=("CRIT-" + _id_tail(intent.intent_id, "OBJECTIVE"),),
        depends_on=(),
        risk_level=RiskLevel(intent.risk_hint or "R1"),
        required_evidence_kinds=("contract_test",),
        gate_refs=("GATE-alignment-objective",),
        required=True,
    )
    completion_claim = Claim(
        claim_id="CLAIM-" + _id_tail(intent.intent_id, "COMPLETE"),
        claim_type=ClaimType.GOVERNANCE,
        statement=f"{goal_ref} reaches completion only from governed evidence.",
        criterion_refs=("CRIT-" + _id_tail(intent.intent_id, "COMPLETE"),),
        depends_on=(base_claim.claim_id,),
        risk_level=RiskLevel.R1,
        required_evidence_kinds=("gate_run",),
        gate_refs=("GATE-alignment-complete",),
        required=True,
    )
    return (base_claim, completion_claim)


def _plan_from_intent(goal_ref: str, intent: IntentDraft, claim_refs: tuple[str, ...], runtime_ref: str) -> PlanDraft:
    objective_claim = claim_refs[0]
    complete_claim = claim_refs[-1]
    capability_requests = tuple(
        _capability_request_from_need(need)
        for need in intent.capability_needs
    )
    if not any(request.capability == "filesystem.write" for request in capability_requests):
        from .plan_ir import CapabilityRequest

        capability_requests = (*capability_requests, CapabilityRequest("filesystem.write", ("outputs/summary.txt",)))
    return PlanDraft(
        goal_ref=goal_ref,
        proposed_by=INLINE_PLANNER_REF,
        rationale="Phase 1 alignment produced an untrusted RequestDraft for admission and authorization.",
        nodes=(
            PlanNodeDraft(
                node_id="NODE-" + _id_tail(intent.intent_id, "WRITE"),
                node_type="bounded_task",
                objective=intent.abstract_goal,
                claim_refs=(objective_claim,),
                depends_on=(),
                input_refs=(intent.intent_id,),
                expected_outputs=(
                    PlanOutputContract(
                        name="phase1-output",
                        schema_ref="schema/phase1-output@sha256:" + "8" * 64,
                        consumer_node_refs=("NODE-" + _id_tail(intent.intent_id, "VERIFY"),),
                    ),
                ),
                capability_requests=capability_requests,
                gate_refs=("GATE-alignment-objective",),
                runtime_ref=runtime_ref,
                budget=PlanBudget(max_model_calls=1, max_tool_calls=2, max_spawned_nodes=0, max_wall_seconds=30, max_cost_usd=0.0),
                retry_policy=RetryPolicy(max_attempts=1, idempotency_key_required=True),
                timeout_seconds=30,
            ),
            PlanNodeDraft(
                node_id="NODE-" + _id_tail(intent.intent_id, "VERIFY"),
                node_type="goal_verification",
                objective="Verify Phase 1 aligned request completion.",
                claim_refs=(objective_claim, complete_claim),
                depends_on=("NODE-" + _id_tail(intent.intent_id, "WRITE"),),
                input_refs=("NODE-" + _id_tail(intent.intent_id, "WRITE"),),
                expected_outputs=(),
                capability_requests=(),
                gate_refs=("GATE-alignment-complete",),
                runtime_ref=runtime_ref,
                budget=PlanBudget(max_model_calls=1, max_tool_calls=1, max_spawned_nodes=0, max_wall_seconds=30, max_cost_usd=0.0),
                retry_policy=RetryPolicy(max_attempts=1),
                timeout_seconds=30,
                terminal_goal_verification=True,
            ),
        ),
    )


def _capability_request_from_need(need: IntentCapabilityNeed):
    from .plan_ir import CapabilityRequest

    return CapabilityRequest(
        need.action,
        need.resources,
        risk_level=need.risk_level,
        approval_refs=need.policy_refs,
    )


def _claim_graph_to_mapping(graph: ClaimGraph) -> dict[str, Any]:
    return {
        "apiVersion": "ahra.dev/v1alpha1",
        "kind": "ClaimGraph",
        "metadata": {
            "name": graph.goal_ref.removeprefix("GOAL-").lower(),
            "goalId": graph.goal_ref,
            "version": graph.version,
        },
        "spec": {
            "goalRef": graph.goal_ref,
            "claims": [
                {
                    "id": claim.claim_id,
                    "type": claim.claim_type.value,
                    "statement": claim.statement,
                    "criterionRefs": list(claim.criterion_refs),
                    "dependsOn": list(claim.depends_on),
                    "riskLevel": claim.risk_level.value,
                    "required": claim.required,
                    "requiredEvidenceKinds": list(claim.required_evidence_kinds),
                    "gateRefs": list(claim.gate_refs),
                    "approvalRequired": claim.approval_required,
                }
                for claim in graph.claims
            ],
        },
    }


def _goal_ref_from_intent(intent_id: str) -> str:
    return "GOAL-" + _id_tail(intent_id, "ALIGNED")


def _request_name(intent_id: str) -> str:
    return ("phase1-" + intent_id.lower().replace("_", "-").replace(".", "-").removeprefix("intent-"))[:63]


def _id_tail(intent_id: str, fallback: str) -> str:
    cleaned = "".join(char if char.isalnum() else "-" for char in intent_id.upper())
    cleaned = cleaned.removeprefix("INTENT-").strip("-")
    if not cleaned:
        return fallback
    return f"{cleaned}-{fallback}"


__all__ = [
    "AlignmentError",
    "AlignmentRegistry",
    "AlignmentSession",
    "AlignmentTurn",
    "AlignmentWorkflowEngine",
    "RequestDraft",
]
