from __future__ import annotations

import asyncio
import unittest
from dataclasses import replace
from datetime import timedelta

from ahra.evidence_v2 import canonical_fingerprint
from ahra.domain import utc_now
from ahra.node_executor import (
    NodeExecutionRequest,
    NodeExecutionResult,
    NodeExecutionStatus,
    NodeExecutionUsage,
    NodeExecutorRegistry,
)
from ahra.plan_execution import (
    InMemoryPlanExecutionStore,
    NodeRunStatus,
    PlanAdmissionError,
    PlanExecutionService,
    PlanExecutionStatus,
    PlanLeaseConflictError,
    PlanVersionConflictError,
    StaticPlanScheduler,
    project_awkp_task,
    reconcile_plan_execution,
)
from ahra.plan_ir import (
    PlanCompilerConfig,
    PlanDraft,
    PlanNodeType,
    PlanValidationError,
    compile_plan_draft,
)
from ahra.verification import CompletionGateResult, DefectRecord, VerificationSelection, VerificationTrigger


D1 = "sha256:" + "1" * 64
D2 = "sha256:" + "2" * 64
D3 = "sha256:" + "3" * 64
D4 = "sha256:" + "4" * 64
D5 = "sha256:" + "5" * 64
D6 = "sha256:" + "6" * 64
D7 = "sha256:" + "7" * 64
D8 = "sha256:" + "8" * 64
RUNTIME_REF = "runtime/local-worktree@sha256:" + "c" * 64
EXECUTOR_RELEASE = "bounded-task-executor@sha256:" + "a" * 64


class RecordingExecutor:
    node_type = PlanNodeType.BOUNDED_TASK.value
    release_ref = EXECUTOR_RELEASE

    def __init__(
        self,
        *,
        delay_seconds: float = 0.0,
        fail_once_for: str | None = None,
        failure_class: str = "transient_process_failure",
        usage: NodeExecutionUsage | None = None,
    ) -> None:
        self.delay_seconds = delay_seconds
        self.fail_once_for = fail_once_for
        self.failure_class = failure_class
        self.usage = usage or NodeExecutionUsage(model_calls=1, tool_calls=1, spawned_nodes=0, cost_usd=0.0)
        self.calls: list[str] = []
        self.active = 0
        self.max_active = 0
        self.failures: set[str] = set()

    async def execute(self, request: NodeExecutionRequest) -> NodeExecutionResult:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.delay_seconds:
                await asyncio.sleep(self.delay_seconds)
            self.calls.append(request.node.node_id)
            if request.node.node_id == self.fail_once_for and request.node.node_id not in self.failures:
                self.failures.add(request.node.node_id)
                return NodeExecutionResult(
                    node_run_id=request.run_id,
                    plan_id=request.plan.plan_id,
                    node_id=request.node.node_id,
                    node_type=request.node.node_type,
                    executor_release=self.release_ref,
                    status=NodeExecutionStatus.ERROR,
                    terminal_failure_refs=(f"FAIL-{request.node.node_id}",),
                    message="transient failure",
                    details={"failureClass": self.failure_class},
                )
            suffix = request.node.node_id.removeprefix("NODE-")
            return NodeExecutionResult(
                node_run_id=request.run_id,
                plan_id=request.plan.plan_id,
                node_id=request.node.node_id,
                node_type=request.node.node_type,
                executor_release=self.release_ref,
                status=NodeExecutionStatus.ACCEPTED,
                artifact_refs=(f"ART-{suffix}",),
                evidence_refs=(f"EVD-{suffix}",),
                gate_refs=request.node.gate_refs,
                usage=self.usage,
                message="accepted",
            )
        finally:
            self.active -= 1


class PassingVerificationService:
    def __init__(self) -> None:
        self.select_calls: list[VerificationTrigger] = []
        self.complete_calls: list[VerificationTrigger | None] = []

    def select(self, trigger: VerificationTrigger) -> VerificationSelection:
        self.select_calls.append(trigger)
        return VerificationSelection((), (), (), (), (), ("fixture",))

    def complete(self, trigger: VerificationTrigger | None = None) -> CompletionGateResult:
        self.complete_calls.append(trigger)
        return CompletionGateResult(complete=True)

    def defects(self) -> tuple[DefectRecord, ...]:
        return ()


class PlanExecutionTests(unittest.TestCase):
    def test_only_valid_immutable_plan_ir_can_start(self) -> None:
        plan, report = _compiled_plan()
        service = PlanExecutionService(InMemoryPlanExecutionStore())

        bad_report = replace(
            report,
            errors=(PlanValidationError("forced-failure", "forced failure", "PlanIR"),),
        )
        with self.assertRaisesRegex(PlanAdmissionError, "passing validation report"):
            service.start_execution(plan, bad_report)

        mismatched = replace(report, subject_digest=D8)
        with self.assertRaisesRegex(PlanAdmissionError, "digest does not match"):
            service.start_execution(plan, mismatched)

        execution = service.start_execution(plan, report, task_ref="TASK-0029")
        self.assertEqual(execution.status, PlanExecutionStatus.ADMITTED)
        self.assertEqual(execution.task_ref, "TASK-0029")
        self.assertEqual(execution.plan_digest, plan.digest())

    def test_static_scheduler_enforces_dag_concurrency_and_goal_gate(self) -> None:
        plan, report = _compiled_plan()
        service = PlanExecutionService(InMemoryPlanExecutionStore())
        executor = RecordingExecutor(delay_seconds=0.01)
        verifier = PassingVerificationService()
        scheduler = _scheduler(service, executor, verifier, max_concurrency=1)
        execution_id = scheduler.submit_plan(plan, report)

        result = asyncio.run(
            scheduler.run_until_terminal(
                plan,
                execution_id,
                workspace_ref="workspace://fixture",
                branch="task-0029",
            )
        )

        self.assertEqual(result.status, PlanExecutionStatus.SUCCEEDED)
        self.assertLessEqual(executor.max_active, 1)
        self.assertEqual(executor.calls, ["NODE-a", "NODE-b"])
        self.assertGreaterEqual(len(verifier.select_calls), 2)
        self.assertEqual(len(verifier.complete_calls), 1)
        self.assertEqual(set(result.artifact_refs), {"ART-a", "ART-b"})
        self.assertTrue({"EVD-a", "EVD-b", "EVD-goal"}.issubset(set(result.evidence_refs)))
        self.assertTrue(result.trace_refs)
        self.assertTrue(result.handoff_refs)

    def test_plan_deadline_stops_scheduling_before_node_execution(self) -> None:
        plan, report = _compiled_plan()
        service = PlanExecutionService(InMemoryPlanExecutionStore())
        executor = RecordingExecutor()
        verifier = PassingVerificationService()
        execution = service.start_execution(
            plan,
            report,
            deadline_at=utc_now() - timedelta(seconds=1),
        )
        scheduler = _scheduler(service, executor, verifier, max_concurrency=1)

        result = asyncio.run(
            scheduler.run_until_terminal(
                plan,
                execution.plan_execution_id,
                workspace_ref="workspace://fixture",
                branch="task-0029",
            )
        )

        self.assertEqual(result.status, PlanExecutionStatus.FAILED)
        self.assertEqual(result.failure_class, "deadline_exceeded")
        self.assertEqual(executor.calls, [])

    def test_budget_snapshots_and_wall_budget_are_enforced(self) -> None:
        plan, report = _compiled_plan(timeout_seconds=None, max_wall_seconds=1)
        service = PlanExecutionService(InMemoryPlanExecutionStore())
        executor = RecordingExecutor(delay_seconds=1.2)
        scheduler = _scheduler(service, executor, PassingVerificationService(), max_concurrency=2)
        execution_id = scheduler.submit_plan(plan, report)

        admitted = service.store.get_execution(execution_id)
        self.assertEqual(admitted.budget_summary["maxWallSeconds"], 3)
        first_node = service.store.list_node_runs(execution_id)[0]
        self.assertEqual(first_node.budget["maxWallSeconds"], 1)

        result = asyncio.run(
            scheduler.run_until_terminal(
                plan,
                execution_id,
                workspace_ref="workspace://fixture",
                branch="task-0029",
            )
        )
        latest = {node.node_id: node for node in service.store.list_node_runs(execution_id)}
        checkpoint_id = result.checkpoint_ref.removeprefix("checkpoint://") if result.checkpoint_ref else ""
        checkpoint = service.store.get_checkpoint(checkpoint_id)

        self.assertEqual(result.status, PlanExecutionStatus.FAILED)
        self.assertEqual(result.failure_class, "timeout")
        self.assertEqual(latest["NODE-a"].status, NodeRunStatus.TIMED_OUT)
        self.assertEqual(checkpoint.node_budgets[latest["NODE-a"].node_run_id]["maxWallSeconds"], 1)

    def test_usage_budget_overrun_fails_node_and_plan(self) -> None:
        plan, report = _compiled_plan(max_cost_usd=0.01)
        service = PlanExecutionService(InMemoryPlanExecutionStore())
        executor = RecordingExecutor(
            usage=NodeExecutionUsage(model_calls=2, tool_calls=3, spawned_nodes=1, cost_usd=0.02)
        )
        scheduler = _scheduler(service, executor, PassingVerificationService(), max_concurrency=1)
        execution_id = scheduler.submit_plan(plan, report)

        result = asyncio.run(
            scheduler.run_until_terminal(
                plan,
                execution_id,
                workspace_ref="workspace://fixture",
                branch="task-0029",
            )
        )
        node_a = [node for node in service.store.list_node_runs(execution_id) if node.node_id == "NODE-a"][0]

        self.assertEqual(result.status, PlanExecutionStatus.FAILED)
        self.assertEqual(result.failure_class, "budget_exceeded")
        self.assertEqual(node_a.status, NodeRunStatus.FAILED)
        self.assertEqual(node_a.failure_class, "budget_exceeded")
        self.assertEqual(node_a.usage["modelCalls"], 2)
        self.assertIn("maxModelCalls", node_a.message)
        self.assertIn("maxToolCalls", node_a.message)
        self.assertIn("maxSpawnedNodes", node_a.message)
        self.assertIn("maxCostUsd", node_a.message)

    def test_declared_verification_boundaries_fail_closed_without_verifier(self) -> None:
        plan, report = _compiled_plan()
        service = PlanExecutionService(InMemoryPlanExecutionStore())
        executor = RecordingExecutor()
        scheduler = _scheduler(service, executor, None, max_concurrency=1)
        execution_id = scheduler.submit_plan(plan, report)

        result = asyncio.run(
            scheduler.run_until_terminal(
                plan,
                execution_id,
                workspace_ref="workspace://fixture",
                branch="task-0029",
            )
        )
        latest = {node.node_id: node for node in service.store.list_node_runs(execution_id)}

        self.assertEqual(result.status, PlanExecutionStatus.FAILED)
        self.assertEqual(result.failure_class, "verification_service_unavailable")
        self.assertEqual(latest["NODE-a"].status, NodeRunStatus.FAILED)
        self.assertEqual(latest["NODE-a"].failure_class, "verification_service_unavailable")
        self.assertNotIn("EVD-goal", result.evidence_refs)

    def test_resume_skips_completed_idempotent_nodes(self) -> None:
        plan, report = _compiled_plan()
        service = PlanExecutionService(InMemoryPlanExecutionStore())
        executor = RecordingExecutor()
        scheduler = _scheduler(service, executor, PassingVerificationService(), max_concurrency=1)
        execution_id = scheduler.submit_plan(plan, report)

        ran = asyncio.run(
            scheduler.run_ready_nodes_once(
                plan,
                execution_id,
                workspace_ref="workspace://fixture",
                branch="task-0029",
            )
        )
        self.assertTrue(ran)
        self.assertEqual(executor.calls, ["NODE-a"])

        resumed = _scheduler(service, executor, PassingVerificationService(), max_concurrency=1)
        result = asyncio.run(
            resumed.run_until_terminal(
                plan,
                execution_id,
                workspace_ref="workspace://fixture",
                branch="task-0029",
            )
        )

        self.assertEqual(result.status, PlanExecutionStatus.SUCCEEDED)
        self.assertEqual(executor.calls.count("NODE-a"), 1)
        self.assertEqual(executor.calls.count("NODE-b"), 1)

    def test_retry_creates_new_node_run_attempt_without_repeating_dependencies(self) -> None:
        plan, report = _compiled_plan(retry_node_a=True)
        service = PlanExecutionService(InMemoryPlanExecutionStore())
        executor = RecordingExecutor(fail_once_for="NODE-a")
        scheduler = _scheduler(service, executor, PassingVerificationService(), max_concurrency=1)
        execution_id = scheduler.submit_plan(plan, report)

        result = asyncio.run(
            scheduler.run_until_terminal(
                plan,
                execution_id,
                workspace_ref="workspace://fixture",
                branch="task-0029",
            )
        )

        node_a_runs = [
            node for node in service.store.list_node_runs(execution_id) if node.node_id == "NODE-a"
        ]
        self.assertEqual(result.status, PlanExecutionStatus.SUCCEEDED)
        self.assertEqual([node.attempt for node in node_a_runs], [1, 2])
        self.assertEqual(executor.calls.count("NODE-a"), 2)
        self.assertEqual(executor.calls.count("NODE-b"), 1)

    def test_stale_expected_version_and_fencing_token_are_rejected(self) -> None:
        plan, report = _compiled_plan()
        service = PlanExecutionService(InMemoryPlanExecutionStore())
        execution = service.start_execution(plan, report)
        node = service.store.list_node_runs(execution.plan_execution_id)[0]
        leased = service.acquire_node_lease(
            node.node_run_id,
            holder="worker:one",
            ttl_seconds=60,
            expected_version=node.status_version,
        )

        with self.assertRaisesRegex(PlanLeaseConflictError, "fencing"):
            service.transition_node(
                leased.node_run_id,
                NodeRunStatus.READY,
                expected_version=leased.status_version,
                holder="worker:one",
                fencing_token=999,
            )
        with self.assertRaises(PlanVersionConflictError):
            service.transition_node(
                leased.node_run_id,
                NodeRunStatus.READY,
                expected_version=0,
                holder="worker:one",
                fencing_token=leased.lease.fencing_token if leased.lease else 1,
            )

    def test_cancellation_propagates_to_active_and_pending_nodes(self) -> None:
        plan, report = _compiled_plan()
        service = PlanExecutionService(InMemoryPlanExecutionStore())
        execution = service.start_execution(plan, report)
        execution = service.transition_execution(
            execution.plan_execution_id,
            PlanExecutionStatus.RUNNING,
            expected_version=service.store.get_execution(execution.plan_execution_id).status_version,
        )
        node = service.store.list_node_runs(execution.plan_execution_id)[0]
        node = service.transition_node(node.node_run_id, NodeRunStatus.READY, expected_version=node.status_version)
        node = service.transition_node(node.node_run_id, NodeRunStatus.ADMITTED, expected_version=node.status_version)
        node = service.acquire_node_lease(
            node.node_run_id,
            holder="worker:one",
            ttl_seconds=60,
            expected_version=node.status_version,
        )
        service.transition_node(
            node.node_run_id,
            NodeRunStatus.RUNNING,
            expected_version=node.status_version,
            holder="worker:one",
            fencing_token=node.lease.fencing_token if node.lease else 1,
        )

        current = service.store.get_execution(execution.plan_execution_id)
        canceled = service.cancel_execution(
            execution.plan_execution_id,
            expected_version=current.status_version,
            reason="test cancellation",
        )

        self.assertEqual(canceled.status, PlanExecutionStatus.CANCELED)
        self.assertTrue(canceled.handoff_refs)
        self.assertTrue(
            all(
                node.status == NodeRunStatus.CANCELED
                for node in service.store.list_node_runs(execution.plan_execution_id)
            )
        )

    def test_projection_and_reconciler_keep_authorities_distinct(self) -> None:
        plan, report = _compiled_plan()
        service = PlanExecutionService(InMemoryPlanExecutionStore())
        execution = service.start_execution(plan, report, task_ref="TASK-0029")
        projection = project_awkp_task(execution, task_id="TASK-0029")

        self.assertEqual(projection.authority_refs["task"], "TASK-0029")
        self.assertEqual(projection.authority_refs["goal"], plan.goal_ref)
        self.assertEqual(projection.authority_refs["planExecution"], execution.plan_execution_id)
        self.assertNotEqual(projection.authority_refs["task"], projection.authority_refs["planExecution"])

        node = service.store.list_node_runs(execution.plan_execution_id)[0]
        old_now = execution.created_at
        leased = service.acquire_node_lease(
            node.node_run_id,
            holder="worker:one",
            ttl_seconds=1,
            expected_version=node.status_version,
            now=old_now,
        )
        findings = reconcile_plan_execution(
            execution,
            (leased,),
            task_projection={"task_id": "TASK-0029", "state": "completed"},
            now=old_now + timedelta(seconds=2),
        )

        codes = {finding.code for finding in findings}
        self.assertIn("expired-node-lease", codes)
        self.assertIn("inconsistent-task-projection", codes)


def _scheduler(
    service: PlanExecutionService,
    executor: RecordingExecutor,
    verifier: PassingVerificationService | None,
    *,
    max_concurrency: int,
) -> StaticPlanScheduler:
    registry = NodeExecutorRegistry()
    registry.register(executor)
    return StaticPlanScheduler(
        service=service,
        executor_registry=registry,
        executor_release_refs={PlanNodeType.BOUNDED_TASK.value: executor.release_ref},
        verification_service=verifier,
        max_concurrency=max_concurrency,
    )


def _compiled_plan(
    *,
    retry_node_a: bool = False,
    timeout_seconds: int | None = 30,
    max_wall_seconds: int = 30,
    max_cost_usd: float = 0.01,
):
    draft = PlanDraft.from_mapping(
        _draft_mapping(
            retry_node_a=retry_node_a,
            timeout_seconds=timeout_seconds,
            max_wall_seconds=max_wall_seconds,
            max_cost_usd=max_cost_usd,
        )
    )
    result = compile_plan_draft(draft, _config())
    assert result.plan is not None, [error.to_dict() for error in result.report.errors]
    assert result.report.valid, [error.to_dict() for error in result.report.errors]
    return result.plan, result.report


def _config() -> PlanCompilerConfig:
    return PlanCompilerConfig(
        goal_ref="GOAL-static-plan-execution",
        goal_digest=D1,
        claim_graph_digest=D2,
        required_claim_refs=frozenset({"CLAIM-a", "CLAIM-b"}),
        registered_node_types={
            "bounded_task": D3,
            "gate_verification": D4,
            "goal_verification": D5,
            "repair": D6,
        },
        registered_gate_refs={
            "GATE-node-a": D3,
            "GATE-node-b": D4,
            "GATE-goal": D5,
        },
        registered_runtime_refs={RUNTIME_REF: D7},
        allowed_capabilities=frozenset({"filesystem.write"}),
        default_runtime_ref=RUNTIME_REF,
        max_fan_out=4,
    )


def _draft_mapping(
    *,
    retry_node_a: bool,
    timeout_seconds: int | None,
    max_wall_seconds: int,
    max_cost_usd: float,
) -> dict:
    goal_node = {
        "id": "NODE-goal",
        "nodeType": "goal_verification",
        "objective": "Verify the static PlanIR goal completion gate.",
        "claimRefs": ["CLAIM-a", "CLAIM-b"],
        "dependsOn": ["NODE-a", "NODE-b"],
        "inputRefs": ["ART-a@sha256:" + "d" * 64, "ART-b@sha256:" + "e" * 64],
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
            "maxWallSeconds": max_wall_seconds,
            "maxCostUsd": max_cost_usd,
        },
        "retryPolicy": {
            "maxAttempts": 1,
            "retryableFailureClasses": [],
            "idempotencyKeyRequired": False,
        },
        "sideEffect": "idempotent",
        "terminalGoalVerification": True,
    }
    if timeout_seconds is not None:
        goal_node["timeoutSeconds"] = timeout_seconds
    return {
        "apiVersion": "ahra.dev/v1alpha1",
        "kind": "PlanDraft",
        "metadata": {
            "goalId": "GOAL-static-plan-execution",
            "proposedBy": "REL-static-fixture@sha256:" + "b" * 64,
        },
        "spec": {
            "rationale": "Fixture for static PlanIR DAG execution.",
            "nodes": [
                _bounded_node(
                    "NODE-a",
                    "CLAIM-a",
                    "GATE-node-a",
                    retry=retry_node_a,
                    timeout_seconds=timeout_seconds,
                    max_wall_seconds=max_wall_seconds,
                    max_cost_usd=max_cost_usd,
                ),
                _bounded_node(
                    "NODE-b",
                    "CLAIM-b",
                    "GATE-node-b",
                    retry=False,
                    timeout_seconds=timeout_seconds,
                    max_wall_seconds=max_wall_seconds,
                    max_cost_usd=max_cost_usd,
                ),
                goal_node,
            ],
        },
    }


def _bounded_node(
    node_id: str,
    claim_ref: str,
    gate_ref: str,
    *,
    retry: bool,
    timeout_seconds: int | None,
    max_wall_seconds: int,
    max_cost_usd: float,
) -> dict:
    name = node_id.removeprefix("NODE-")
    retry_policy = {
        "maxAttempts": 2 if retry else 1,
        "retryableFailureClasses": ["transient_process_failure"] if retry else [],
        "idempotencyKeyRequired": retry,
    }
    node = {
        "id": node_id,
        "nodeType": "bounded_task",
        "objective": f"Produce artifact {name}.",
        "claimRefs": [claim_ref],
        "dependsOn": [],
        "inputRefs": [f"DOC-{name}@{canonical_fingerprint({'node': node_id})}"],
        "expectedOutputs": [
            {
                "name": f"{name}-artifact",
                "schemaRef": "ahra/artifact/code-change/0.1",
                "consumerNodeRefs": ["NODE-goal"],
                "artifactRequired": True,
            }
        ],
        "capabilityRequests": [{"capability": "filesystem.write", "resources": [f"{name}.txt"]}],
        "gateRefs": [gate_ref],
        "runtimeRef": RUNTIME_REF,
        "budgetRequest": {
            "maxModelCalls": 1,
            "maxToolCalls": 2,
            "maxSpawnedNodes": 0,
            "maxWallSeconds": max_wall_seconds,
            "maxCostUsd": max_cost_usd,
        },
        "retryPolicy": retry_policy,
        "sideEffect": "idempotent",
    }
    if timeout_seconds is not None:
        node["timeoutSeconds"] = timeout_seconds
    return node


if __name__ == "__main__":
    unittest.main()
