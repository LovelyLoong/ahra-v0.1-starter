from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from typing import Any, Mapping

from .acceptance_contracts import ClaimGraph
from .approval_service import ApprovalRecord
from .boundary_contract import BoundaryContract, BoundaryContractEntry, BoundaryContractError
from .cross_alignment import CrossAlignmentReport, validate_cross_alignment
from .request_draft import (
    RequestDraft,
    RequestDraftError,
    RequestDraftRegistry,
    _claim_graph_to_mapping,
    _goal_ref_from_intent,
    _request_id,
    _request_name,
)
from .request_admission import RequestDraftAdmission, RequestDraftAdmissionResult
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
CROSS_ALIGNMENT_REPORT_OUTPUT = "CrossAlignmentReport"
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
class GateDecisionRecord:
    decision_id: str
    question: str
    recommendation: str
    alternatives: tuple[str, ...]
    consequences: tuple[str, ...]
    blocking: bool = True
    final_answer: str | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "GateDecisionRecord":
        decision_id = _optional_string(data.get("decisionId") or data.get("decision_id") or data.get("id"))
        question = _optional_string(data.get("question"))
        recommendation = _optional_string(data.get("recommendation"))
        if not decision_id or not question or not recommendation:
            raise AlignmentSessionError(
                "invalid_gate1_decision_record",
                "Gate 1 decision records require decisionId, question, and recommendation",
                ref="agentOutput.decisionRecords",
            )
        return cls(
            decision_id=decision_id,
            question=question,
            recommendation=recommendation,
            alternatives=_string_tuple(data.get("alternatives") or ()),
            consequences=_string_tuple(data.get("consequences") or ()),
            blocking=bool(data.get("blocking", True)),
            final_answer=_optional_string(data.get("finalAnswer") or data.get("final_answer")),
        )

    def to_mapping(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "decisionId": self.decision_id,
            "question": self.question,
            "recommendation": self.recommendation,
            "alternatives": list(self.alternatives),
            "consequences": list(self.consequences),
            "blocking": self.blocking,
        }
        if self.final_answer:
            data["finalAnswer"] = self.final_answer
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
    boundary_contract: BoundaryContract | None = None
    boundary_contract_digest: str | None = None
    frozen_claim_graph: ClaimGraph | None = None
    frozen_claim_graph_digest: str | None = None
    cross_alignment_report: Mapping[str, Any] | None = None
    cross_alignment_redraft_attempts: int = 0
    request_admission_report: Mapping[str, Any] | None = None
    request_admission_redraft_attempts: int = 0
    requirement_approved_by: str | None = None
    missing_dimensions: tuple[str, ...] = ()
    gate_decisions: tuple[GateDecisionRecord, ...] = ()

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
            boundary_contract=(
                BoundaryContract.from_mapping(_mapping(data["boundaryContract"], "boundaryContract"))
                if data.get("boundaryContract")
                else None
            ),
            boundary_contract_digest=str(data["boundaryContractDigest"]) if data.get("boundaryContractDigest") else None,
            frozen_claim_graph=(
                ClaimGraph.from_mapping(_mapping(data["frozenClaimGraph"], "frozenClaimGraph"))
                if "frozenClaimGraph" in data and data["frozenClaimGraph"] is not None
                else None
            ),
            frozen_claim_graph_digest=str(data["frozenClaimGraphDigest"]) if data.get("frozenClaimGraphDigest") else None,
            cross_alignment_report=(
                _mapping(data["crossAlignmentReport"], "crossAlignmentReport")
                if data.get("crossAlignmentReport")
                else None
            ),
            cross_alignment_redraft_attempts=int(data.get("crossAlignmentRedraftAttempts", 0)),
            request_admission_report=(
                _mapping(data["requestAdmissionReport"], "requestAdmissionReport")
                if data.get("requestAdmissionReport")
                else None
            ),
            request_admission_redraft_attempts=int(data.get("requestAdmissionRedraftAttempts", 0)),
            requirement_approved_by=str(data["requirementApprovedBy"]) if data.get("requirementApprovedBy") else None,
            missing_dimensions=tuple(str(item) for item in data.get("missingDimensions", ())),
            gate_decisions=tuple(
                GateDecisionRecord.from_mapping(_mapping(item, "gateDecision"))
                for item in data.get("gateDecisions", ())
            ),
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
        if self.boundary_contract:
            data["boundaryContract"] = self.boundary_contract.to_mapping()
        if self.boundary_contract_digest:
            data["boundaryContractDigest"] = self.boundary_contract_digest
        if self.frozen_claim_graph is not None:
            data["frozenClaimGraph"] = _claim_graph_to_mapping(self.frozen_claim_graph)
        if self.frozen_claim_graph_digest:
            data["frozenClaimGraphDigest"] = self.frozen_claim_graph_digest
        if self.cross_alignment_report:
            data["crossAlignmentReport"] = dict(self.cross_alignment_report)
        if self.cross_alignment_redraft_attempts:
            data["crossAlignmentRedraftAttempts"] = self.cross_alignment_redraft_attempts
        if self.request_admission_report:
            data["requestAdmissionReport"] = dict(self.request_admission_report)
        if self.request_admission_redraft_attempts:
            data["requestAdmissionRedraftAttempts"] = self.request_admission_redraft_attempts
        if self.requirement_approved_by:
            data["requirementApprovedBy"] = self.requirement_approved_by
        if self.gate_decisions:
            data["gateDecisions"] = [decision.to_mapping() for decision in self.gate_decisions]
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
        max_cross_alignment_redrafts: int = 1,
        agent_timeout_seconds: float = DEFAULT_AGENT_TIMEOUT_SECONDS,
    ) -> None:
        if registry is not None and profile_registry is not None:
            raise ValueError("pass either registry or profile_registry, not both")
        self.agent_driver = agent_driver
        self.registry = registry or RequestDraftRegistry(profiles=profile_registry or GoalOperationProfileRegistry())
        self.default_profile_ref = default_profile_ref
        self.max_dialogue_turns = max_dialogue_turns
        self.max_cross_alignment_redrafts = _non_negative_int(max_cross_alignment_redrafts, "max_cross_alignment_redrafts")
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
        missing_dimensions = _string_tuple(decision.get("missingDimensions") or decision.get("missing_dimensions"))
        gate_decisions = _merge_gate_decisions(
            current.gate_decisions,
            _gate_decisions_from_output(decision, missing_dimensions=missing_dimensions, turn_index=after_user.next_turn_index),
        )
        unresolved_decisions = _unanswered_blocking_decisions(gate_decisions)
        if converged and unresolved_decisions:
            raise AlignmentSessionError(
                "gate1_blocking_decisions_unanswered",
                "Gate 1 cannot freeze while blocking decision records remain unanswered",
                ref="agentOutput.decisionRecords",
                refs=tuple(decision.decision_id for decision in unresolved_decisions),
                data={
                    "unansweredDecisionIds": [decision.decision_id for decision in unresolved_decisions],
                },
            )
        if converged and not frozen_requirement:
            raise AlignmentSessionError(
                "missing_frozen_requirement",
                "converged alignment turn must include frozenRequirement",
                ref="agentOutput.frozenRequirement",
            )
        boundary_contract: BoundaryContract | None = None
        boundary_contract_digest: str | None = None
        if converged:
            boundary_contract = _boundary_contract_from_decision(decision, after_user, frozen_requirement or agent_message)
            boundary_contract_digest = boundary_contract.digest()
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
            boundary_contract=boundary_contract or after_agent.boundary_contract,
            boundary_contract_digest=boundary_contract_digest or after_agent.boundary_contract_digest,
            missing_dimensions=missing_dimensions,
            gate_decisions=gate_decisions,
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
        unresolved_decisions = _unanswered_blocking_decisions(current.gate_decisions)
        if unresolved_decisions:
            raise AlignmentSessionError(
                "gate1_blocking_decisions_unanswered",
                "requirement freeze requires final answers for all blocking Gate 1 decisions",
                ref="session.gateDecisions",
                refs=tuple(decision.decision_id for decision in unresolved_decisions),
                data={
                    "unansweredDecisionIds": [decision.decision_id for decision in unresolved_decisions],
                },
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
        frozen = _snapshot_with_boundary_contract(current)
        return replace(frozen, stage="frozen", requirement_approved_by=actor)

    async def draft_request(
        self,
        snapshot: AlignmentSessionSnapshot | Mapping[str, Any],
        *,
        approval_service: ApprovalServicePort | None = None,
    ) -> AlignmentSessionResult:
        current = self.resume_from_snapshot(snapshot)
        if current.stage == "frozen":
            current = _snapshot_with_boundary_contract(current)
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
        drafting_snapshot = current
        for redraft_attempt in range(self.max_cross_alignment_redrafts + 1):
            try:
                claim_id_prefix = f"CLM-{current.intent.intent_id.upper().replace('INTENT-', '')}"
                goal_ref = _goal_ref_from_intent(current.intent.intent_id)
                boundary_contract = drafting_snapshot.boundary_contract
                if boundary_contract is None:
                    raise AlignmentSessionError(
                        "missing_boundary_contract",
                        "request drafting requires a frozen boundary contract",
                        ref="session.boundaryContract",
                    )
                boundary_contract_mapping = boundary_contract.to_mapping()
                admission_contract = _draft_admission_contract(self.registry, drafting_snapshot, current.intent)
                acceptance_result = await self._run_agent(
                    drafting_snapshot,
                    expected_output=ACCEPTANCE_DRAFT_OUTPUT,
                    payload={
                        "phase": "acceptance-draft",
                        "boundaryContract": boundary_contract_mapping,
                        "boundaryContractDigest": drafting_snapshot.boundary_contract_digest,
                        "admissionContract": admission_contract,
                        "redraftAttempt": redraft_attempt,
                        "previousCrossAlignmentReport": drafting_snapshot.cross_alignment_report,
                        "previousRequestAdmissionReport": drafting_snapshot.request_admission_report,
                    },
                )
            except AlignmentSessionError as exc:
                if exc.code == "agent_driver_timeout":
                    exc.snapshot = self._snapshot_with_agent_error(drafting_snapshot, exc, stage="frozen")
                raise
            acceptance = _mapping(acceptance_result.output, ACCEPTANCE_DRAFT_OUTPUT)
            claim_graph = _claim_graph_from_output(acceptance)
            claim_graph_digest = _claim_graph_digest(claim_graph)
            frozen = replace(
                drafting_snapshot,
                frozen_claim_graph=claim_graph,
                frozen_claim_graph_digest=claim_graph_digest,
            )
            after_acceptance = frozen.append_turn(
                actor="agent:acceptance",
                message=_summary(acceptance, "acceptance draft produced"),
                expected_output=ACCEPTANCE_DRAFT_OUTPUT,
                trace_ref=acceptance_result.trace_ref,
            )
            frozen_claim_graph_mapping = _claim_graph_to_mapping(claim_graph)
            try:
                requirement_result = await self._run_agent(
                    after_acceptance,
                    expected_output=REQUIREMENT_DRAFT_OUTPUT,
                    payload={
                        "phase": "requirement-draft",
                        "intent": current.intent.to_mapping(),
                        "boundaryContract": boundary_contract_mapping,
                        "boundaryContractDigest": drafting_snapshot.boundary_contract_digest,
                        "frozenClaimGraph": frozen_claim_graph_mapping,
                        "frozenClaimGraphDigest": claim_graph_digest,
                        "admissionContract": admission_contract,
                        "readOnlyInputs": {
                            "boundaryContract": boundary_contract_mapping,
                            "boundaryContractDigest": drafting_snapshot.boundary_contract_digest,
                            "claimGraph": frozen_claim_graph_mapping,
                            "claimGraphDigest": claim_graph_digest,
                            "admissionContract": admission_contract,
                        },
                        "requirementTrace": {
                            "frozenRequirement": current.frozen_requirement,
                        },
                        "profileRef": current.profile_ref,
                        "runtimeRef": current.runtime_ref,
                        "redraftAttempt": redraft_attempt,
                        "previousCrossAlignmentReport": drafting_snapshot.cross_alignment_report,
                        "previousRequestAdmissionReport": drafting_snapshot.request_admission_report,
                        "coordinationRules": {
                            "claimIdPrefix": claim_id_prefix,
                            "claimIdFormat": f"{claim_id_prefix}-<SHORT-DESCRIPTOR>",
                            "instruction": f"When referencing acceptance claims in your PlanDraft nodes, use claim IDs already present in the frozen ClaimGraph. Do not author or rewrite the ClaimGraph.",
                        },
                        "goalRef": goal_ref,
                    },
                )
            except AlignmentSessionError as exc:
                if exc.code == "agent_driver_timeout":
                    exc.snapshot = self._snapshot_with_agent_error(after_acceptance, exc, stage="frozen")
                raise
            requirement = _mapping(requirement_result.output, REQUIREMENT_DRAFT_OUTPUT)
            _ensure_requirement_did_not_rewrite_claim_graph(requirement, claim_graph_digest)
            plan = _plan_from_output(requirement)
            cross_alignment_report = validate_cross_alignment(
                boundary_contract=boundary_contract,
                claim_graph=claim_graph,
                plan=plan,
            )
            after_requirement = after_acceptance.append_turn(
                actor="agent:requirement",
                message=_summary(requirement, "requirement draft produced"),
                expected_output=REQUIREMENT_DRAFT_OUTPUT,
                trace_ref=requirement_result.trace_ref,
            )
            if not cross_alignment_report.accepted:
                exhausted = redraft_attempt >= self.max_cross_alignment_redrafts
                rejected_snapshot = self._snapshot_with_cross_alignment_report(
                    after_requirement,
                    cross_alignment_report,
                    redraft_attempt=redraft_attempt,
                    exhausted=exhausted,
                )
                if exhausted:
                    raise self._cross_alignment_error(cross_alignment_report, rejected_snapshot)
                drafting_snapshot = rejected_snapshot
                continue
            request_draft = self._request_from_agent_outputs(
                after_requirement,
                requirement,
                claim_graph,
                claim_graph_digest,
                plan=plan,
            )
            admission = None
            if approval_service is not None:
                admission = RequestDraftAdmission(self.registry).evaluate(request_draft)
                if not admission.accepted:
                    exhausted = redraft_attempt >= self.max_cross_alignment_redrafts
                    rejected_snapshot = self._snapshot_with_request_admission_report(
                        after_requirement,
                        admission,
                        redraft_attempt=redraft_attempt,
                        exhausted=exhausted,
                    )
                    if exhausted:
                        raise self._request_admission_error(admission, rejected_snapshot, request_draft)
                    drafting_snapshot = rejected_snapshot
                    continue
            final_snapshot = replace(
                after_requirement,
                stage="request_drafted",
                cross_alignment_report=cross_alignment_report.to_mapping(),
                cross_alignment_redraft_attempts=redraft_attempt,
                request_admission_report=admission.to_dict() if admission is not None else after_requirement.request_admission_report,
                request_admission_redraft_attempts=redraft_attempt if admission is not None else after_requirement.request_admission_redraft_attempts,
            )
            approval_record = None
            if approval_service is not None:
                approval_record = approval_service.request_authorization(request_draft, actor=current.producer_actor)
            return AlignmentSessionResult(
                snapshot=final_snapshot,
                request_draft=request_draft,
                approval_record=approval_record,
            )
        raise AssertionError("unreachable cross-alignment redraft loop exit")

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

    def _snapshot_with_cross_alignment_report(
        self,
        snapshot: AlignmentSessionSnapshot,
        report: CrossAlignmentReport,
        *,
        redraft_attempt: int,
        exhausted: bool,
    ) -> AlignmentSessionSnapshot:
        report_mapping = report.to_mapping()
        message = (
            "cross-alignment gate failed; redraft bound exhausted"
            if exhausted
            else "cross-alignment gate failed; requesting bounded redraft"
        )
        return replace(
            snapshot.append_turn(
                actor="agent:cross-alignment",
                message=message,
                expected_output=CROSS_ALIGNMENT_REPORT_OUTPUT,
                error=report_mapping,
            ),
            stage="failed" if exhausted else "frozen",
            cross_alignment_report=report_mapping,
            cross_alignment_redraft_attempts=redraft_attempt,
        )

    def _snapshot_with_request_admission_report(
        self,
        snapshot: AlignmentSessionSnapshot,
        report: RequestDraftAdmissionResult,
        *,
        redraft_attempt: int,
        exhausted: bool,
    ) -> AlignmentSessionSnapshot:
        report_mapping = report.to_dict()
        message = (
            "RequestDraft admission failed; redraft bound exhausted"
            if exhausted
            else "RequestDraft admission failed; requesting bounded redraft"
        )
        return replace(
            snapshot.append_turn(
                actor="agent:request-admission",
                message=message,
                expected_output="RequestDraftAdmission",
                error=report_mapping,
            ),
            stage="failed" if exhausted else "frozen",
            request_admission_report=report_mapping,
            request_admission_redraft_attempts=redraft_attempt,
        )

    def _cross_alignment_error(
        self,
        report: CrossAlignmentReport,
        snapshot: AlignmentSessionSnapshot,
    ) -> AlignmentSessionError:
        report_mapping = report.to_mapping()
        mismatch_codes = tuple(mismatch.code for mismatch in report.mismatches)
        return AlignmentSessionError(
            "cross_alignment_redraft_exhausted",
            "cross-alignment gate rejected all bounded redraft attempts before Human Gate 2",
            ref="crossAlignmentReport",
            refs=mismatch_codes or ("crossAlignmentReport",),
            data={
                "crossAlignmentReport": report_mapping,
                "maxCrossAlignmentRedrafts": self.max_cross_alignment_redrafts,
            },
            snapshot=snapshot,
        )

    def _request_admission_error(
        self,
        report: RequestDraftAdmissionResult,
        snapshot: AlignmentSessionSnapshot,
        request_draft: RequestDraft,
    ) -> AlignmentSessionError:
        report_mapping = report.to_dict()
        rejection_codes = tuple(rejection.code for rejection in report.rejections)
        return AlignmentSessionError(
            "request_draft_admission_redraft_exhausted",
            "RequestDraft admission rejected all bounded redraft attempts before Human Gate 2",
            ref="requestAdmissionReport",
            refs=rejection_codes or ("requestAdmissionReport",),
            data={
                "requestAdmissionReport": report_mapping,
                "requestDraft": request_draft.to_mapping(),
                "maxRequestAdmissionRedrafts": self.max_cross_alignment_redrafts,
            },
            snapshot=snapshot,
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
        claim_graph: ClaimGraph,
        claim_graph_digest: str,
        *,
        plan: PlanDraft | None = None,
    ) -> RequestDraft:
        profile = self._resolve_profile(snapshot.profile_ref, runtime_ref=snapshot.runtime_ref, runtime_digest=snapshot.runtime_digest)
        aligned_intent = replace(snapshot.intent, abstract_goal=_summary(requirement, snapshot.frozen_requirement or snapshot.intent.abstract_goal))
        goal_ref = _goal_ref_from_intent(aligned_intent.intent_id)
        _ensure_requirement_did_not_rewrite_claim_graph(requirement, claim_graph_digest)
        required_claim_refs = tuple(claim.claim_id for claim in claim_graph.claims if claim.required)
        plan = plan or _plan_from_output(requirement)
        _ensure_plan_claim_refs_resolve_claim_graph(plan, claim_graph)
        allowed_capabilities = tuple(sorted({need.action for need in aligned_intent.capability_needs} | {"filesystem.write"}))
        capability_policies = {need.action: need.policy_refs for need in aligned_intent.capability_needs if need.policy_refs}
        goal_digest = canonical_fingerprint({"goalRef": goal_ref, "abstractGoal": aligned_intent.abstract_goal})
        actual_claim_graph_digest = _claim_graph_digest(claim_graph)
        if actual_claim_graph_digest != claim_graph_digest:
            raise AlignmentSessionError(
                "frozen_claim_graph_digest_mismatch",
                "RequestDraft ClaimGraph must match the frozen ClaimGraph digest",
                ref="RequestDraft.spec.claimGraph",
                refs=(claim_graph_digest, actual_claim_graph_digest),
                data={
                    "expectedClaimGraphDigest": claim_graph_digest,
                    "actualClaimGraphDigest": actual_claim_graph_digest,
                },
            )
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


def _boundary_contract_from_decision(
    decision: Mapping[str, Any],
    snapshot: AlignmentSessionSnapshot,
    frozen_requirement: str,
) -> BoundaryContract:
    data = decision.get("boundaryContract") or decision.get("boundary_contract")
    try:
        if data is None:
            return _default_boundary_contract(snapshot, frozen_requirement)
        return BoundaryContract.freeze(_mapping(data, "agentOutput.boundaryContract"))
    except BoundaryContractError as exc:
        raise AlignmentSessionError(
            exc.code,
            exc.message,
            ref=f"agentOutput.boundaryContract.{exc.ref}",
            refs=exc.refs,
        ) from exc


def _snapshot_with_boundary_contract(snapshot: AlignmentSessionSnapshot) -> AlignmentSessionSnapshot:
    try:
        boundary_contract = snapshot.boundary_contract or _default_boundary_contract(
            snapshot,
            snapshot.frozen_requirement or snapshot.intent.abstract_goal,
        )
        boundary_contract = boundary_contract.validate_for_freeze()
        digest = boundary_contract.digest()
    except BoundaryContractError as exc:
        raise AlignmentSessionError(
            exc.code,
            exc.message,
            ref=f"session.boundaryContract.{exc.ref}",
            refs=exc.refs,
        ) from exc
    if snapshot.boundary_contract_digest and snapshot.boundary_contract_digest != digest:
        raise AlignmentSessionError(
            "boundary_contract_digest_mismatch",
            "stored boundary contract digest does not match the typed contract",
            ref="session.boundaryContractDigest",
            refs=(snapshot.boundary_contract_digest, digest),
        )
    return replace(snapshot, boundary_contract=boundary_contract, boundary_contract_digest=digest)


def _default_boundary_contract(snapshot: AlignmentSessionSnapshot, frozen_requirement: str) -> BoundaryContract:
    if snapshot.producer_actor == "agent:producer":
        entries = [
            BoundaryContractEntry(
                entry_id="CRIT-" + _boundary_contract_entry_tail(snapshot.intent.intent_id, "OBJECTIVE"),
                kind="must",
                statement=frozen_requirement,
                source_refs=("compat.phase1_fixture", "frozenRequirement"),
            ),
            BoundaryContractEntry(
                entry_id="CRIT-" + _boundary_contract_entry_tail(snapshot.intent.intent_id, "COMPLETE"),
                kind="completion_signal",
                statement="The request reaches completion only from governed evidence.",
                source_refs=("compat.phase1_fixture",),
            ),
        ]
        return BoundaryContract(
            name=_boundary_contract_name(snapshot.intent.intent_id),
            version=1,
            entries=tuple(entries),
        ).validate_for_freeze()
    entries = [
        BoundaryContractEntry(
            entry_id="CRIT-summary-artifact",
            kind="completion_signal",
            statement=frozen_requirement or "The governed deterministic summary artifact exists.",
            source_refs=("compat.workflow_a_cli_fixture", "frozenRequirement"),
        ),
    ]
    return BoundaryContract(
        name=_boundary_contract_name(snapshot.intent.intent_id),
        version=1,
        entries=tuple(entries),
    ).validate_for_freeze()


def _boundary_contract_name(intent_id: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in intent_id)
    cleaned = cleaned.strip("-") or "alignment"
    if cleaned.startswith("intent-"):
        cleaned = cleaned.removeprefix("intent-")
    return ("boundary-" + cleaned)[:63].rstrip("-")


def _boundary_contract_entry_tail(intent_id: str, fallback: str) -> str:
    cleaned = "".join(char if char.isalnum() else "-" for char in intent_id.upper())
    cleaned = cleaned.removeprefix("INTENT-").strip("-")
    if not cleaned:
        return fallback
    return f"{cleaned}-{fallback}"


def _boundary_contract_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": True,
        "required": ["apiVersion", "kind", "metadata", "spec"],
        "properties": {
            "apiVersion": {"type": "string", "const": "ahra.dev/v1alpha1"},
            "kind": {"type": "string", "const": "BoundaryContract"},
            "metadata": {
                "type": "object",
                "required": ["name", "version"],
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "version": {"type": "integer", "minimum": 1},
                },
            },
            "spec": {
                "type": "object",
                "required": ["entries"],
                "properties": {
                    "entries": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "required": ["id", "kind", "statement"],
                            "properties": {
                                "id": {"type": "string", "minLength": 1},
                                "kind": {
                                    "type": "string",
                                    "enum": ["must", "must_not", "completion_signal", "free_zone", "open_question"],
                                },
                                "statement": {"type": "string", "minLength": 1},
                                "sourceRefs": {"type": "array", "items": {"type": "string"}},
                            },
                        },
                    },
                },
            },
        },
    }


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
                "boundaryContract": _boundary_contract_output_schema(),
                "missingDimensions": {"type": "array", "items": {"type": "string"}},
                "decisionRecords": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": [
                            "decisionId",
                            "question",
                            "recommendation",
                            "alternatives",
                            "consequences",
                            "blocking",
                        ],
                        "properties": {
                            "decisionId": {"type": "string", "minLength": 1},
                            "question": {"type": "string", "minLength": 1},
                            "recommendation": {"type": "string", "minLength": 1},
                            "alternatives": {"type": "array", "items": {"type": "string"}},
                            "consequences": {"type": "array", "items": {"type": "string"}},
                            "blocking": {"type": "boolean"},
                            "finalAnswer": {"type": "string"},
                        },
                    },
                },
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
                                                    "maxModelCalls": {"type": "integer", "minimum": 1},
                                                    "maxToolCalls": {"type": "integer", "minimum": 1},
                                                    "maxSpawnedNodes": {"type": "integer", "minimum": 0},
                                                    "maxWallSeconds": {"type": "integer", "minimum": 1},
                                                    "maxCostUsd": {"type": "number", "minimum": 0},
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


def _draft_admission_contract(
    registry: RequestDraftRegistry,
    snapshot: AlignmentSessionSnapshot,
    intent: IntentDraft,
) -> dict[str, Any]:
    allowed_capabilities = sorted({need.action for need in intent.capability_needs} | {"filesystem.write"})
    return {
        "registeredNodeTypes": dict(sorted(registry.node_type_digests.items())),
        "registeredGateRefs": dict(sorted(registry.gate_ref_digests.items())),
        "registeredRuntimeRefs": {snapshot.runtime_ref: snapshot.runtime_digest},
        "allowedCapabilities": allowed_capabilities,
        "budgetRules": [
            "budgetRequest.maxModelCalls must be a positive integer greater than or equal to 1.",
            "budgetRequest.maxToolCalls must be a positive integer greater than or equal to 1.",
            "budgetRequest.maxSpawnedNodes must be a non-negative integer.",
            "budgetRequest.maxWallSeconds and timeoutSeconds must be positive when present.",
            "timeoutSeconds must not exceed budgetRequest.maxWallSeconds when both are present.",
        ],
        "claimGraphRules": [
            "Every Claim criterionRefs entry must reference a frozen boundary-contract entry of kind must, must_not, or completion_signal.",
            "Claims must not reference free_zone boundary entries.",
            "Claim gateRefs must be empty or use only keys from registeredGateRefs.",
            "Do not invent HumanGate-1, HumanGate-2, planning gates, review gates, or any other gate name.",
            "Human approval is represented by approvalRequired: true; it is not represented by a gateRef.",
            "Every required Claim must either set approvalRequired: true or use at least one registered gateRef.",
        ],
        "planDraftRules": [
            "Every PlanDraft nodeType must be one of the registeredNodeTypes keys.",
            "Use bounded_task for normal planning or documentation work; use goal_verification only for terminal goal verification.",
            "Every PlanDraft node gateRefs entry must use only keys from registeredGateRefs.",
            "Every PlanDraft node must include at least one registered gateRef.",
            "Do not invent HumanGate-1, HumanGate-2, planning, analysis, or human_gate node types.",
            "Every budgetRequest.maxModelCalls and budgetRequest.maxToolCalls must be positive integers greater than or equal to 1.",
            "Every budgetRequest.maxSpawnedNodes must be a non-negative integer.",
            "Only request capabilities listed in allowedCapabilities.",
        ],
    }


def _claim_graph_from_output(output: Mapping[str, Any]) -> ClaimGraph:
    present, claim_graph_data, ref = _optional_claim_graph_payload(output, "agentOutput")
    if present:
        return ClaimGraph.from_mapping(_mapping(claim_graph_data, ref))
    if output.get("kind") == "ClaimGraph":
        return ClaimGraph.from_mapping(output)
    raise AlignmentSessionError(
        "missing_claim_graph",
        "Acceptance Agent output must include an explicit ClaimGraph",
        ref="agentOutput.claimGraph",
    )


def _optional_claim_graph_payload(output: Mapping[str, Any], ref_prefix: str) -> tuple[bool, Any, str]:
    if "claimGraph" in output:
        return True, output["claimGraph"], f"{ref_prefix}.claimGraph"
    if "claim_graph" in output:
        return True, output["claim_graph"], f"{ref_prefix}.claim_graph"
    return False, None, f"{ref_prefix}.claimGraph"


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


def _claim_graph_digest(claim_graph: ClaimGraph) -> str:
    return canonical_fingerprint(_claim_graph_to_mapping(claim_graph))


def _ensure_claim_criterion_refs_resolve_boundary(
    claim_graph: ClaimGraph,
    boundary_contract: BoundaryContract,
) -> None:
    boundary_entry_ids = boundary_contract.entry_ids
    unresolved_by_claim: dict[str, list[str]] = {}
    for claim in claim_graph.claims:
        unresolved = sorted({ref for ref in claim.criterion_refs if ref not in boundary_entry_ids})
        if unresolved:
            unresolved_by_claim[claim.claim_id] = unresolved
    if not unresolved_by_claim:
        return
    unresolved_refs = tuple(sorted({ref for refs in unresolved_by_claim.values() for ref in refs}))
    raise AlignmentSessionError(
        "unresolved_boundary_criterion_refs",
        "ClaimGraph criterionRefs must resolve to boundary contract entry IDs",
        ref="claimGraph.spec.claims[].criterionRefs",
        refs=unresolved_refs,
        data={
            "unresolvedCriterionRefs": list(unresolved_refs),
            "claimCriterionRefs": unresolved_by_claim,
        },
    )


def _ensure_requirement_did_not_rewrite_claim_graph(
    requirement: Mapping[str, Any],
    frozen_claim_graph_digest: str,
) -> None:
    for key in ("claimGraph", "claim_graph"):
        if key not in requirement:
            continue
        candidate = requirement[key]
        candidate_digest = canonical_fingerprint(candidate)
        if candidate_digest == frozen_claim_graph_digest:
            continue
        raise AlignmentSessionError(
            "frozen_claim_graph_digest_mismatch",
            "Requirement Agent ClaimGraph output diverges from the frozen ClaimGraph",
            ref=f"RequirementDraft.{key}",
            refs=(frozen_claim_graph_digest, candidate_digest),
            data={
                "expectedClaimGraphDigest": frozen_claim_graph_digest,
                "actualClaimGraphDigest": candidate_digest,
            },
        )


def _ensure_plan_claim_refs_resolve_claim_graph(plan: PlanDraft, claim_graph: ClaimGraph) -> None:
    claim_ids = {claim.claim_id for claim in claim_graph.claims}
    unresolved_by_node: dict[str, list[str]] = {}
    for node in plan.nodes:
        unresolved = sorted({ref for ref in node.claim_refs if ref not in claim_ids})
        if unresolved:
            unresolved_by_node[node.node_id] = unresolved
    if not unresolved_by_node:
        return
    unresolved_refs = tuple(sorted({ref for refs in unresolved_by_node.values() for ref in refs}))
    raise AlignmentSessionError(
        "unresolved_plan_claim_refs",
        "PlanDraft node claimRefs must resolve to Claim IDs in the frozen ClaimGraph",
        ref="planDraft.spec.nodes[].claimRefs",
        refs=unresolved_refs,
        data={
            "unresolvedClaimRefs": list(unresolved_refs),
            "nodeClaimRefs": unresolved_by_node,
        },
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


def _non_negative_int(value: int, ref: str) -> int:
    count = int(value)
    if count < 0:
        raise ValueError(f"{ref} must be greater than or equal to zero")
    return count


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


def _gate_decisions_from_output(
    decision: Mapping[str, Any],
    *,
    missing_dimensions: tuple[str, ...],
    turn_index: int,
) -> tuple[GateDecisionRecord, ...]:
    raw = decision.get("decisionRecords") or decision.get("decision_records") or decision.get("decisions")
    if raw is not None:
        if not isinstance(raw, (list, tuple)):
            raise AlignmentSessionError(
                "invalid_gate1_decision_records",
                "decisionRecords must be a list of structured Gate 1 decision records",
                ref="agentOutput.decisionRecords",
            )
        return tuple(GateDecisionRecord.from_mapping(_mapping(item, "decisionRecord")) for item in raw)
    return tuple(
        GateDecisionRecord(
            decision_id=f"G1-{turn_index:02d}-{index:02d}",
            question=f"Resolve Gate 1 choice: {dimension}.",
            recommendation=f"Ask the human for a final answer for {dimension} before freezing the requirement boundary.",
            alternatives=(
                "answer before Gate 1",
                "remove this dimension from scope",
            ),
            consequences=(
                "Gate 1 remains blocked until the final answer is recorded.",
            ),
            blocking=True,
        )
        for index, dimension in enumerate(missing_dimensions, start=1)
    )


def _merge_gate_decisions(
    previous: tuple[GateDecisionRecord, ...],
    current: tuple[GateDecisionRecord, ...],
) -> tuple[GateDecisionRecord, ...]:
    ordered: dict[str, GateDecisionRecord] = {decision.decision_id: decision for decision in previous}
    for decision in current:
        ordered[decision.decision_id] = decision
    return tuple(ordered.values())


def _unanswered_blocking_decisions(
    decisions: tuple[GateDecisionRecord, ...],
) -> tuple[GateDecisionRecord, ...]:
    return tuple(decision for decision in decisions if decision.blocking and not decision.final_answer)


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
    "CROSS_ALIGNMENT_REPORT_OUTPUT",
    "DEFAULT_AGENT_TIMEOUT_SECONDS",
    "REQUIREMENT_DRAFT_OUTPUT",
    "AlignmentSessionError",
    "AlignmentSessionManager",
    "AlignmentSessionResult",
    "AlignmentSessionSnapshot",
    "AlignmentSessionTurn",
    "GateDecisionRecord",
]
