from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

from .capabilities import CapabilityAdmissionService, CapabilityScope, RuntimeCapabilityProfile
from .domain import utc_now
from .evidence_v2 import canonical_fingerprint
from .node_executor import (
    NodeExecutionRequest,
    NodeExecutionResult,
    NodeExecutionStatus,
    NodeExecutionUsage,
    NodeExecutorRegistry,
)
from .plan_execution import (
    GoalExecutionStatus,
    PlanExecutionService,
    PlanExecutionStatus,
    StaticPlanScheduler,
)
from .plan_ir import PlanCompilerConfig, PlanDraft, PlanIR, PlanNodeType, PlanValidationReport, compile_plan_draft
from .sqlite_control_store import SQLiteControlStore, recover_sqlite_control_plane
from .verification import (
    CompletionGateResult,
    DefectRecord,
    DeterministicGateRunner,
    GateRunnerRegistry,
    VerificationExecutor,
    VerificationSelection,
    VerificationTrigger,
)


GOAL_REF = "GOAL-sqlite-recovery"
GOAL_DIGEST = "sha256:" + "1" * 64
CLAIM_GRAPH_DIGEST = "sha256:" + "2" * 64
NODE_TYPE_DIGEST = "sha256:" + "3" * 64
GOAL_NODE_DIGEST = "sha256:" + "4" * 64
GATE_EFFECT_DIGEST = "sha256:" + "5" * 64
GATE_GOAL_DIGEST = "sha256:" + "6" * 64
RUNTIME_REF = "runtime/local-sqlite-recovery@sha256:" + "7" * 64
RUNTIME_DIGEST = "sha256:" + "8" * 64
EXECUTOR_RELEASE = "sqlite-recovery-executor@sha256:" + "9" * 64
GOAL_EXECUTION_ID = "GEXEC-sqlite-recovery"


class DeterministicEffectExecutor:
    node_type = PlanNodeType.BOUNDED_TASK.value
    release_ref = EXECUTOR_RELEASE

    def __init__(self, *, store: SQLiteControlStore, workspace: Path, crash_after_idempotency: bool = False) -> None:
        self.store = store
        self.workspace = workspace
        self.crash_after_idempotency = crash_after_idempotency
        self.calls = 0

    async def execute(self, request: NodeExecutionRequest) -> NodeExecutionResult:
        self.calls += 1
        self.workspace.mkdir(parents=True, exist_ok=True)
        effect_path = self.workspace / "effect.txt"
        with effect_path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(f"effect:{request.run_id}\n")
        idempotency_key = f"IDEMP-{request.run_id}"
        result = NodeExecutionResult(
            node_run_id=request.run_id,
            plan_id=request.plan.plan_id,
            node_id=request.node.node_id,
            node_type=request.node.node_type,
            executor_release=self.release_ref,
            status=NodeExecutionStatus.ACCEPTED,
            artifact_refs=(f"file://{effect_path}",),
            evidence_refs=("EVD-effect-executor-result",),
            gate_refs=request.node.gate_refs,
            usage=NodeExecutionUsage(model_calls=1, tool_calls=1, spawned_nodes=0, cost_usd=0.0),
            message="effect committed",
            details={"idempotencyKey": idempotency_key},
        )
        node_run = self.store.get_node_run(request.run_id)
        self.store.record_idempotency_result(
            idempotency_key=idempotency_key,
            plan_execution_id=node_run.plan_execution_id,
            node_run_id=request.run_id,
            result=result,
        )
        if self.crash_after_idempotency:
            os._exit(97)
        return result


class PassingVerificationService:
    def select(self, trigger: VerificationTrigger) -> VerificationSelection:
        return VerificationSelection((), (), (), (), (), ("sqlite-recovery-fixture",))

    def complete(self, trigger: VerificationTrigger | None = None) -> CompletionGateResult:
        return CompletionGateResult(complete=True, current_claim_coverage=1.0)

    def defects(self) -> tuple[DefectRecord, ...]:
        return ()


def compiled_recovery_plan() -> tuple[PlanIR, PlanValidationReport]:
    draft = PlanDraft.from_mapping(
        {
            "apiVersion": "ahra.dev/v1alpha1",
            "kind": "PlanDraft",
            "metadata": {
                "goalId": GOAL_REF,
                "proposedBy": "sqlite-recovery-fixture@sha256:" + "a" * 64,
            },
            "spec": {
                "rationale": "TASK-0037 deterministic SQLite crash recovery fixture.",
                "nodes": [
                    {
                        "id": "NODE-effect",
                        "nodeType": "bounded_task",
                        "objective": "Commit one deterministic local side effect.",
                        "claimRefs": ["CLAIM-effect"],
                        "dependsOn": [],
                        "inputRefs": ["DOC-effect@" + canonical_fingerprint({"doc": "effect"})],
                        "expectedOutputs": [
                            {
                                "name": "effect-file",
                                "schemaRef": "ahra/artifact/local-file/0.1",
                                "consumerNodeRefs": ["NODE-goal"],
                                "artifactRequired": True,
                            }
                        ],
                        "capabilityRequests": [{"capability": "filesystem.write", "resources": ["effect.txt"]}],
                        "gateRefs": ["GATE-effect"],
                        "runtimeRef": RUNTIME_REF,
                        "budgetRequest": {
                            "maxModelCalls": 1,
                            "maxToolCalls": 2,
                            "maxSpawnedNodes": 0,
                            "maxWallSeconds": 30,
                            "maxCostUsd": 0.0,
                        },
                        "retryPolicy": {
                            "maxAttempts": 1,
                            "retryableFailureClasses": [],
                            "idempotencyKeyRequired": True,
                        },
                        "sideEffect": "idempotent",
                    },
                    {
                        "id": "NODE-goal",
                        "nodeType": "goal_verification",
                        "objective": "Verify the recovered side effect and Goal completion.",
                        "claimRefs": ["CLAIM-effect"],
                        "dependsOn": ["NODE-effect"],
                        "inputRefs": ["ART-effect@" + canonical_fingerprint({"node": "NODE-effect"})],
                        "expectedOutputs": [
                            {
                                "name": "goal-report",
                                "schemaRef": "ahra/verification-result/0.1",
                                "consumerNodeRefs": [],
                                "deliveryRole": "evidence",
                                "artifactRequired": True,
                            }
                        ],
                        "capabilityRequests": [],
                        "gateRefs": ["GATE-goal"],
                        "runtimeRef": RUNTIME_REF,
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
                        "sideEffect": "idempotent",
                        "terminalGoalVerification": True,
                    },
                ],
            },
        }
    )
    result = compile_plan_draft(draft, recovery_plan_config())
    if result.plan is None or not result.report.valid:
        raise RuntimeError("sqlite recovery fixture PlanDraft failed validation")
    return result.plan, result.report


def recovery_plan_config() -> PlanCompilerConfig:
    return PlanCompilerConfig(
        goal_ref=GOAL_REF,
        goal_digest=GOAL_DIGEST,
        claim_graph_digest=CLAIM_GRAPH_DIGEST,
        required_claim_refs=frozenset({"CLAIM-effect"}),
        registered_node_types={
            PlanNodeType.BOUNDED_TASK.value: NODE_TYPE_DIGEST,
            PlanNodeType.GOAL_VERIFICATION.value: GOAL_NODE_DIGEST,
        },
        registered_gate_refs={
            "GATE-effect": GATE_EFFECT_DIGEST,
            "GATE-goal": GATE_GOAL_DIGEST,
        },
        registered_runtime_refs={RUNTIME_REF: RUNTIME_DIGEST},
        allowed_capabilities=frozenset({"filesystem.write"}),
        default_runtime_ref=RUNTIME_REF,
        max_fan_out=2,
    )


def make_recovery_scheduler(
    *,
    service: PlanExecutionService,
    store: SQLiteControlStore,
    workspace: Path,
    crash_after_idempotency: bool = False,
) -> tuple[StaticPlanScheduler, DeterministicEffectExecutor, VerificationExecutor]:
    executor = DeterministicEffectExecutor(
        store=store,
        workspace=workspace,
        crash_after_idempotency=crash_after_idempotency,
    )
    registry = NodeExecutorRegistry()
    registry.register(executor)
    gate_registry = GateRunnerRegistry()
    gate_registry.register(DeterministicGateRunner())
    verification_executor = VerificationExecutor(gate_registry)
    scheduler = StaticPlanScheduler(
        service=service,
        executor_registry=registry,
        executor_release_refs={PlanNodeType.BOUNDED_TASK.value: EXECUTOR_RELEASE},
        verification_service=PassingVerificationService(),
        verification_executor=verification_executor,
        capability_admission=_capability_admission(),
        max_concurrency=1,
        lease_holder="scheduler:sqlite-recovery",
        lease_ttl_seconds=1,
    )
    return scheduler, executor, verification_executor


def create_recovery_execution(store: SQLiteControlStore, workspace: Path) -> tuple[PlanIR, str]:
    plan, report = compiled_recovery_plan()
    service = PlanExecutionService(store)
    goal = service.create_goal_execution(
        goal_ref=plan.goal_ref,
        goal_digest=plan.goal_digest,
        claim_graph_digest=plan.claim_graph_digest,
        goal_execution_id=GOAL_EXECUTION_ID,
        workspace_ref=str(workspace),
    )
    execution = service.start_execution(
        plan,
        report,
        goal_execution_ref=goal.goal_execution_id,
        task_ref="TASK-0037",
    )
    service.attach_plan_execution(
        goal.goal_execution_id,
        execution.plan_execution_id,
        expected_version=store.get_goal_execution(goal.goal_execution_id).status_version,
    )
    return plan, execution.plan_execution_id


def run_crash_after_idempotency(db_path: Path, workspace: Path) -> None:
    store = SQLiteControlStore(db_path)
    plan, plan_execution_id = create_recovery_execution(store, workspace)
    service = PlanExecutionService(store)
    scheduler, _executor, _verification_executor = make_recovery_scheduler(
        service=service,
        store=store,
        workspace=workspace,
        crash_after_idempotency=True,
    )
    asyncio.run(
        scheduler.run_ready_nodes_once(
            plan,
            plan_execution_id,
            workspace_ref=str(workspace),
            branch="task-0037",
        )
    )
    raise RuntimeError("crash-after-idempotency phase did not exit at the expected checkpoint")


def run_stop_after_terminal(db_path: Path, workspace: Path) -> None:
    store = SQLiteControlStore(db_path)
    plan, plan_execution_id = create_recovery_execution(store, workspace)
    service = PlanExecutionService(store)
    scheduler, _executor, _verification_executor = make_recovery_scheduler(
        service=service,
        store=store,
        workspace=workspace,
        crash_after_idempotency=False,
    )
    asyncio.run(
        scheduler.run_ready_nodes_once(
            plan,
            plan_execution_id,
            workspace_ref=str(workspace),
            branch="task-0037",
        )
    )
    os._exit(75)


def run_resume(db_path: Path, workspace: Path, report_path: Path) -> None:
    started = time.monotonic()
    store = SQLiteControlStore(db_path)
    recovery_report = recover_sqlite_control_plane(store, now=utc_now() + timedelta(hours=1))
    plan, _report = compiled_recovery_plan()
    executions = store.list_executions()
    if len(executions) != 1:
        raise RuntimeError(f"expected exactly one PlanExecution, found {len(executions)}")
    service = PlanExecutionService(store)
    scheduler, executor, verification_executor = make_recovery_scheduler(
        service=service,
        store=store,
        workspace=workspace,
        crash_after_idempotency=False,
    )
    final_execution = asyncio.run(
        scheduler.run_until_terminal(
            plan,
            executions[0].plan_execution_id,
            workspace_ref=str(workspace),
            branch="task-0037",
        )
    )
    goal = store.get_goal_execution(final_execution.goal_execution_ref or GOAL_EXECUTION_ID)
    if goal.active_plan_execution_ref == final_execution.plan_execution_id and final_execution.status.terminal:
        goal = service.finish_active_plan_execution(
            goal.goal_execution_id,
            final_execution.plan_execution_id,
            expected_version=goal.status_version,
        )
    if final_execution.status == PlanExecutionStatus.SUCCEEDED and goal.status == GoalExecutionStatus.VERIFYING:
        goal = service.complete_goal(
            goal.goal_execution_id,
            completion_complete=True,
            expected_version=goal.status_version,
            evidence_refs=final_execution.evidence_refs,
            artifact_refs=final_execution.artifact_refs,
        )

    final_execution = store.get_execution(final_execution.plan_execution_id)
    final_goal = store.get_goal_execution(goal.goal_execution_id)
    nodes = store.list_node_runs(final_execution.plan_execution_id)
    checkpoint = store.get_checkpoint(final_execution.checkpoint_ref or "")
    effect_lines = _effect_lines(workspace)
    payload: dict[str, Any] = {
        "schema_version": "ahra/sqlite-recovery-fixture-report/0.1",
        "task": "TASK-0037",
        "sqliteDb": str(db_path),
        "workspace": str(workspace),
        "planExecution": final_execution.to_dict(),
        "goalExecution": final_goal.to_dict(),
        "nodeRuns": [node.to_dict() for node in nodes],
        "checkpoint": checkpoint.to_dict(),
        "recoveryReport": recovery_report.to_dict(),
        "gateRunRefsInResumeProcess": [gate_run.gate_run_id for gate_run in verification_executor.gate_runs],
        "metrics": {
            "crashRecoverySucceeded": (
                final_execution.status == PlanExecutionStatus.SUCCEEDED
                and final_goal.status == GoalExecutionStatus.SUCCEEDED
            ),
            "resumeExecutorCallCount": executor.calls,
            "sideEffectLineCount": len(effect_lines),
            "duplicateEffectCount": max(0, len(effect_lines) - 1),
            "checkpointLoadSuccess": checkpoint.plan_execution_id == final_execution.plan_execution_id,
            "recoveryWallTimeSeconds": round(time.monotonic() - started, 6),
            "persistedEvidenceRefCount": len(set(final_execution.evidence_refs)),
            "persistedArtifactRefCount": len(set(final_execution.artifact_refs)),
        },
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _capability_admission() -> CapabilityAdmissionService:
    scope = CapabilityScope(
        allowed_actions={"filesystem.write": ("effect.txt",)},
        allowed_roles_by_action={"filesystem.write": ("executor",)},
    )
    return CapabilityAdmissionService(
        goal_scope=scope,
        policy_scope=scope,
        runtime_profile=RuntimeCapabilityProfile(
            runtime_ref=RUNTIME_REF,
            supported_actions=frozenset({"filesystem.write"}),
        ),
    )


def _effect_lines(workspace: Path) -> list[str]:
    path = workspace / "effect.txt"
    if not path.exists():
        return []
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TASK-0037 SQLite recovery fixture")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--phase", required=True, choices=("crash-after-idempotency", "stop-after-terminal", "resume"))
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    if args.phase == "crash-after-idempotency":
        run_crash_after_idempotency(args.db, args.workspace)
    elif args.phase == "stop-after-terminal":
        run_stop_after_terminal(args.db, args.workspace)
    elif args.phase == "resume":
        if args.report is None:
            parser.error("--report is required for resume")
        run_resume(args.db, args.workspace, args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
