from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from typing import Any, Mapping

from .acceptance_contracts import ClaimGraph
from .approval_service import ApprovalRecord
from .request_draft import (
    RequestDraft,
    RequestDraftError,
    RequestDraftRegistry,
    _claim_graph_to_mapping,
    _goal_ref_from_intent,
    _request_id,
    _request_name,
)
from .evidence_v2 import canonical_fingerprint
from .goal_operations import (
    DEVELOPMENT_BOUNDED_PROFILE_REF,
    GoalOperationError,
    GoalOperationProfile,
    GoalOperationProfileRegistry,
)
from .intent_draft import IntentDraft
from .plan_ir import PlanDraft
from .ports import (
    AgentDriver,
    AgentOutputContract,
    AgentRole,
    AgentRunRequest,
    AgentRuntimeProfile,
    ApprovalService as ApprovalServicePort,
)


ALIGNMENT_DECISION_OUTPUT = "AlignmentTurnDecision"
REQUIREMENT_DRAFT_OUTPUT = "RequirementDraft"
ACCEPTANCE_DRAFT_OUTPUT = "AcceptanceDraft"
DEFAULT_AGENT_TIMEOUT_SECONDS = 60.0


class AlignmentSessionError(ValueError):
    """Structured failure for alignment-session contract violations."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        ref: str,
        refs: tuple[str, ...] = (),
        data: Mapping[str, Any] | None = None,
        snapshot: Any | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.ref = ref
        self.refs = refs or (ref,)
        self.data = dict(data or {})
        self.snapshot = snapshot
        super().__init__(f"{code} {ref}: {message}")

    def to_dict(self) -> dict[str, Any]:
        payload = {"code": self.code, "message": self.message, "ref": self.ref, "refs": list(self.refs)}
        if self.data:
            payload["data"] = self.data
        return payload


@dataclass(frozen=True, slots=True)
class AlignmentSessionTurn:
    index: int
    actor: str
    message: str
    expected_output: str | None = None
    trace_ref: str | None = None
    error: Mapping[str, Any] | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "AlignmentSessionTurn":
        return cls(
            index=int(data["index"]),
            actor=str(data["actor"]),
            message=str(data["message"]),
            expected_output=str(data["expectedOutput"]) if data.get("expectedOutput") else None,
            trace_ref=str(data["traceRef"]) if data.get("traceRef") else None,
            error=_mapping(data["error"], "turn.error") if data.get("error") else None,
        )

    def to_mapping(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "index": self.index,
            "actor": self.actor,
            "message": self.message,
        }
        if self.expected_output:
            data["expectedOutput"] = self.expected_output
        if self.trace_ref:
            data["traceRef"] = self.trace_ref
        if self.error:
            data["error"] = dict(self.error)
        return data


@dataclass(frozen=True, slots=True)
class AlignmentSessionSnapshot:
    session_id: str
    intent: IntentDraft
    profile_ref: str
    runtime_ref: str
    runtime_digest: str
    workspace_ref: str
    artifact_dir: str
    store_path: str
    producer_actor: str
    stage: str = "dialogue"
    turns: tuple[AlignmentSessionTurn, ...] = ()
    frozen_requirement: str | None = None
    requirement_approved_by: str | None = None
    missing_dimensions: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "AlignmentSessionSnapshot":
        return cls(
            session_id=str(data["sessionId"]),
            intent=IntentDraft.from_mapping(_mapping(data["intent"], "intent")),
            profile_ref=str(data["profileRef"]),
            runtime_ref=str(data["runtimeRef"]),
            runtime_digest=str(data["runtimeDigest"]),
            workspace_ref=str(data["workspaceRef"]),
            artifact_dir=str(data["artifactDir"]),
            store_path=str(data["storePath"]),
            producer_actor=str(data["producerActor"]),
            stage=str(data.get("stage") or "dialogue"),
            turns=tuple(AlignmentSessionTurn.from_mapping(_mapping(item, "turn")) for item in data.get("turns", ())),
            frozen_requirement=str(data["frozenRequirement"]) if data.get("frozenRequirement") else None,
            requirement_approved_by=str(data["requirementApprovedBy"]) if data.get("requirementApprovedBy") else None,
            missing_dimensions=tuple(str(item) for item in data.get("missingDimensions", ())),
        )

    @property
    def next_turn_index(self) -> int:
        return len(self.turns) + 1

    def append_turn(
        self,
        *,
        actor: str,
        message: str,
        expected_output: str | None = None,
        trace_ref: str | None = None,
        error: Mapping[str, Any] | None = None,
    ) -> "AlignmentSessionSnapshot":
        return replace(
            self,
            turns=(
                *self.turns,
                AlignmentSessionTurn(
                    index=self.next_turn_index,
                    actor=actor,
                    message=message,
                    expected_output=expected_output,
                    trace_ref=trace_ref,
                    error=error,
                ),
            ),
        )

    def to_mapping(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "sessionId": self.session_id,
            "intent": self.intent.to_mapping(),
            "profileRef": self.profile_ref,
            "runtimeRef": self.runtime_ref,
            "runtimeDigest": self.runtime_digest,
            "workspaceRef": self.workspace_ref,
            "artifactDir": self.artifact_dir,
            "storePath": self.store_path,
            "producerActor": self.producer_actor,
            "stage": self.stage,
            "turns": [turn.to_mapping() for turn in self.turns],
            "missingDimensions": list(self.missing_dimensions),
        }
        if self.frozen_requirement:
            data["frozenRequirement"] = self.frozen_requirement
        if self.requirement_approved_by:
            data["requirementApprovedBy"] = self.requirement_approved_by
        return data


@dataclass(frozen=True, slots=True)
class AlignmentSessionResult:
    snapshot: AlignmentSessionSnapshot
    request_draft: RequestDraft
    approval_record: ApprovalRecord | None = None


class AlignmentSessionManager:
    """AgentDriver-backed Workflow A session manager.

    The manager owns state transitions only. It asks provider-neutral
    AgentDrivers for dialogue, requirement, and acceptance drafts, then emits an
    untrusted RequestDraft for RequestDraftAdmission / ApprovalService to handle.
    """

    def __init__(
        self,
        agent_driver: AgentDriver,
        *,
        registry: RequestDraftRegistry | None = None,
        profile_registry: GoalOperationProfileRegistry | None = None,
        default_profile_ref: str = DEVELOPMENT_BOUNDED_PROFILE_REF,
        max_dialogue_turns: int = 8,
        agent_timeout_seconds: float = DEFAULT_AGENT_TIMEOUT_SECONDS,
    ) -> None:
        if registry is not None and profile_registry is not None:
            raise ValueError("pass either registry or profile_registry, not both")
        self.agent_driver = agent_driver
        self.registry = registry or RequestDraftRegistry(profiles=profile_registry or GoalOperationProfileRegistry())
        self.default_profile_ref = default_profile_ref
        self.max_dialogue_turns = max_dialogue_turns
        self.agent_timeout_seconds = _positive_timeout_seconds(agent_timeout_seconds)

    def start(
        self,
        intent: IntentDraft,
        *,
        profile_ref: str | None = None,
        runtime_ref: str | None = None,
        runtime_digest: str | None = None,
        workspace_ref: str = "workspace",
        artifact_dir: str = ".ahra/artifacts",
        store_path: str = ".ahra/goal-control.sqlite3",
        producer_actor: str = "agent:alignment-session",
    ) -> AlignmentSessionSnapshot:
        selected_profile_ref = profile_ref or _context_string(intent, "profileRef") or self.default_profile_ref
        selected_runtime_ref = runtime_ref or _context_string(intent, "runtimeRef")
        selected_runtime_digest = runtime_digest or _context_string(intent, "runtimeDigest")
        profile = self._resolve_profile(
            selected_profile_ref,
            runtime_ref=selected_runtime_ref,
            runtime_digest=selected_runtime_digest,
        )
        return AlignmentSessionSnapshot(
            session_id=_session_id(intent, selected_profile_ref, workspace_ref),
            intent=intent,
            profile_ref=profile.profile_ref,
            runtime_ref=profile.runtime_ref,
            runtime_digest=profile.runtime_digest,
            workspace_ref=workspace_ref,
            artifact_dir=artifact_dir,
            store_path=store_path,
            producer_actor=producer_actor,
        )

    def resume_from_snapshot(self, snapshot: AlignmentSessionSnapshot | Mapping[str, Any]) -> AlignmentSessionSnapshot:
        if isinstance(snapshot, AlignmentSessionSnapshot):
            self._resolve_profile(snapshot.profile_ref, runtime_ref=snapshot.runtime_ref, runtime_digest=snapshot.runtime_digest)
            return snapshot
        restored = AlignmentSessionSnapshot.from_mapping(snapshot)
        self._resolve_profile(restored.profile_ref, runtime_ref=restored.runtime_ref, runtime_digest=restored.runtime_digest)
        return restored

    async def advance(
        self,
        snapshot: AlignmentSessionSnapshot | Mapping[str, Any],
        user_message: str,
        *,
        actor: str = "human:maintainer",
    ) -> AlignmentSessionSnapshot:
        current = self.resume_from_snapshot(snapshot)
        if current.stage not in {"dialogue", "awaiting_user"}:
            raise AlignmentSessionError(
                "alignment_not_accepting_dialogue",
                "only dialogue snapshots can accept another user turn",
                ref="session.stage",
            )
        if len(current.turns) >= self.max_dialogue_turns * 2:
            raise AlignmentSessionError("alignment_turn_limit", "alignment dialogue exceeded configured turn limit", ref="session.turns")
        after_user = current.append_turn(actor=actor, message=user_message)
        try:
            driver_output = await self._run_agent(
                after_user,
                expected_output=ALIGNMENT_DECISION_OUTPUT,
                payload={
                    "phase": "alignment-dialogue",
                    "intent": after_user.intent.to_mapping(),
                    "session": after_user.to_mapping(),
                    "userMessage": user_message,
                    "checklist": [
                        "output form",
                        "must-haves",
                        "must-nots",
                        "completion signal",
                        "allowed free zones",
                    ],
                },
            )
        except AlignmentSessionError as exc:
            if exc.code == "agent_driver_timeout":
                exc.snapshot = self._snapshot_with_agent_error(after_user, exc, stage="awaiting_user")
            raise
        decision = _mapping(driver_output.output, ALIGNMENT_DECISION_OUTPUT)
        agent_message = _required_string(decision, "message", ALIGNMENT_DECISION_OUTPUT)
        converged = bool(decision.get("converged", False))
        frozen_requirement = _optional_string(decision.get("frozenRequirement") or decision.get("frozen_requirement"))
        if converged and not frozen_requirement:
            raise AlignmentSessionError(
                "missing_frozen_requirement",
                "converged alignment turn must include frozenRequirement",
                ref="agentOutput.frozenRequirement",
            )
        after_agent = after_user.append_turn(
            actor="agent:alignment",
            message=agent_message,
            expected_output=ALIGNMENT_DECISION_OUTPUT,
            trace_ref=driver_output.trace_ref,
        )
        return replace(
            after_agent,
            stage="awaiting_requirement_approval" if converged else "awaiting_user",
            frozen_requirement=frozen_requirement or after_agent.frozen_requirement,
            missing_dimensions=_string_tuple(decision.get("missingDimensions") or decision.get("missing_dimensions")),
        )

    def approve_requirement(
        self,
        snapshot: AlignmentSessionSnapshot | Mapping[str, Any],
        *,
        actor: str,
    ) -> AlignmentSessionSnapshot:
        current = self.resume_from_snapshot(snapshot)
        if current.stage != "awaiting_requirement_approval" or not current.frozen_requirement:
            raise AlignmentSessionError(
                "requirement_approval_not_waiting",
                "requirement approval requires an agent-proposed frozen requirement",
                ref="session.stage",
            )
        if actor == current.producer_actor:
            raise AlignmentSessionError(
                "producer_cannot_approve_requirement",
                "requirement freeze requires a human actor distinct from producer",
                ref="approval.actor",
                refs=(actor,),
            )
        if not actor.startswith("human:"):
            raise AlignmentSessionError(
                "requirement_approval_requires_human",
                "requirement freeze requires explicit human confirmation",
                ref="approval.actor",
                refs=(actor,),
            )
        return replace(current, stage="frozen", requirement_approved_by=actor)

    async def draft_request(
        self,
        snapshot: AlignmentSessionSnapshot | Mapping[str, Any],
        *,
        approval_service: ApprovalServicePort | None = None,
    ) -> AlignmentSessionResult:
        current = self.resume_from_snapshot(snapshot)
        if current.stage == "awaiting_requirement_approval":
            raise AlignmentSessionError(
                "requirement_not_approved",
                "request drafting requires Human Gate 1 requirement approval",
                ref="session.requirementApprovedBy",
            )
        if current.stage != "frozen" or not current.frozen_requirement:
            raise AlignmentSessionError(
                "alignment_not_frozen",
                "request drafting requires a frozen requirement snapshot",
                ref="session.frozenRequirement",
            )
        try:
            claim_id_prefix = f"CLM-{current.intent.intent_id.upper().replace('INTENT-', '')}"
            goal_ref = _goal_ref_from_intent(current.intent.intent_id)
            requirement_result = await self._run_agent(
                current,
                expected_output=REQUIREMENT_DRAFT_OUTPUT,
                payload={
                    "phase": "requirement-draft",
                    "intent": current.intent.to_mapping(),
                    "frozenRequirement": current.frozen_requirement,
                    "profileRef": current.profile_ref,
                    "runtimeRef": current.runtime_ref,
                    "coordinationRules": {
                        "claimIdPrefix": claim_id_prefix,
                        "claimIdFormat": f"{claim_id_prefix}-<SHORT-DESCRIPTOR>",
                        "instruction": f"When referencing acceptance claims in your PlanDraft nodes, use claim IDs that start with '{claim_id_prefix}-'. The Acceptance Agent will use the same prefix. Keep descriptors short (1-3 uppercase words with hyphens).",
                    },
                    "goalRef": goal_ref,
                },
            )
            acceptance_result = await self._run_agent(
                current,
                expected_output=ACCEPTANCE_DRAFT_OUTPUT,
                payload={
                    "phase": "acceptance-draft",
                    "intent": current.intent.to_mapping(),
                    "frozenRequirement": current.frozen_requirement,
                    "profileRef": current.profile_ref,
                    "runtimeRef": current.runtime_ref,
                    "coordinationRules": {
                        "claimIdPrefix": claim_id_prefix,
                        "claimIdFormat": f"{claim_id_prefix}-<SHORT-DESCRIPTOR>",
                        "instruction": f"All claim IDs in your ClaimGraph must start with '{claim_id_prefix}-' followed by a short descriptor (1-3 uppercase words with hyphens, e.g. '{claim_id_prefix}-LINT-PASS'). The Requirement Agent will reference claims using the same prefix.",
                    },
                    "goalRef": goal_ref,
                },
            )
        except AlignmentSessionError as exc:
            if exc.code == "agent_driver_timeout":
                exc.snapshot = self._snapshot_with_agent_error(current, exc, stage="frozen")
            raise
        requirement = _mapping(requirement_result.output, REQUIREMENT_DRAFT_OUTPUT)
        acceptance = _mapping(acceptance_result.output, ACCEPTANCE_DRAFT_OUTPUT)
        request_draft = self._request_from_agent_outputs(current, requirement, acceptance)
        final_snapshot = replace(
            current.append_turn(
                actor="agent:requirement",
                message=_summary(requirement, "requirement draft produced"),
                expected_output=REQUIREMENT_DRAFT_OUTPUT,
                trace_ref=requirement_result.trace_ref,
            ).append_turn(
                actor="agent:acceptance",
                message=_summary(acceptance, "acceptance draft produced"),
                expected_output=ACCEPTANCE_DRAFT_OUTPUT,
                trace_ref=acceptance_result.trace_ref,
            ),
            stage="request_drafted",
        )
        approval_record = None
        if approval_service is not None:
            approval_record = approval_service.request_authorization(request_draft, actor=current.producer_actor)
        return AlignmentSessionResult(
            snapshot=final_snapshot,
            request_draft=request_draft,
            approval_record=approval_record,
        )

    async def run(
        self,
        intent: IntentDraft,
        user_messages: tuple[str, ...] | list[str],
        *,
        requirement_approval_actor: str | None = None,
        **start_kwargs: Any,
    ) -> AlignmentSessionResult:
        snapshot = self.start(intent, **start_kwargs)
        for message in user_messages:
            snapshot = await self.advance(snapshot, str(message))
            if snapshot.stage == "awaiting_requirement_approval":
                if requirement_approval_actor is not None:
                    snapshot = self.approve_requirement(snapshot, actor=requirement_approval_actor)
                break
        return await self.draft_request(snapshot)

    async def _run_agent(self, snapshot: AlignmentSessionSnapshot, *, expected_output: str, payload: dict[str, Any]) -> Any:
        request = AgentRunRequest(
            role=AgentRole.PLANNER,
            run_id=f"{snapshot.session_id}:{expected_output}:{snapshot.next_turn_index}",
            expected_output=expected_output,
            payload=payload,
            workspace_ref=snapshot.workspace_ref,
            output_contract=_output_contract(expected_output),
            runtime_profile=AgentRuntimeProfile(
                profile_ref=f"alignment-session/{snapshot.profile_ref}",
                sandbox="read_only",
                capabilities=(),
            ),
            metadata={"alignmentSessionId": snapshot.session_id, "stage": snapshot.stage},
        )
        task = asyncio.create_task(self.agent_driver.run(request))
        try:
            return await asyncio.wait_for(asyncio.shield(task), timeout=self.agent_timeout_seconds)
        except asyncio.TimeoutError as exc:
            task.cancel()
            task.add_done_callback(_consume_cancelled_task)
            raise self._timeout_error(snapshot, expected_output) from exc

    def _timeout_error(self, snapshot: AlignmentSessionSnapshot, expected_output: str) -> AlignmentSessionError:
        return AlignmentSessionError(
            "agent_driver_timeout",
            f"AgentDriver timed out while producing {expected_output}",
            ref="agentDriver.timeout",
            refs=(expected_output, snapshot.stage),
            data={
                "expectedOutput": expected_output,
                "timeoutSeconds": self.agent_timeout_seconds,
                "alignmentSessionId": snapshot.session_id,
            },
        )

    def _snapshot_with_agent_error(
        self,
        snapshot: AlignmentSessionSnapshot,
        error: AlignmentSessionError,
        *,
        stage: str,
    ) -> AlignmentSessionSnapshot:
        expected_output = str(error.data.get("expectedOutput") or "AgentDriver")
        return replace(
            snapshot.append_turn(
                actor="agent:error",
                message=error.message,
                expected_output=expected_output,
                error=error.to_dict(),
            ),
            stage=stage,
        )

    def _resolve_profile(
        self,
        profile_ref: str,
        *,
        runtime_ref: str | None = None,
        runtime_digest: str | None = None,
    ) -> GoalOperationProfile:
        try:
            profile = self.registry.resolve_profile(profile_ref)
        except (RequestDraftError, GoalOperationError) as exc:
            raise AlignmentSessionError(
                "unknown_profile_ref",
                f"unknown Goal operation profile: {profile_ref}",
                ref="spec.profileRef",
                refs=(profile_ref,),
            ) from exc
        if runtime_ref is not None and runtime_ref != profile.runtime_ref:
            raise AlignmentSessionError(
                "unknown_runtime_ref",
                "runtimeRef is not registered for selected profile",
                ref="spec.runtime.runtimeRef",
                refs=(profile_ref, runtime_ref),
            )
        if runtime_digest is not None and runtime_digest != profile.runtime_digest:
            raise AlignmentSessionError(
                "runtime_digest_mismatch",
                "runtime digest does not match selected profile registry",
                ref="spec.runtime.digest",
                refs=(profile_ref, runtime_digest),
            )
        return profile

    def _request_from_agent_outputs(
        self,
        snapshot: AlignmentSessionSnapshot,
        requirement: Mapping[str, Any],
        acceptance: Mapping[str, Any],
    ) -> RequestDraft:
        profile = self._resolve_profile(snapshot.profile_ref, runtime_ref=snapshot.runtime_ref, runtime_digest=snapshot.runtime_digest)
        aligned_intent = replace(snapshot.intent, abstract_goal=_summary(requirement, snapshot.frozen_requirement or snapshot.intent.abstract_goal))
        goal_ref = _goal_ref_from_intent(aligned_intent.intent_id)
        claim_graph = _claim_graph_from_output(acceptance)
        required_claim_refs = tuple(claim.claim_id for claim in claim_graph.claims if claim.required)
        plan = _plan_from_output(requirement)
        allowed_capabilities = tuple(sorted({need.action for need in aligned_intent.capability_needs} | {"filesystem.write"}))
        capability_policies = {need.action: need.policy_refs for need in aligned_intent.capability_needs if need.policy_refs}
        goal_digest = canonical_fingerprint({"goalRef": goal_ref, "abstractGoal": aligned_intent.abstract_goal})
        claim_graph_digest = canonical_fingerprint(_claim_graph_to_mapping(claim_graph))
        return RequestDraft(
            request_id=_request_id(
                aligned_intent,
                profile=profile,
                producer_actor=snapshot.producer_actor,
                workspace_ref=snapshot.workspace_ref,
                artifact_dir=snapshot.artifact_dir,
                store_path=snapshot.store_path,
                goal_ref=goal_ref,
                goal_digest=goal_digest,
                claim_graph_digest=claim_graph_digest,
                required_claim_refs=required_claim_refs,
                allowed_capabilities=allowed_capabilities,
                capability_policies=capability_policies,
                plan=plan,
            ),
            intent_id=aligned_intent.intent_id,
            producer_actor=snapshot.producer_actor,
            name=_request_name(aligned_intent.intent_id),
            idempotency_key=_request_name(aligned_intent.intent_id) + "-001",
            profile_ref=profile.profile_ref,
            workspace_ref=snapshot.workspace_ref,
            artifact_dir=snapshot.artifact_dir,
            store_kind="sqlite",
            store_path=snapshot.store_path,
            planner_adapter_ref=profile.planner_adapter_ref,
            executor_adapter_ref=profile.executor_adapter_ref,
            gate_runner_adapter_ref=profile.gate_runner_adapter_ref,
            runtime_ref=profile.runtime_ref,
            runtime_digest=profile.runtime_digest,
            goal_ref=goal_ref,
            goal_digest=goal_digest,
            claim_graph=claim_graph,
            claim_graph_digest=claim_graph_digest,
            required_claim_refs=required_claim_refs,
            registered_node_types=dict(self.registry.node_type_digests),
            registered_gate_refs=dict(self.registry.gate_ref_digests),
            registered_runtime_refs={profile.runtime_ref: profile.runtime_digest},
            allowed_capabilities=allowed_capabilities,
            capability_policies=capability_policies,
            plan_draft=plan,
        )


def _output_contract(expected_output: str) -> AgentOutputContract:
    schema: dict[str, Any]
    if expected_output == ALIGNMENT_DECISION_OUTPUT:
        schema = {
            "type": "object",
            "additionalProperties": True,
            "required": ["message", "converged"],
            "properties": {
                "message": {"type": "string", "minLength": 1},
                "converged": {"type": "boolean"},
                "frozenRequirement": {"type": "string"},
                "missingDimensions": {"type": "array", "items": {"type": "string"}},
            },
        }
    elif expected_output == REQUIREMENT_DRAFT_OUTPUT:
        schema = {
            "type": "object",
            "additionalProperties": True,
            "properties": {
                "summary": {"type": "string", "minLength": 1},
                "planDraft": {
                    "type": "object",
                    "required": ["apiVersion", "kind", "metadata", "spec"],
                    "properties": {
                        "apiVersion": {"type": "string", "const": "ahra.dev/v1alpha1"},
                        "kind": {"type": "string", "const": "PlanDraft"},
                        "metadata": {
                            "type": "object",
                            "required": ["goalId", "proposedBy"],
                            "properties": {
                                "goalId": {"type": "string"},
                                "proposedBy": {"type": "string"},
                            },
                        },
                        "spec": {
                            "type": "object",
                            "required": ["nodes"],
                            "properties": {
                                "rationale": {"type": "string"},
                                "nodes": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "required": ["id", "nodeType", "objective", "budgetRequest"],
                                        "properties": {
                                            "id": {"type": "string"},
                                            "nodeType": {"type": "string"},
                                            "objective": {"type": "string"},
                                            "claimRefs": {"type": "array", "items": {"type": "string"}},
                                            "dependsOn": {"type": "array", "items": {"type": "string"}},
                                            "inputRefs": {"type": "array", "items": {"type": "string"}},
                                            "expectedOutputs": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object",
                                                    "required": ["name", "schemaRef"],
                                                    "properties": {
                                                        "name": {"type": "string"},
                                                        "schemaRef": {"type": "string"},
                                                        "consumerNodeRefs": {"type": "array", "items": {"type": "string"}},
                                                        "deliveryRole": {"type": "string"},
                                                        "artifactRequired": {"type": "boolean"},
                                                    },
                                                },
                                            },
                                            "capabilityRequests": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object",
                                                    "required": ["capability", "resources"],
                                                    "properties": {
                                                        "capability": {"type": "string"},
                                                        "resources": {"type": "array", "items": {"type": "string"}},
                                                        "riskLevel": {"type": "string"},
                                                        "approvalRefs": {"type": "array", "items": {"type": "string"}},
                                                    },
                                                },
                                            },
                                            "gateRefs": {"type": "array", "items": {"type": "string"}},
                                            "runtimeRef": {"type": "string"},
                                            "budgetRequest": {
                                                "type": "object",
                                                "required": ["maxModelCalls", "maxToolCalls"],
                                                "properties": {
                                                    "maxModelCalls": {"type": "integer"},
                                                    "maxToolCalls": {"type": "integer"},
                                                    "maxSpawnedNodes": {"type": "integer"},
                                                    "maxWallSeconds": {"type": "integer"},
                                                    "maxCostUsd": {"type": "number"},
                                                },
                                            },
                                            "retryPolicy": {
                                                "type": "object",
                                                "properties": {
                                                    "maxAttempts": {"type": "integer"},
                                                    "backoffSeconds": {"type": "number"},
                                                    "idempotencyKeyRequired": {"type": "boolean"},
                                                },
                                            },
                                            "timeoutSeconds": {"type": "integer"},
                                            "compensationRef": {"type": "string"},
                                            "sideEffect": {"type": "string"},
                                            "terminalGoalVerification": {"type": "boolean"},
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        }
    elif expected_output == ACCEPTANCE_DRAFT_OUTPUT:
        schema = {
            "type": "object",
            "additionalProperties": True,
            "properties": {
                "summary": {"type": "string", "minLength": 1},
                "claimGraph": {
                    "type": "object",
                    "required": ["apiVersion", "kind", "metadata", "spec"],
                    "properties": {
                        "apiVersion": {"type": "string", "const": "ahra.dev/v1alpha1"},
                        "kind": {"type": "string", "const": "ClaimGraph"},
                        "metadata": {
                            "type": "object",
                            "required": ["version"],
                            "properties": {
                                "version": {"type": "integer"},
                            },
                        },
                        "spec": {
                            "type": "object",
                            "required": ["goalRef", "claims"],
                            "properties": {
                                "goalRef": {"type": "string"},
                                "claims": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "required": ["id", "type", "statement", "criterionRefs", "riskLevel", "requiredEvidenceKinds"],
                                        "properties": {
                                            "id": {"type": "string"},
                                            "type": {
                                                "type": "string",
                                                "enum": ["functional", "structural", "quality", "security", "operational", "governance"],
                                            },
                                            "statement": {"type": "string"},
                                            "criterionRefs": {"type": "array", "items": {"type": "string"}},
                                            "dependsOn": {"type": "array", "items": {"type": "string"}},
                                            "riskLevel": {
                                                "type": "string",
                                                "enum": ["R0", "R1", "R2", "R3"],
                                            },
                                            "requiredEvidenceKinds": {"type": "array", "items": {"type": "string"}},
                                            "gateRefs": {"type": "array", "items": {"type": "string"}},
                                            "approvalRequired": {"type": "boolean"},
                                            "required": {"type": "boolean"},
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        }
    else:
        raise ValueError(f"unsupported alignment output contract: {expected_output}")
    return AgentOutputContract(name=expected_output, schema=schema, example=None)


def _claim_graph_from_output(output: Mapping[str, Any]) -> ClaimGraph:
    claim_graph_data = output.get("claimGraph") or output.get("claim_graph")
    if claim_graph_data is not None:
        return ClaimGraph.from_mapping(_mapping(claim_graph_data, "claimGraph"))
    if output.get("kind") == "ClaimGraph":
        return ClaimGraph.from_mapping(output)
    raise AlignmentSessionError(
        "missing_claim_graph",
        "Acceptance Agent output must include an explicit ClaimGraph",
        ref="agentOutput.claimGraph",
    )


def _plan_from_output(output: Mapping[str, Any]) -> PlanDraft:
    plan_data = output.get("planDraft") or output.get("plan_draft")
    if plan_data is not None:
        return PlanDraft.from_mapping(_mapping(plan_data, "planDraft"))
    if output.get("kind") == "PlanDraft":
        return PlanDraft.from_mapping(output)
    raise AlignmentSessionError(
        "missing_plan_draft",
        "Requirement Agent output must include an explicit PlanDraft",
        ref="agentOutput.planDraft",
    )


def _mapping(value: Any, ref: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AlignmentSessionError("invalid_mapping", f"{ref} must be a mapping", ref=ref)
    return value


def _positive_timeout_seconds(value: float) -> float:
    timeout = float(value)
    if timeout <= 0:
        raise ValueError("agent timeout must be greater than zero seconds")
    return timeout


def _consume_cancelled_task(task: asyncio.Task[Any]) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        return
    except Exception:
        return


def _required_string(data: Mapping[str, Any], key: str, ref: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AlignmentSessionError("missing_string", f"{key} must be a non-empty string", ref=f"{ref}.{key}")
    return value


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise AlignmentSessionError("invalid_string_list", "value must be a list of strings", ref="agentOutput.missingDimensions")
    return tuple(str(item) for item in value)


def _summary(data: Mapping[str, Any], fallback: str) -> str:
    for key in ("summary", "requirement", "frozenRequirement", "objective"):
        value = _optional_string(data.get(key))
        if value:
            return value
    return fallback


def _context_string(intent: IntentDraft, key: str) -> str | None:
    value = intent.context.get(key)
    return value if isinstance(value, str) and value.strip() else None


def _session_id(intent: IntentDraft, profile_ref: str, workspace_ref: str) -> str:
    digest = canonical_fingerprint(
        {
            "intent": intent.to_mapping(),
            "profileRef": profile_ref,
            "workspaceRef": workspace_ref,
        }
    )
    return "ASESS-" + digest.removeprefix("sha256:")[:16]


__all__ = [
    "ACCEPTANCE_DRAFT_OUTPUT",
    "ALIGNMENT_DECISION_OUTPUT",
    "DEFAULT_AGENT_TIMEOUT_SECONDS",
    "REQUIREMENT_DRAFT_OUTPUT",
    "AlignmentSessionError",
    "AlignmentSessionManager",
    "AlignmentSessionResult",
    "AlignmentSessionSnapshot",
    "AlignmentSessionTurn",
]
