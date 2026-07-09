from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

import yaml

from .acceptance_contracts import ClaimGraph
from .alignment_session import (
    ACCEPTANCE_DRAFT_OUTPUT,
    ALIGNMENT_DECISION_OUTPUT,
    REQUIREMENT_DRAFT_OUTPUT,
    AlignmentSessionError,
    AlignmentSessionManager,
    AlignmentSessionSnapshot,
)
from .approval_service import ApprovalService
from .intent_draft import IntentDraft
from .plan_ir import PlanDraft
from .ports import AgentDriver, AgentRunRequest, AgentRunResult
from .request_draft import RequestDraft
from .request_admission import RequestDraftAdmission
from .validation import load_document
from .workflow_a_briefing import (
    DEFAULT_GATE2_BRIEFING_NAME,
    request_digest,
    verify_gate2_briefing,
    write_gate2_briefing,
)


class RequestDraftAdmissionError(ValueError):
    def __init__(
        self,
        *,
        request_id: str,
        admission: Mapping[str, Any],
        session_path: Path,
        request_draft_path: Path,
    ) -> None:
        self.request_id = request_id
        self.admission = dict(admission)
        self.session_path = session_path
        self.request_draft_path = request_draft_path
        rejections = self.admission.get("rejections", [])
        codes = [
            str(item.get("code"))
            for item in rejections
            if isinstance(item, Mapping) and item.get("code")
        ]
        self.codes = tuple(codes)
        message = f"RequestDraft admission rejected {request_id}"
        if codes:
            message = f"{message}: {', '.join(codes)}"
        super().__init__(message)

    def to_error_dict(self) -> dict[str, Any]:
        return {
            "code": "request_draft_admission_rejected",
            "error": str(self),
            "refs": list(self.codes),
            "sessionPath": str(self.session_path),
            "requestDraftPath": str(self.request_draft_path),
            "admission": dict(self.admission),
        }


class WorkflowAFixtureDriver:
    """Deterministic CLI fixture driver; explicit smoke-test use only."""

    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        if request.expected_output == ALIGNMENT_DECISION_OUTPUT:
            return AgentRunResult(
                output={
                    "message": "Requirement boundary is ready for human approval.",
                    "converged": True,
                    "frozenRequirement": "Write one governed deterministic summary artifact in the local workspace.",
                    "missingDimensions": [],
                }
            )
        if request.expected_output == REQUIREMENT_DRAFT_OUTPUT:
            return AgentRunResult(output=_fixture_requirement_output())
        if request.expected_output == ACCEPTANCE_DRAFT_OUTPUT:
            return AgentRunResult(output=_fixture_acceptance_output())
        raise ValueError(f"unsupported Workflow A fixture output: {request.expected_output}")


class UnavailableWorkflowADriver:
    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        raise RuntimeError(f"Workflow A command requires an AgentDriver for {request.expected_output}")


def start_session(
    *,
    intent_path: Path,
    session_path: Path,
    profile_ref: str | None = None,
    runtime_ref: str | None = None,
    runtime_digest: str | None = None,
    workspace_ref: str = "workspace",
    artifact_dir: str = ".ahra/artifacts",
    store_path: str = ".ahra/goal-control.sqlite3",
    producer_actor: str = "agent:alignment-session",
) -> dict[str, Any]:
    intent = IntentDraft.from_mapping(load_document(intent_path))
    manager = AlignmentSessionManager(UnavailableWorkflowADriver())
    snapshot = manager.start(
        intent,
        profile_ref=profile_ref,
        runtime_ref=runtime_ref,
        runtime_digest=runtime_digest,
        workspace_ref=_normalize_cli_path(workspace_ref),
        artifact_dir=_normalize_cli_path(artifact_dir),
        store_path=_normalize_cli_path(store_path),
        producer_actor=producer_actor,
    )
    _write_json(session_path, snapshot.to_mapping())
    return {"sessionPath": str(session_path), "snapshot": snapshot.to_mapping()}


async def advance_session(
    *,
    session_path: Path,
    message: str,
    actor: str,
    driver: AgentDriver,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    manager = _manager(driver, timeout_seconds=timeout_seconds)
    try:
        snapshot = await manager.advance(_load_snapshot(session_path), message, actor=actor)
    except AlignmentSessionError as exc:
        _write_error_snapshot(session_path, exc)
        raise
    _write_json(session_path, snapshot.to_mapping())
    return {"sessionPath": str(session_path), "snapshot": snapshot.to_mapping()}


def approve_requirement(*, session_path: Path, actor: str) -> dict[str, Any]:
    manager = AlignmentSessionManager(UnavailableWorkflowADriver())
    snapshot = manager.approve_requirement(_load_snapshot(session_path), actor=actor)
    _write_json(session_path, snapshot.to_mapping())
    return {"sessionPath": str(session_path), "snapshot": snapshot.to_mapping()}


def read_snapshot(*, session_path: Path) -> dict[str, Any]:
    return {"sessionPath": str(session_path), "snapshot": _load_snapshot(session_path).to_mapping()}


def _manager(driver: AgentDriver, *, timeout_seconds: float | None) -> AlignmentSessionManager:
    if timeout_seconds is None:
        return AlignmentSessionManager(driver)
    return AlignmentSessionManager(driver, agent_timeout_seconds=timeout_seconds)


def _write_error_snapshot(session_path: Path, error: AlignmentSessionError) -> None:
    snapshot = error.snapshot
    if isinstance(snapshot, AlignmentSessionSnapshot):
        _write_json(session_path, snapshot.to_mapping())


async def draft_request(
    *,
    session_path: Path,
    request_draft_path: Path,
    approval_path: Path | None,
    briefing_path: Path | None = None,
    driver: AgentDriver,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    manager = _manager(driver, timeout_seconds=timeout_seconds)
    approval_service = ApprovalService() if approval_path is not None else None
    try:
        result = await manager.draft_request(_load_snapshot(session_path), approval_service=approval_service)
    except AlignmentSessionError as exc:
        request_draft_mapping = exc.data.get("requestDraft")
        if isinstance(request_draft_mapping, Mapping):
            _write_json(request_draft_path, request_draft_mapping)
        _write_error_snapshot(session_path, exc)
        raise
    admission = RequestDraftAdmission().evaluate(result.request_draft).to_dict()
    if not admission["accepted"]:
        rejected_snapshot = replace(
            result.snapshot.append_turn(
                actor="agent:request-admission",
                message="RequestDraft admission rejected before Gate 2 authorization.",
                expected_output="RequestDraftAdmission",
                error=admission,
            ),
            stage="frozen",
        )
        _write_json(session_path, rejected_snapshot.to_mapping())
        _write_json(request_draft_path, result.request_draft.to_mapping())
        raise RequestDraftAdmissionError(
            request_id=result.request_draft.request_id,
            admission=admission,
            session_path=session_path,
            request_draft_path=request_draft_path,
        )

    _write_json(session_path, result.snapshot.to_mapping())
    _write_json(request_draft_path, result.request_draft.to_mapping())
    payload: dict[str, Any] = {
        "sessionPath": str(session_path),
        "requestDraftPath": str(request_draft_path),
        "requestDraft": result.request_draft.to_mapping(),
        "admission": admission,
    }
    if approval_path is not None:
        approval_record = result.approval_record
        if approval_record is None:
            raise RuntimeError("Gate 2 approval was not created after RequestDraftAdmission")
        approval_mapping = {
            **approval_record.to_dict(),
            "requestDigest": request_digest(result.request_draft),
        }
        _write_json(approval_path, approval_mapping)
        selected_briefing_path = briefing_path or approval_path.with_name(DEFAULT_GATE2_BRIEFING_NAME)
        briefing = write_gate2_briefing(
            selected_briefing_path,
            result.request_draft,
            approval_mapping,
            request_draft_path=request_draft_path,
            approval_path=approval_path,
        )
        payload["approvalPath"] = str(approval_path)
        payload["approval"] = approval_mapping
        payload["briefingPath"] = str(selected_briefing_path)
        payload["briefing"] = briefing
    return payload


def admit_request(*, request_draft_path: Path) -> dict[str, Any]:
    draft = load_request_draft(request_draft_path)
    return RequestDraftAdmission().evaluate(draft).to_dict()


def authorize_request(
    *,
    request_draft_path: Path,
    approval_path: Path,
    briefing_path: Path | None,
    output_path: Path,
    actor: str,
    reason: str = "",
) -> dict[str, Any]:
    draft = load_request_draft(request_draft_path)
    approval = _load_json(approval_path)
    if str(approval.get("requestId") or "") != draft.request_id:
        raise ValueError("approval does not belong to RequestDraft")
    if str(approval.get("approvalId") or "") != "APR-" + draft.request_id.removeprefix("REQ-"):
        raise ValueError("approval id does not belong to RequestDraft")
    if str(approval.get("status") or "") != "waiting_auth":
        raise ValueError("approval is not waiting_auth")
    selected_briefing_path = briefing_path or approval_path.with_name(DEFAULT_GATE2_BRIEFING_NAME)
    verify_gate2_briefing(
        selected_briefing_path.read_text(encoding="utf-8"),
        draft,
        approval,
    )
    service = ApprovalService()
    record = service.request_authorization(draft, actor=str(approval.get("requestedBy") or "agent:workflow-a-cli"))
    approved = service.approve(record.approval_id, actor=actor, reason=reason)
    frozen = service.freeze(draft, approval_id=record.approval_id)
    approved_mapping = {
        **approved.to_dict(),
        "requestDigest": request_digest(draft),
    }
    _write_json(approval_path, approved_mapping)
    _write_yaml(output_path, frozen.to_dict())
    return {
        "approval": approved_mapping,
        "briefingPath": str(selected_briefing_path),
        "goalExecutionRequestPath": str(output_path),
        "goalExecutionRequest": frozen.to_dict(),
    }


def workflow_status(
    *,
    session_path: Path,
    request_draft_path: Path | None = None,
    approval_path: Path | None = None,
    briefing_path: Path | None = None,
    output_path: Path | None = None,
    workflow_b_artifact_dir: Path | None = None,
) -> dict[str, Any]:
    snapshot = _load_snapshot(session_path).to_mapping()
    stage = str(snapshot.get("stage") or "unknown")
    approval = _load_json(approval_path) if approval_path and approval_path.exists() else None
    selected_briefing_path = briefing_path
    if selected_briefing_path is None and approval_path is not None:
        selected_briefing_path = approval_path.with_name(DEFAULT_GATE2_BRIEFING_NAME)
    workflow_b_started = _workflow_b_started(output_path, workflow_b_artifact_dir)
    paths = {
        "session": _path_status(session_path),
        "requestDraft": _path_status(request_draft_path),
        "approval": _path_status(approval_path),
        "briefing": _path_status(selected_briefing_path),
        "requestOutput": _path_status(output_path),
        "workflowBArtifactDir": _path_status(workflow_b_artifact_dir),
    }
    next_action = _next_safe_action(
        stage=stage,
        approval=approval,
        paths=paths,
        workflow_b_started=workflow_b_started,
    )
    status_text = (
        f"Workflow A stage: {stage}. "
        f"Next safe action: {next_action}. "
        f"Workflow B started: {str(workflow_b_started).lower()}."
    )
    return {
        "stage": stage,
        "paths": paths,
        "nextSafeAction": next_action,
        "workflowBStarted": workflow_b_started,
        "statusText": status_text,
    }


def load_request_draft(path: Path) -> RequestDraft:
    data = _load_json(path)
    spec = _mapping(data.get("spec"), "spec")
    metadata = _mapping(data.get("metadata"), "metadata")
    store = _mapping(spec.get("store"), "spec.store")
    planner = _mapping(spec.get("planner"), "spec.planner")
    executor = _mapping(spec.get("executor"), "spec.executor")
    gate_runner = _mapping(spec.get("gateRunner"), "spec.gateRunner")
    runtime = _mapping(spec.get("runtime"), "spec.runtime")
    goal = _mapping(spec.get("goal"), "spec.goal")
    registry = _mapping(spec.get("registry"), "spec.registry")
    execution = _mapping(spec.get("execution"), "spec.execution")
    policies = _mapping(spec.get("capabilityPolicies", {}), "spec.capabilityPolicies")
    return RequestDraft(
        request_id=str(metadata["requestId"]),
        intent_id=str(metadata["intentId"]),
        producer_actor=str(metadata["producerActor"]),
        name=str(metadata["name"]),
        idempotency_key=str(metadata["idempotencyKey"]),
        profile_ref=str(spec["profileRef"]),
        workspace_ref=str(spec["workspaceRef"]),
        artifact_dir=str(spec["artifactDir"]),
        store_kind=str(store["kind"]),
        store_path=str(store["path"]),
        planner_adapter_ref=str(planner["adapterRef"]),
        executor_adapter_ref=str(executor["adapterRef"]),
        gate_runner_adapter_ref=str(gate_runner["adapterRef"]),
        runtime_ref=str(runtime["runtimeRef"]),
        runtime_digest=str(runtime["digest"]),
        goal_ref=str(goal["goalRef"]),
        goal_digest=str(goal["goalDigest"]),
        claim_graph=ClaimGraph.from_mapping(_mapping(spec.get("claimGraph"), "spec.claimGraph")),
        claim_graph_digest=str(goal["claimGraphDigest"]),
        required_claim_refs=tuple(str(item) for item in goal.get("requiredClaimRefs", ())),
        registered_node_types={str(key): str(value) for key, value in _mapping(registry.get("nodeTypes"), "spec.registry.nodeTypes").items()},
        registered_gate_refs={str(key): str(value) for key, value in _mapping(registry.get("gateRefs"), "spec.registry.gateRefs").items()},
        registered_runtime_refs={str(key): str(value) for key, value in _mapping(registry.get("runtimeRefs"), "spec.registry.runtimeRefs").items()},
        allowed_capabilities=tuple(str(item) for item in registry.get("allowedCapabilities", ())),
        capability_policies={str(key): tuple(str(item) for item in value) for key, value in policies.items()},
        plan_draft=PlanDraft.from_mapping(_mapping(spec.get("planDraft"), "spec.planDraft")),
        max_repair_cycles=int(execution.get("maxRepairCycles", 0)),
        max_concurrency=int(execution.get("maxConcurrency", 1)),
        branch=str(execution.get("branch", "main")),
    )


def _load_snapshot(path: Path) -> AlignmentSessionSnapshot:
    return AlignmentSessionSnapshot.from_mapping(_load_json(path))


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return dict(_mapping(data, str(path)))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_yaml(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(dict(payload), sort_keys=False), encoding="utf-8")


def _path_status(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"path": None, "known": False, "exists": False}
    return {"path": str(path), "known": True, "exists": path.exists()}


def _workflow_b_started(output_path: Path | None, artifact_dir: Path | None) -> bool:
    if artifact_dir is not None and (
        (artifact_dir / "goal-start-report.json").exists()
        or (artifact_dir / "plan-ir.json").exists()
        or (artifact_dir / "workflow-run-result.json").exists()
    ):
        return True
    return bool(output_path is not None and output_path.exists() and artifact_dir is not None)


def _next_safe_action(
    *,
    stage: str,
    approval: Mapping[str, Any] | None,
    paths: Mapping[str, Mapping[str, Any]],
    workflow_b_started: bool,
) -> str:
    if stage in {"dialogue", "awaiting_user"}:
        return "advance Workflow A alignment with workflow-a advance"
    if stage == "awaiting_requirement_approval":
        return "review Gate 1 decisions, then run workflow-a approve-requirement"
    if stage == "frozen":
        return "run workflow-a draft to produce RequestDraft, ApprovalRecord, and Gate 2 briefing"
    if stage == "failed":
        return "inspect the session failure report before redrafting or restarting"
    if stage == "request_drafted":
        if approval and approval.get("status") == "waiting_auth":
            if not paths["briefing"]["exists"]:
                return "regenerate the Gate 2 briefing before authorization"
            return "review the Gate 2 briefing, then run workflow-a authorize"
        if paths["requestOutput"]["exists"] and not workflow_b_started:
            return "run goal validate/plan/start on the frozen GoalExecutionRequest"
        if workflow_b_started:
            return "monitor Workflow B artifacts and completion evidence"
    return "inspect workflow-a status and current artifacts"


def _normalize_cli_path(value: str) -> str:
    path = Path(value)
    if path.is_absolute():
        return str(path)
    return str(path.resolve())


def _mapping(value: Any, ref: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{ref} must be a mapping")
    return value


def _fixture_requirement_output() -> dict[str, Any]:
    return {
        "summary": "Write one governed deterministic summary artifact in the local workspace.",
        "planDraft": {
            "apiVersion": "ahra.dev/v1alpha1",
            "kind": "PlanDraft",
            "metadata": {
                "goalId": "GOAL-PHASE1-EXAMPLE-ALIGNED",
                "proposedBy": "planner/workflow-a-cli-fixture",
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
                                "consumerNodeRefs": ["NODE-goal-verification"],
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
                    },
                    {
                        "id": "NODE-goal-verification",
                        "nodeType": "goal_verification",
                        "objective": "Verify the summary artifact satisfies the frozen requirement.",
                        "claimRefs": ["CLAIM-summary-artifact"],
                        "dependsOn": ["NODE-write-summary"],
                        "inputRefs": ["NODE-write-summary"],
                        "expectedOutputs": [],
                        "capabilityRequests": [],
                        "gateRefs": ["GATE-alignment-complete"],
                        "runtimeRef": "runtime/local-goal@sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
                        "budgetRequest": {
                            "maxModelCalls": 1,
                            "maxToolCalls": 1,
                            "maxSpawnedNodes": 0,
                            "maxWallSeconds": 30,
                            "maxCostUsd": 0.0,
                        },
                        "retryPolicy": {
                            "maxAttempts": 1,
                            "retryableFailureClasses": [],
                            "idempotencyKeyRequired": False,
                        },
                        "timeoutSeconds": 30,
                        "sideEffect": "idempotent",
                        "terminalGoalVerification": True,
                    },
                ],
            },
        },
    }


def _fixture_acceptance_output() -> dict[str, Any]:
    return {
        "summary": "Acceptance requires governed evidence for the deterministic summary artifact.",
        "claimGraph": {
            "apiVersion": "ahra.dev/v1alpha1",
            "kind": "ClaimGraph",
            "metadata": {
                "name": "workflow-a-cli-fixture-claims",
                "goalId": "GOAL-PHASE1-EXAMPLE-ALIGNED",
                "version": 1,
            },
            "spec": {
                "goalRef": "GOAL-PHASE1-EXAMPLE-ALIGNED",
                "claims": [
                    {
                        "id": "CLAIM-summary-artifact",
                        "type": "functional",
                        "statement": "A deterministic summary artifact is produced in the local workspace.",
                        "criterionRefs": ["CRIT-summary-artifact"],
                        "dependsOn": [],
                        "riskLevel": "R1",
                        "required": True,
                        "requiredEvidenceKinds": ["artifact"],
                        "gateRefs": ["GATE-alignment-objective"],
                    }
                ],
            },
        },
    }


__all__ = [
    "WorkflowAFixtureDriver",
    "RequestDraftAdmissionError",
    "admit_request",
    "advance_session",
    "approve_requirement",
    "authorize_request",
    "draft_request",
    "load_request_draft",
    "read_snapshot",
    "start_session",
    "workflow_status",
]
