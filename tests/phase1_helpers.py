from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml

from ahra.alignment_engine import AlignmentWorkflowEngine
from ahra.approval_service import ApprovalService
from ahra.awkp_state_writer import AwkpTaskStateWriter
from ahra.awkp_task_creator import AwkpTaskCreateRequest, AwkpTaskCreator
from ahra.goal_operations import GoalAwkpBridge, GoalAwkpBridgeRequest, GoalExecutionRequest, GoalOperationService
from ahra.intent_draft import IntentCapabilityNeed, IntentDraft
from ahra.request_admission import RequestDraftAdmission
from ahra.validation import load_document


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_INTENT = ROOT / "examples" / "intents" / "phase1-example-intent.yaml"


def example_intent(**replacements: Any) -> IntentDraft:
    draft = IntentDraft.from_mapping(load_document(EXAMPLE_INTENT))
    return replace(draft, **replacements) if replacements else draft


def aligned_approved_request(root: Path, intent: IntentDraft | None = None) -> GoalExecutionRequest:
    engine = AlignmentWorkflowEngine()
    session = engine.start(intent or example_intent())
    for actor, message in (
        ("human:maintainer", "Keep the scope bounded."),
        ("agent:alignment", "Draft the claims."),
        ("agent:alignment", "Draft the plan."),
    ):
        session = engine.advance(session, actor=actor, message=message)
    draft = engine.draft_request(
        session,
        producer_actor="agent:producer",
        workspace_ref=str(root / "workspace"),
        artifact_dir=str(root / ".ahra" / "artifacts"),
        store_path=str(root / ".ahra" / "goal-control.sqlite3"),
    )
    RequestDraftAdmission().require_accepted(draft)
    approvals = ApprovalService()
    approval = approvals.request_authorization(draft, actor="agent:producer")
    approvals.approve(approval.approval_id, actor="human:maintainer")
    return approvals.freeze(draft, approval_id=approval.approval_id)


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
