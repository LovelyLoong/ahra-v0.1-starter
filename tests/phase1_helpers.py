from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml

from ahra.acceptance_contracts import Claim, ClaimGraph, ClaimType, RiskLevel
from ahra.alignment_session import (
    ACCEPTANCE_DRAFT_OUTPUT,
    ALIGNMENT_DECISION_OUTPUT,
    REQUIREMENT_DRAFT_OUTPUT,
    AlignmentSessionManager,
)
from ahra.approval_service import ApprovalService
from ahra.awkp_state_writer import AwkpTaskStateWriter
from ahra.awkp_task_creator import AwkpTaskCreateRequest, AwkpTaskCreator
from ahra.goal_operations import GoalAwkpBridge, GoalAwkpBridgeRequest, GoalExecutionRequest, GoalOperationService, M1_PROFILE_REF
from ahra.intent_draft import IntentCapabilityNeed, IntentDraft
from ahra.plan_ir import CapabilityRequest, PlanBudget, PlanDraft, PlanNodeDraft, PlanOutputContract, RetryPolicy
from ahra.ports import AgentRunRequest, AgentRunResult
from ahra.request_admission import RequestDraftAdmission
from ahra.request_draft import RequestDraft, _claim_graph_to_mapping
from ahra.validation import load_document


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_INTENT = ROOT / "examples" / "intents" / "phase1-example-intent.yaml"


def example_intent(**replacements: Any) -> IntentDraft:
    draft = IntentDraft.from_mapping(load_document(EXAMPLE_INTENT))
    return replace(draft, **replacements) if replacements else draft


def aligned_approved_request(root: Path, intent: IntentDraft | None = None) -> GoalExecutionRequest:
    draft = request_draft_from_intent(root, intent or example_intent())
    RequestDraftAdmission().require_accepted(draft)
    approvals = ApprovalService()
    approval = approvals.request_authorization(draft, actor="agent:producer")
    approvals.approve(approval.approval_id, actor="human:maintainer")
    return approvals.freeze(draft, approval_id=approval.approval_id)


def request_draft_from_intent(root: Path, intent: IntentDraft) -> RequestDraft:
    manager = AlignmentSessionManager(_Phase1AlignmentDriver(intent))
    snapshot = manager.start(
        intent,
        profile_ref=M1_PROFILE_REF,
        producer_actor="agent:producer",
        workspace_ref=str(root / "workspace"),
        artifact_dir=str(root / ".ahra" / "artifacts"),
        store_path=str(root / ".ahra" / "goal-control.sqlite3"),
    )
    snapshot = asyncio.run(manager.advance(snapshot, "Keep the scope bounded.", actor="human:maintainer"))
    snapshot = manager.approve_requirement(snapshot, actor="human:maintainer")
    result = asyncio.run(manager.draft_request(snapshot))
    return result.request_draft


class _Phase1AlignmentDriver:
    def __init__(self, intent: IntentDraft) -> None:
        self.intent = intent

    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        if request.expected_output == ALIGNMENT_DECISION_OUTPUT:
            return AgentRunResult(
                output={
                    "message": "Requirement boundary is ready for human approval.",
                    "converged": True,
                    "frozenRequirement": self.intent.abstract_goal,
                    "missingDimensions": [],
                }
            )
        if request.expected_output == REQUIREMENT_DRAFT_OUTPUT:
            return AgentRunResult(
                output={
                    "summary": self.intent.abstract_goal,
                    "planDraft": _plan_from_intent(self.intent).to_dict(),
                }
            )
        if request.expected_output == ACCEPTANCE_DRAFT_OUTPUT:
            return AgentRunResult(
                output={
                    "summary": "Acceptance requires governed evidence for the requested output.",
                    "claimGraph": _claim_graph_to_mapping(_claim_graph_from_intent(self.intent)),
                }
            )
        raise AssertionError(f"unexpected Workflow A fixture output {request.expected_output}")


def _claim_graph_from_intent(intent: IntentDraft) -> ClaimGraph:
    goal_ref = _goal_ref_from_intent(intent.intent_id)
    objective_claim = Claim(
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
        depends_on=(objective_claim.claim_id,),
        risk_level=RiskLevel.R1,
        required_evidence_kinds=("gate_run",),
        gate_refs=("GATE-alignment-complete",),
        required=True,
    )
    return ClaimGraph(goal_ref=goal_ref, version=1, claims=(objective_claim, completion_claim))


def _plan_from_intent(intent: IntentDraft) -> PlanDraft:
    goal_ref = _goal_ref_from_intent(intent.intent_id)
    objective_claim = "CLAIM-" + _id_tail(intent.intent_id, "OBJECTIVE")
    complete_claim = "CLAIM-" + _id_tail(intent.intent_id, "COMPLETE")
    capability_requests = tuple(
        CapabilityRequest(
            need.action,
            need.resources,
            risk_level=need.risk_level,
            approval_refs=need.policy_refs,
        )
        for need in intent.capability_needs
    )
    if not any(request.capability == "filesystem.write" for request in capability_requests):
        capability_requests = (*capability_requests, CapabilityRequest("filesystem.write", ("outputs/summary.txt",)))
    return PlanDraft(
        goal_ref=goal_ref,
        proposed_by="planner/phase1-test-fixture",
        rationale="Phase 1 test fixture produces an explicit untrusted RequestDraft for admission and authorization.",
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
                runtime_ref="runtime/local-goal@sha256:" + "e" * 64,
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
                runtime_ref="runtime/local-goal@sha256:" + "e" * 64,
                budget=PlanBudget(max_model_calls=1, max_tool_calls=1, max_spawned_nodes=0, max_wall_seconds=30, max_cost_usd=0.0),
                retry_policy=RetryPolicy(max_attempts=1),
                timeout_seconds=30,
                terminal_goal_verification=True,
            ),
        ),
    )


def _goal_ref_from_intent(intent_id: str) -> str:
    return "GOAL-" + _id_tail(intent_id, "ALIGNED")


def _id_tail(intent_id: str, fallback: str) -> str:
    cleaned = "".join(char if char.isalnum() else "-" for char in intent_id.upper())
    cleaned = cleaned.removeprefix("INTENT-").strip("-")
    if not cleaned:
        return fallback
    return f"{cleaned}-{fallback}"


def write_request(path: Path, request: GoalExecutionRequest) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(request.to_dict(), sort_keys=False), encoding="utf-8")
    return path


def start_goal(root: Path, intent: IntentDraft | None = None) -> dict[str, Any]:
    request = aligned_approved_request(root, intent)
    request_path = write_request(root / "goal-run-request.yaml", request)
    return GoalOperationService().start(request_path)


def network_intent_with_policy() -> IntentDraft:
    return example_intent(
        capability_needs=(
            IntentCapabilityNeed(
                action="network.access",
                resources=("https://example.invalid/status",),
                reason="Fetch a governed status summary.",
                risk_level="R2",
                policy_refs=("POLICY-network-test",),
            ),
            IntentCapabilityNeed(
                action="filesystem.write",
                resources=("outputs/summary.txt",),
                reason="Persist the governed network summary.",
                risk_level="R1",
            ),
        ),
        risk_hint="R2",
    )


def bridge_completed_goal(root: Path, start_result: dict[str, Any]) -> dict[str, Any]:
    work_root = root / "work"
    task_id = "TASK-PHASE1-E2E"
    producer = "agent:producer"
    verifier = "agent:verifier"
    AwkpTaskCreator().create(
        AwkpTaskCreateRequest(
            task_id=task_id,
            title="Phase 1 temporary bridge task",
            description="Temporary task used by Phase 1 integration test.",
            context_id="CTX-phase1-test",
            acceptance_criteria=("The GoalExecution evidence is accepted by EvidenceGate.",),
            work_root=work_root,
            actor="agent:test",
            output_contract_kinds=("verification_summary",),
        )
    )
    claim = AwkpTaskStateWriter(work_root=work_root).acquire_working(
        task_id,
        expected_version=0,
        actor=producer,
        idempotency_key=f"{task_id}:claim",
        reason="Claim temporary Phase 1 bridge task.",
    )
    artifact_dir = root / ".ahra" / "artifacts"
    evidence_ref = first_kernel_evidence_ref(artifact_dir)
    report = write_gate_report(root / "awkp-gate-input.json", task_id, evidence_ref, verifier)
    bridge = GoalAwkpBridge(work_root=work_root).run(
        GoalAwkpBridgeRequest(
            goal_execution_id=start_result["goalExecutionId"],
            task=task_id,
            work_root=work_root,
            expected_task_version=claim.state_version,
            producer_actor=producer,
            verifier_actor=verifier,
            fencing_token=str(claim.fencing_token),
            report_paths=(report,),
            db_path=root / ".ahra" / "goal-control.sqlite3",
            artifact_dir=artifact_dir,
            idempotency_key_prefix=f"{task_id}:phase1-bridge",
        )
    )
    return {
        "task_id": task_id,
        "terminal_state": bridge.orchestration.terminal_state,
        "evidence_ref": evidence_ref,
        "state": json.loads((work_root / "tasks" / task_id / "state.json").read_text(encoding="utf-8")),
    }


def first_kernel_evidence_ref(artifact_dir: Path) -> str:
    for path in sorted((artifact_dir / "kernel-evidence").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        return str(data["metadata"]["evidenceId"])
    raise AssertionError("kernel evidence was not materialized")


def write_gate_report(path: Path, task_id: str, evidence_ref: str, verifier: str) -> Path:
    payload = {
        "schema_version": "ahra/evidence-gate-input/0.1",
        "task_id": task_id,
        "verifier": verifier,
        "decision": "approve",
        "summary": "Verifier mapped Phase 1 temporary task criterion to kernel evidence.",
        "criteria": [
            {
                "criterion_index": 1,
                "status": "passed",
                "evidence_refs": [evidence_ref],
                "command_refs": ["CMD-phase1-kernel-evidence"],
                "notes": "GoalExecution produced kernel EvidenceV2.",
            }
        ],
        "commands": [
            {
                "command_id": "CMD-phase1-kernel-evidence",
                "command": "GoalOperationService.start",
                "status": "passed",
                "criterion_indices": [1],
                "evidence_refs": [evidence_ref],
            }
        ],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path
