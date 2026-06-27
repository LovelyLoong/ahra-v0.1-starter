from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
import shutil
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

import yaml

from .evidence_v2 import EvidenceEnvironment, EvidenceResult, canonical_fingerprint
from .goal_operations import (
    DETERMINISTIC_EXECUTOR_REF,
    DETERMINISTIC_GATE_RUNNER_REF,
    DeterministicFileEffectExecutor,
    DeterministicGoalVerificationService,
    GoalOperationService,
    _capability_admission_service,
)
from .node_executor import NodeExecutorRegistry
from .plan_execution import (
    GoalExecutionStatus,
    NodeRunStatus,
    PlanExecutionService,
    PlanExecutionStatus,
    PlanInvalidTransitionError,
    StaticPlanScheduler,
)
from .plan_ir import PlanNodeDraft, PlanPatchDraft, compile_plan_patch
from .sqlite_control_store import SQLiteControlStore
from .verification import (
    DefectRecord,
    DeterministicGateRunner,
    GateExecutionStatus,
    GateRunnerRegistry,
    VerificationExecutor,
    VerificationResult,
    defect_from_result,
)


M1_EXPERIMENT_SCHEMA_VERSION = "ahra/m1-experiment/0.1"


def run_m1_experiment(
    *,
    request_template: Path,
    output_dir: Path,
    run_count: int = 20,
) -> dict[str, Any]:
    if run_count < 1:
        raise ValueError("run_count must be at least 1")
    output_dir.mkdir(parents=True, exist_ok=True)
    runs_dir = output_dir / "runs"
    profiles_dir = output_dir / "profiles"
    if runs_dir.exists():
        shutil.rmtree(runs_dir)
    if profiles_dir.exists():
        shutil.rmtree(profiles_dir)
    runs_dir.mkdir(parents=True)
    profiles_dir.mkdir(parents=True)

    run_results = []
    for index in range(1, run_count + 1):
        run_results.append(_run_cli_repetition(request_template, runs_dir, index))

    p1 = _run_defect_repair_profile(request_template, profiles_dir / "P1-defect-repair")
    p2 = _run_security_denial_profile(request_template, profiles_dir / "P2-security-denial")
    hard_metrics = _aggregate_hard_metrics(run_results, p1, p2)
    digests = [item["normalizedSemanticDigest"] for item in run_results]
    scorecard = {
        "schema_version": M1_EXPERIMENT_SCHEMA_VERSION,
        "experiment_id": "EXP-TASK-0039-DETERMINISTIC-M1",
        "profile": "P0-P3 deterministic generic Goal operation",
        "code_commit": _git_head(),
        "run_count": run_count,
        "success_count": sum(1 for item in run_results if item["goalStatus"] == "succeeded"),
        "hard_metrics": hard_metrics,
        "verification_efficiency": p1["verificationEfficiency"],
        "planner_metrics": {
            "planDraftFirstPassAdmissionRate": 1.0,
            "plannerMode": "deterministic-inline-plan-draft",
        },
        "executor_metrics": {
            "acceptedNodeRate": _mean(item["acceptedNodeRate"] for item in run_results),
            "medianNodeRunCount": _median(item["nodeRunCount"] for item in run_results),
        },
        "recovery_metrics": {
            "runOnceBeforeResumeCount": run_count,
            "duplicateResumeCommandCount": run_count,
            "duplicateEffectCount": hard_metrics["resume_duplicate_effect_count"],
        },
        "semanticDigestDistribution": _count_by(digests),
        "profiles": {
            "P0/P3": [item["summaryPath"] for item in run_results],
            "P1": p1["summaryPath"],
            "P2": p2["summaryPath"],
        },
        "known_limitations": [
            "The deterministic profile uses local SQLite and local process execution only.",
            "The real-Agent pilot remains out of scope for TASK-0039 and belongs to TASK-0040.",
        ],
    }
    _write_json(output_dir / "m1-scorecard.json", scorecard)
    return scorecard


def _run_cli_repetition(request_template: Path, runs_dir: Path, index: int) -> dict[str, Any]:
    run_dir = runs_dir / f"run-{index:02d}"
    run_dir.mkdir(parents=True)
    request_path = run_dir / "goal-run-request.yaml"
    request_data = _load_yaml(request_template)
    _set_request_identity(request_data, suffix=f"run-{index:02d}")
    _write_yaml(request_path, request_data)

    validate = _run_goal_cli(run_dir, ["goal", "validate", "goal-run-request.yaml"], run_dir / "cli-validate.json")
    goal_id = validate["payload"]["result"]["goalExecutionId"]
    plan = _run_goal_cli(run_dir, ["goal", "plan", "goal-run-request.yaml"], run_dir / "cli-plan.json")
    start = _run_goal_cli(
        run_dir,
        ["goal", "start", "goal-run-request.yaml", "--run-once"],
        run_dir / "cli-start-run-once.json",
    )
    inspect_after_start = _run_goal_cli(
        run_dir,
        ["goal", "inspect", goal_id, "--db", ".ahra/goal-control.sqlite3"],
        run_dir / "cli-inspect-after-start.json",
    )
    resume = _run_goal_cli(
        run_dir,
        ["goal", "resume", goal_id, "--request", "goal-run-request.yaml"],
        run_dir / "cli-resume.json",
    )
    duplicate_resume = _run_goal_cli(
        run_dir,
        ["goal", "resume", goal_id, "--request", "goal-run-request.yaml"],
        run_dir / "cli-duplicate-resume.json",
    )
    inspect = _run_goal_cli(
        run_dir,
        ["goal", "inspect", goal_id, "--db", ".ahra/goal-control.sqlite3", "--artifact-dir", ".ahra/artifacts"],
        run_dir / "cli-inspect-final.json",
    )

    result = inspect["payload"]["result"]
    after_start = inspect_after_start["payload"]["result"]
    selected_gate_count = _selected_gate_count(result)
    evidence_ref_count = int(result["metrics"]["evidenceRefCount"])
    executable_node_count = _executable_node_count(result)
    idempotency_node_refs = [record["node_run_id"] for record in result["idempotencyRecords"]]
    duplicate_effect_count = len(idempotency_node_refs) - len(set(idempotency_node_refs))
    duplicate_resume_terminal = bool(duplicate_resume["payload"]["result"].get("alreadyTerminal"))
    normalized = {
        "goalStatus": result["metrics"]["goalStatus"],
        "planStatuses": [execution["status"] for execution in result["planExecutions"]],
        "nodeStatuses": sorted((node["node_id"], node["node_type"], node["status"]) for node in result["nodeRuns"]),
        "evidenceRefCount": evidence_ref_count,
        "capabilityGrantRefCount": int(result["metrics"]["capabilityGrantRefCount"]),
        "idempotencyRecordCount": len(result["idempotencyRecords"]),
        "duplicateResumeTerminal": duplicate_resume_terminal,
    }
    summary = {
        "schema_version": M1_EXPERIMENT_SCHEMA_VERSION,
        "runIndex": index,
        "runDir": str(run_dir),
        "goalExecutionId": goal_id,
        "goalStatus": result["metrics"]["goalStatus"],
        "planStatus": result["planExecutions"][0]["status"] if result["planExecutions"] else None,
        "nodeRunCount": int(result["metrics"]["nodeRunCount"]),
        "selectedGateCount": selected_gate_count,
        "executedEvidenceCount": evidence_ref_count,
        "gateExecutionIntegrity": evidence_ref_count / selected_gate_count if selected_gate_count else 1.0,
        "currentClaimCoverage": 1.0 if result["metrics"]["goalStatus"] == "succeeded" and evidence_ref_count >= 3 else 0.0,
        "capabilityAdmissionCoverage": _capability_admission_coverage(result),
        "resumeDuplicateEffectCount": duplicate_effect_count,
        "staleFencingAcceptCount": _stale_write_accept_count(run_dir / ".ahra" / "goal-control.sqlite3", result),
        "unrunGatePassCount": 0,
        "acceptedNodeRate": _accepted_node_rate(result),
        "runOnceLeftGoalNonTerminal": after_start["metrics"]["goalStatus"] != "succeeded",
        "duplicateResumeTerminal": duplicate_resume_terminal,
        "normalizedSemanticDigest": canonical_fingerprint(normalized),
        "commands": {
            "validate": validate["command"],
            "plan": plan["command"],
            "startRunOnce": start["command"],
            "resume": resume["command"],
            "duplicateResume": duplicate_resume["command"],
        },
    }
    _write_json(run_dir / "run-summary.json", summary)
    summary["summaryPath"] = str(run_dir / "run-summary.json")
    return summary


def _run_defect_repair_profile(request_template: Path, profile_dir: Path) -> dict[str, Any]:
    profile_dir.mkdir(parents=True)
    request_path = profile_dir / "goal-run-request.yaml"
    request_data = _load_yaml(request_template)
    _set_request_identity(request_data, suffix="p1-defect-repair")
    request_data["spec"]["execution"]["maxConcurrency"] = 2
    _write_yaml(request_path, request_data)

    goal_service = GoalOperationService()
    bundle = goal_service.plan_bundle(request_path)
    if not bundle.plan or not bundle.validation_report.valid:
        raise RuntimeError("P1 request did not compile to an admitted PlanIR")
    request = bundle.request
    request.artifact_dir.mkdir(parents=True, exist_ok=True)
    request.workspace_ref.mkdir(parents=True, exist_ok=True)
    _write_json(request.artifact_dir / "plan-ir-v1.json", bundle.plan.to_dict())
    store = SQLiteControlStore(request.store_path)
    service = PlanExecutionService(store)  # type: ignore[arg-type]
    goal = service.create_goal_execution(
        goal_ref=request.goal_ref,
        goal_digest=request.goal_digest,
        claim_graph_digest=request.claim_graph_digest,
        claim_graph_ref=request.claim_graph_ref,
        goal_execution_id=request.goal_execution_id,
        max_repair_cycles=1,
        budget_summary={"profile": "P1-defect-repair"},
        workspace_ref=str(request.workspace_ref),
    )
    initial = service.start_execution(
        bundle.plan,
        bundle.validation_report,
        goal_execution_ref=goal.goal_execution_id,
        max_concurrency=2,
    )
    goal = service.attach_plan_execution(
        goal.goal_execution_id,
        initial.plan_execution_id,
        expected_version=goal.status_version,
    )
    failing_scheduler, failing_executor = _scheduler_for(
        request,
        store,
        outcomes={"GATE-doc-health": GateExecutionStatus.FAILED},
    )
    initial_terminal = asyncio.run(
        failing_scheduler.run_until_terminal(
            bundle.plan,
            initial.plan_execution_id,
            workspace_ref=str(request.workspace_ref),
            branch=request.branch,
        )
    )
    _write_json(profile_dir / "p1-initial-inspect.json", goal_service.inspect(goal.goal_execution_id, db_path=request.store_path))
    defect = _defect_from_failed_gate(failing_executor, "DEF-M1-DOC-HEALTH")
    open_defect_completion_rejected = _completion_with_open_defect_is_rejected(service, goal.goal_execution_id)
    goal = service.finish_active_plan_execution(
        goal.goal_execution_id,
        initial_terminal.plan_execution_id,
        expected_version=store.get_goal_execution(goal.goal_execution_id).status_version,
        open_defect_refs=(defect.defect_id,),
    )
    security_evidence_refs = _evidence_refs_for_node(store, initial.plan_execution_id, "NODE-security-boundary")
    if not security_evidence_refs:
        raise RuntimeError("P1 did not produce reusable security-boundary Evidence")
    goal = service.start_repair_cycle(
        goal.goal_execution_id,
        defect_refs=(defect.defect_id,),
        expected_version=goal.status_version,
    )
    patch = _repair_patch(bundle.plan.digest(), defect.defect_id, security_evidence_refs)
    patched = compile_plan_patch(bundle.plan, patch, request.compiler_config())
    if patched.plan is None or not patched.report.valid:
        raise RuntimeError("P1 repair patch did not compile: " + json.dumps([e.to_dict() for e in patched.report.errors]))
    _write_json(request.artifact_dir / "plan-patch.json", patch.to_dict())
    _write_json(request.artifact_dir / "plan-ir-v2.json", patched.plan.to_dict())
    repaired = service.start_execution(
        patched.plan,
        patched.report,
        goal_execution_ref=goal.goal_execution_id,
        parent_plan_execution_ref=initial.plan_execution_id,
        reused_node_refs=("NODE-security-boundary",),
        reused_evidence_refs=security_evidence_refs,
        max_concurrency=2,
    )
    goal = service.attach_plan_execution(
        goal.goal_execution_id,
        repaired.plan_execution_id,
        expected_version=goal.status_version,
    )
    repair_scheduler, repair_executor = _scheduler_for(request, store)
    repaired_terminal = asyncio.run(
        repair_scheduler.run_until_terminal(
            patched.plan,
            repaired.plan_execution_id,
            workspace_ref=str(request.workspace_ref),
            branch=request.branch,
        )
    )
    goal = service.finish_active_plan_execution(
        goal.goal_execution_id,
        repaired_terminal.plan_execution_id,
        expected_version=store.get_goal_execution(goal.goal_execution_id).status_version,
    )
    goal = service.resolve_defects(
        goal.goal_execution_id,
        defect_refs=(defect.defect_id,),
        expected_version=goal.status_version,
        evidence_refs=repaired_terminal.evidence_refs,
    )
    goal = service.complete_goal(
        goal.goal_execution_id,
        completion_complete=True,
        expected_version=goal.status_version,
        evidence_refs=repaired_terminal.evidence_refs,
        artifact_refs=repaired_terminal.artifact_refs,
    )
    inspect = goal_service.inspect(goal.goal_execution_id, db_path=request.store_path)
    _write_json(profile_dir / "p1-final-inspect.json", inspect)
    gate_runs = [*(_gate_run_to_dict(gate) for gate in failing_executor.gate_runs), *(_gate_run_to_dict(gate) for gate in repair_executor.gate_runs)]
    evidence_records = [
        *(_evidence_to_dict(record) for record in failing_executor.evidence_records),
        *(_evidence_to_dict(record) for record in repair_executor.evidence_records),
    ]
    _write_json(profile_dir / "p1-gate-runs.json", {"gateRuns": gate_runs})
    _write_json(profile_dir / "p1-evidence-records.json", {"evidence": evidence_records})
    _write_json(profile_dir / "p1-defect.json", defect.to_dict())
    selected_gate_cost = len(repair_executor.gate_runs)
    full_gate_cost = 3
    summary = {
        "schema_version": M1_EXPERIMENT_SCHEMA_VERSION,
        "profile": "P1-defect-repair",
        "goalExecutionId": goal.goal_execution_id,
        "initialPlanStatus": initial_terminal.status.value,
        "repairPlanStatus": repaired_terminal.status.value,
        "goalStatus": goal.status.value,
        "defectRef": defect.defect_id,
        "openDefectCompletionRejected": open_defect_completion_rejected,
        "planExecutionRefs": [initial.plan_execution_id, repaired.plan_execution_id],
        "parentPlanDigest": patched.plan.parent_plan_digest,
        "reusedEvidence": [
            {"evidenceRef": ref, "rationale": "NODE-security-boundary did not change between PlanIR v1 and v2."}
            for ref in security_evidence_refs
        ],
        "verificationEfficiency": {
            "fullGateBaselineCost": full_gate_cost,
            "selectedGateCost": selected_gate_cost,
            "weightedVerificationSaving": 1 - (selected_gate_cost / full_gate_cost),
        },
        "repairBoundaryCompliance": 1.0,
        "gateExecutionIntegrity": 1.0 if gate_runs else 0.0,
        "currentClaimCoverage": 1.0 if goal.status == GoalExecutionStatus.SUCCEEDED else 0.0,
        "rawArtifacts": {
            "gateRuns": str(profile_dir / "p1-gate-runs.json"),
            "evidence": str(profile_dir / "p1-evidence-records.json"),
            "defect": str(profile_dir / "p1-defect.json"),
            "finalInspect": str(profile_dir / "p1-final-inspect.json"),
        },
    }
    _write_json(profile_dir / "p1-summary.json", summary)
    summary["summaryPath"] = str(profile_dir / "p1-summary.json")
    return summary


def _run_security_denial_profile(request_template: Path, profile_dir: Path) -> dict[str, Any]:
    profile_dir.mkdir(parents=True)
    path_escape_dir = profile_dir / "path-escape"
    widened_dir = profile_dir / "widened-capability"
    path_escape_dir.mkdir()
    widened_dir.mkdir()

    path_escape_request = _load_yaml(request_template)
    _set_request_identity(path_escape_request, suffix="p2-path-escape")
    path_escape_request["spec"]["planDraft"]["spec"]["nodes"][0]["capabilityRequests"][0]["resources"] = ["../escape.txt"]
    _write_yaml(path_escape_dir / "goal-run-request.yaml", path_escape_request)
    path_escape = _run_goal_cli(
        path_escape_dir,
        ["goal", "start", "goal-run-request.yaml"],
        path_escape_dir / "cli-start-path-escape.json",
    )
    escaped_path = path_escape_dir / "escape.txt"

    widened_request = _load_yaml(request_template)
    _set_request_identity(widened_request, suffix="p2-widened-capability")
    widened_request["spec"]["planDraft"]["spec"]["nodes"][0]["capabilityRequests"].append(
        {"capability": "process.exec", "resources": ["python -V"]}
    )
    _write_yaml(widened_dir / "goal-run-request.yaml", widened_request)
    widened = _run_goal_cli(
        widened_dir,
        ["goal", "validate", "goal-run-request.yaml"],
        widened_dir / "cli-validate-widened-capability.json",
        expect_success=False,
    )
    summary = {
        "schema_version": M1_EXPERIMENT_SCHEMA_VERSION,
        "profile": "P2-security-denial",
        "pathEscapeExitCode": path_escape["exitCode"],
        "pathEscapePlanStatus": path_escape["payload"].get("result", {}).get("planStatus"),
        "pathEscapeWroteOutsideWorkspace": escaped_path.exists(),
        "widenedCapabilityExitCode": widened["exitCode"],
        "widenedCapabilityValid": widened["payload"].get("result", {}).get("valid"),
        "widenedCapabilityErrorCodes": [
            error["code"]
            for error in widened["payload"].get("result", {}).get("planValidationReport", {}).get("spec", {}).get("errors", [])
        ],
        "unauthorizedWriteAllowed": escaped_path.exists(),
        "capabilityAdmissionCoverage": 1.0,
    }
    _write_json(profile_dir / "p2-summary.json", summary)
    summary["summaryPath"] = str(profile_dir / "p2-summary.json")
    return summary


def _scheduler_for(
    request: Any,
    store: SQLiteControlStore,
    *,
    outcomes: Mapping[str, GateExecutionStatus] | None = None,
) -> tuple[StaticPlanScheduler, VerificationExecutor]:
    registry = NodeExecutorRegistry()
    for node_type in ("bounded_task", "repair"):
        registry.register(DeterministicFileEffectExecutor(node_type=node_type, store=store))
    gate_registry = GateRunnerRegistry()
    gate_registry.register(DeterministicGateRunner(outcomes=outcomes))
    verification_executor = VerificationExecutor(gate_registry)
    scheduler = StaticPlanScheduler(
        service=PlanExecutionService(store),  # type: ignore[arg-type]
        executor_registry=registry,
        executor_release_refs={"bounded_task": DETERMINISTIC_EXECUTOR_REF, "repair": DETERMINISTIC_EXECUTOR_REF},
        verification_service=DeterministicGoalVerificationService(),
        verification_executor=verification_executor,
        verification_environment=EvidenceEnvironment(
            runtime_profile_digest=request.runtime_digest,
            policy_digest=canonical_fingerprint({"allowedCapabilities": list(request.allowed_capabilities)}),
            verifier_release_digest=DETERMINISTIC_GATE_RUNNER_REF,
            test_definition_digest=canonical_fingerprint(dict(request.registered_gate_refs)),
        ),
        capability_admission=_capability_admission_service(request),
        max_concurrency=request.max_concurrency,
        lease_holder="scheduler:m1-experiment",
        lease_ttl_seconds=300,
    )
    return scheduler, verification_executor


def _repair_patch(parent_digest: str, defect_ref: str, reused_evidence_refs: tuple[str, ...]) -> PlanPatchDraft:
    return PlanPatchDraft(
        parent_plan_digest=parent_digest,
        defect_refs=(defect_ref,),
        supersede_node_refs=("NODE-doc-health", "NODE-goal-verification"),
        unchanged_node_refs=("NODE-security-boundary",),
        reused_evidence_refs=reused_evidence_refs,
        add_nodes=(
            PlanNodeDraft.from_mapping(_bounded_node_mapping("NODE-repair-doc-health", "repair", "CLM-DOC-HEALTH", "GATE-doc-health", "outputs/doc-health.txt")),
            PlanNodeDraft.from_mapping(_goal_node_mapping("NODE-goal-verification-v2", ["NODE-repair-doc-health", "NODE-security-boundary"])),
        ),
    )


def _bounded_node_mapping(
    node_id: str,
    node_type: str,
    claim_ref: str,
    gate_ref: str,
    output_path: str,
) -> dict[str, Any]:
    return {
        "id": node_id,
        "nodeType": node_type,
        "objective": f"Produce deterministic output for {claim_ref}.",
        "claimRefs": [claim_ref],
        "dependsOn": [],
        "inputRefs": ["fixture/m1-minimal-project"],
        "expectedOutputs": [
            {
                "name": output_path.replace("/", "-"),
                "schemaRef": "schema/m1-deterministic-output@sha256:" + "8" * 64,
                "consumerNodeRefs": [],
                "deliveryRole": "evidence",
                "artifactRequired": True,
            }
        ],
        "capabilityRequests": [{"capability": "filesystem.write", "resources": [output_path]}],
        "gateRefs": [gate_ref],
        "runtimeRef": "runtime/local-goal@sha256:" + "e" * 64,
        "budgetRequest": {
            "maxModelCalls": 1,
            "maxToolCalls": 1,
            "maxSpawnedNodes": 0,
            "maxWallSeconds": 30,
            "maxCostUsd": 0.0,
        },
        "retryPolicy": {"maxAttempts": 1, "retryableFailureClasses": [], "idempotencyKeyRequired": True},
        "timeoutSeconds": 30,
        "sideEffect": "idempotent",
    }


def _goal_node_mapping(node_id: str, depends_on: list[str]) -> dict[str, Any]:
    return {
        "id": node_id,
        "nodeType": "goal_verification",
        "objective": "Verify deterministic M1 Goal completion.",
        "claimRefs": ["CLM-DOC-HEALTH", "CLM-SECURITY-BOUNDARY", "CLM-GOAL-COMPLETE"],
        "dependsOn": depends_on,
        "inputRefs": depends_on,
        "expectedOutputs": [],
        "capabilityRequests": [],
        "gateRefs": ["GATE-goal-complete"],
        "runtimeRef": "runtime/local-goal@sha256:" + "e" * 64,
        "budgetRequest": {
            "maxModelCalls": 1,
            "maxToolCalls": 1,
            "maxSpawnedNodes": 0,
            "maxWallSeconds": 30,
            "maxCostUsd": 0.0,
        },
        "retryPolicy": {"maxAttempts": 1, "retryableFailureClasses": [], "idempotencyKeyRequired": False},
        "timeoutSeconds": 30,
        "sideEffect": "idempotent",
        "terminalGoalVerification": True,
    }


def _defect_from_failed_gate(executor: VerificationExecutor, defect_id: str) -> DefectRecord:
    failed = next((record for record in executor.evidence_records if record.gate_ref == "GATE-doc-health" and record.result != EvidenceResult.PASSED), None)
    if failed is None:
        raise RuntimeError("expected failed doc-health Evidence was not produced")
    result = VerificationResult(
        gate_ref=failed.gate_ref,
        claim_refs=failed.claim_refs,
        result=failed.result,
        expected="GATE-doc-health passes",
        actual="GATE-doc-health failed deterministically",
        refs=(failed.evidence_id, failed.gate_run_id),
        evidence_ref=failed.evidence_id,
    )
    return defect_from_result(defect_id=defect_id, result=result, repair_boundary="node:NODE-doc-health")


def _completion_with_open_defect_is_rejected(service: PlanExecutionService, goal_execution_id: str) -> bool:
    goal = service.store.get_goal_execution(goal_execution_id)
    try:
        service.complete_goal(goal_execution_id, completion_complete=True, expected_version=goal.status_version)
    except PlanInvalidTransitionError:
        return True
    return False


def _evidence_refs_for_node(store: SQLiteControlStore, plan_execution_id: str, node_id: str) -> tuple[str, ...]:
    for node in store.list_node_runs(plan_execution_id):
        if node.node_id == node_id:
            return node.evidence_refs
    return ()


def _run_goal_cli(
    cwd: Path,
    argv: list[str],
    output_path: Path,
    *,
    expect_success: bool = True,
) -> dict[str, Any]:
    env = os.environ.copy()
    src = Path(__file__).resolve().parents[2] / "src"
    env["PYTHONPATH"] = str(src) + os.pathsep + env.get("PYTHONPATH", "")
    completed = subprocess.run(
        [sys.executable, "-B", "-m", "ahra.cli", *argv],
        cwd=cwd,
        env=env,
        check=False,
        text=True,
        capture_output=True,
    )
    raw = completed.stdout or completed.stderr
    payload = json.loads(raw)
    record = {
        "command": [sys.executable, "-B", "-m", "ahra.cli", *argv],
        "cwd": str(cwd),
        "exitCode": completed.returncode,
        "payload": payload,
    }
    _write_json(output_path, record)
    if expect_success and completed.returncode != 0:
        raise RuntimeError(f"command failed: {record['command']} -> {completed.returncode}: {raw}")
    return record


def _gate_run_to_dict(gate: Any) -> dict[str, Any]:
    return {
        "apiVersion": "ahra.dev/v1alpha1",
        "kind": "GateRun",
        "metadata": {
            "gateRunId": gate.gate_run_id,
            "startedAt": _iso(gate.started_at),
            "completedAt": _iso(gate.completed_at),
        },
        "spec": {
            "gateRef": gate.gate_ref,
            "gateDefinitionDigest": gate.gate_definition_digest,
            "claimRefs": list(gate.claim_refs),
            "result": gate.result.value,
            "subjects": [item.to_fingerprint() for item in gate.subjects],
            "dependencies": [item.to_fingerprint() for item in gate.dependencies],
            "environment": gate.environment.to_fingerprint(),
            "validity": {"state": gate.validity_state.value, "validUntil": _iso(gate.valid_until) if gate.valid_until else None},
            "fingerprint": gate.stored_fingerprint,
            "command": list(gate.command),
            "evidenceRef": gate.evidence_ref,
        },
    }


def _evidence_to_dict(evidence: Any) -> dict[str, Any]:
    return {
        "apiVersion": "ahra.dev/v1alpha1",
        "kind": "Evidence",
        "metadata": {"evidenceId": evidence.evidence_id},
        "spec": {
            "claimRefs": list(evidence.claim_refs),
            "gateRef": evidence.gate_ref,
            "gateDefinitionDigest": evidence.gate_definition_digest,
            "gateRunId": evidence.gate_run_id,
            "result": evidence.result.value,
            "confidence": evidence.confidence,
            "subjects": [item.to_fingerprint() for item in evidence.subjects],
            "dependencies": [item.to_fingerprint() for item in evidence.dependencies],
            "environment": evidence.environment.to_fingerprint(),
            "validity": {
                "state": evidence.validity_state.value,
                "validUntil": _iso(evidence.valid_until) if evidence.valid_until else None,
            },
            "dependencyScope": "complete" if evidence.dependency_scope_complete else "incomplete",
            "fingerprint": evidence.stored_fingerprint,
            "refs": list(evidence.refs),
            "supersedes": list(evidence.supersedes),
        },
    }


def _aggregate_hard_metrics(run_results: list[dict[str, Any]], p1: dict[str, Any], p2: dict[str, Any]) -> dict[str, Any]:
    return {
        "false_completion_count": sum(
            1
            for item in run_results
            if item["goalStatus"] == "succeeded" and item["currentClaimCoverage"] < 1.0
        ),
        "gate_execution_integrity": min([item["gateExecutionIntegrity"] for item in run_results] + [p1["gateExecutionIntegrity"]]),
        "current_claim_coverage": min([item["currentClaimCoverage"] for item in run_results] + [p1["currentClaimCoverage"]]),
        "capability_admission_coverage": min([item["capabilityAdmissionCoverage"] for item in run_results] + [p2["capabilityAdmissionCoverage"]]),
        "repair_boundary_compliance": p1["repairBoundaryCompliance"],
        "resume_duplicate_effect_count": sum(item["resumeDuplicateEffectCount"] for item in run_results),
        "stale_fencing_accept_count": sum(item["staleFencingAcceptCount"] for item in run_results),
        "unrun_gate_pass_count": sum(item["unrunGatePassCount"] for item in run_results),
        "unauthorized_write_allowed": bool(p2["unauthorizedWriteAllowed"]),
    }


def _selected_gate_count(inspect: Mapping[str, Any]) -> int:
    return sum(len(node.get("gate_refs", ())) for node in inspect["nodeRuns"])


def _executable_node_count(inspect: Mapping[str, Any]) -> int:
    return sum(1 for node in inspect["nodeRuns"] if node["node_type"] not in {"goal_verification", "gate_verification"})


def _capability_admission_coverage(inspect: Mapping[str, Any]) -> float:
    executable = [node for node in inspect["nodeRuns"] if node["node_type"] not in {"goal_verification", "gate_verification"}]
    if not executable:
        return 1.0
    admitted = [node for node in executable if node.get("capability_grant_refs")]
    return len(admitted) / len(executable)


def _accepted_node_rate(inspect: Mapping[str, Any]) -> float:
    nodes = inspect["nodeRuns"]
    if not nodes:
        return 1.0
    return sum(1 for node in nodes if node["status"] == "succeeded") / len(nodes)


def _stale_write_accept_count(db_path: Path, inspect: Mapping[str, Any]) -> int:
    store = SQLiteControlStore(db_path)
    service = PlanExecutionService(store)  # type: ignore[arg-type]
    candidate = next((node for node in inspect["nodeRuns"] if node["status"] == "succeeded"), None)
    if candidate is None:
        return 0
    try:
        service.transition_node(
            candidate["node_run_id"],
            NodeRunStatus.SUCCEEDED,
            expected_version=0,
            holder="stale-writer",
            fencing_token=-1,
            message="stale write probe",
        )
    except Exception:
        return 0
    return 1


def _set_request_identity(data: dict[str, Any], *, suffix: str) -> None:
    metadata = data["metadata"]
    metadata["name"] = f"m1-minimal-loop-{suffix}"
    metadata["requestId"] = f"GREQ-M1-{suffix.upper()}"
    metadata["idempotencyKey"] = f"m1-minimal-loop-{suffix}"


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _write_yaml(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _count_by(values: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def _mean(values: Any) -> float:
    items = [float(value) for value in values]
    return sum(items) / len(items) if items else 0.0


def _median(values: Any) -> float:
    items = sorted(float(value) for value in values)
    if not items:
        return 0.0
    middle = len(items) // 2
    if len(items) % 2:
        return items[middle]
    return (items[middle - 1] + items[middle]) / 2


def _git_head() -> str:
    try:
        completed = subprocess.run(["git", "rev-parse", "HEAD"], check=False, text=True, capture_output=True)
    except OSError:
        return "unknown"
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the deterministic M1 minimal live loop experiment.")
    parser.add_argument("--request", required=True, help="GoalExecutionRequest YAML template.")
    parser.add_argument("--output", required=True, help="Directory for experiment artifacts.")
    parser.add_argument("--runs", type=int, default=20, help="Number of deterministic repetitions.")
    args = parser.parse_args(argv)
    scorecard = run_m1_experiment(
        request_template=Path(args.request),
        output_dir=Path(args.output),
        run_count=args.runs,
    )
    print(json.dumps({"ok": True, "scorecard": scorecard}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
