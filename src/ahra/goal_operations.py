from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Mapping

import yaml

from .capabilities import CapabilityAdmissionService, CapabilityScope, LocalRuntimeGateway, RuntimeCapabilityProfile
from .acceptance_contracts import Claim, ClaimGraph, ClaimType, RiskLevel
from .domain import utc_now
from .evidence_v2 import EvidenceEnvironment, EvidenceV2, canonical_fingerprint
from .node_executor import (
    NodeExecutionRequest,
    NodeExecutionResult,
    NodeExecutionStatus,
    NodeExecutionUsage,
    NodeExecutorRegistry,
)
from .plan_execution import (
    GoalExecutionStatus,
    GOAL_TRANSITIONS,
    NodeRunStatus,
    PlanExecutionRecord,
    PlanExecutionService,
    PlanExecutionStatus,
    PlanInvalidTransitionError,
    StaticPlanScheduler,
)
from .plan_ir import PlanCompilerConfig, PlanDraft, PlanIR, PlanValidationReport, compile_plan_draft
from .sqlite_control_store import SQLiteControlStore, recover_sqlite_control_plane
from .verification import (
    CompletionGateResult,
    DeterministicGateRunner,
    GateRunnerRegistry,
    VerificationExecutor,
    VerificationSelection,
    VerificationTrigger,
    evaluate_completion,
)

if TYPE_CHECKING:
    from .ports import AgentDriver


GOAL_OPERATION_SCHEMA_VERSION = "ahra/goal-operation/0.1"
M1_PROFILE_REF = "profile/m1-deterministic@sha256:" + "a" * 64
M1_REAL_PLANNER_PROFILE_REF = "profile/m1-real-planner@sha256:" + "f" * 64
M1_REAL_EXECUTOR_PROFILE_REF = "profile/m1-real-executor@sha256:" + "9" * 64
M1_REAL_COMBINED_PROFILE_REF = "profile/m1-real-combined@sha256:" + "8" * 64
INLINE_PLANNER_REF = "planner/inline-plan-draft@sha256:" + "b" * 64
REAL_PLANNER_ADAPTER_REF = "planner/agent-driver-plan-draft@sha256:" + "7" * 64
DETERMINISTIC_EXECUTOR_REF = "executor/deterministic-file-effect@sha256:" + "c" * 64
REAL_BOUNDED_EXECUTOR_REF = "executor/bounded-task-agent-driver@sha256:" + "6" * 64
DETERMINISTIC_GATE_RUNNER_REF = "gate-runner/deterministic@sha256:" + "d" * 64
LOCAL_GOAL_RUNTIME_REF = "runtime/local-goal@sha256:" + "e" * 64
LOCAL_GOAL_RUNTIME_DIGEST = "sha256:" + "e" * 64


class GoalOperationError(RuntimeError):
    def __init__(self, code: str, message: str, *, refs: tuple[str, ...] = ()) -> None:
        self.code = code
        self.message = message
        self.refs = refs
        super().__init__(f"{code}: {message}")

    def to_error_dict(self) -> dict[str, Any]:
        return {"code": self.code, "error": self.message, "refs": list(self.refs)}


@dataclass(frozen=True, slots=True)
class GoalOperationProfile:
    profile_ref: str
    planner_adapter_ref: str
    executor_adapter_ref: str
    gate_runner_adapter_ref: str
    runtime_ref: str
    runtime_digest: str
    store_kinds: frozenset[str]
    executable_node_types: frozenset[str]
    scheduler_node_types: frozenset[str]

    @property
    def registered_node_types(self) -> frozenset[str]:
        return self.executable_node_types | self.scheduler_node_types


@dataclass(frozen=True, slots=True)
class GoalExecutionRequest:
    name: str
    request_id: str
    idempotency_key: str
    profile_ref: str
    workspace_ref: Path
    artifact_dir: Path
    store_kind: str
    store_path: Path
    planner_adapter_ref: str
    executor_adapter_ref: str
    gate_runner_adapter_ref: str
    runtime_ref: str
    runtime_digest: str
    goal_ref: str
    goal_digest: str
    claim_graph_digest: str
    claim_graph_ref: str | None
    required_claim_refs: tuple[str, ...]
    registered_node_types: Mapping[str, str]
    registered_gate_refs: Mapping[str, str]
    registered_runtime_refs: Mapping[str, str]
    allowed_capabilities: tuple[str, ...]
    plan_draft: PlanDraft
    max_repair_cycles: int
    max_concurrency: int
    branch: str

    @property
    def goal_execution_id(self) -> str:
        return "GEXEC-" + canonical_fingerprint(
            {
                "idempotencyKey": self.idempotency_key,
                "goalRef": self.goal_ref,
                "goalDigest": self.goal_digest,
                "profileRef": self.profile_ref,
            }
        ).removeprefix("sha256:")[:16]

    def compiler_config(self) -> PlanCompilerConfig:
        return PlanCompilerConfig(
            goal_ref=self.goal_ref,
            goal_digest=self.goal_digest,
            claim_graph_digest=self.claim_graph_digest,
            required_claim_refs=frozenset(self.required_claim_refs),
            registered_node_types=dict(self.registered_node_types),
            registered_gate_refs=dict(self.registered_gate_refs),
            registered_runtime_refs=dict(self.registered_runtime_refs),
            allowed_capabilities=frozenset(self.allowed_capabilities),
            default_runtime_ref=self.runtime_ref,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "apiVersion": "ahra.dev/v1alpha1",
            "kind": "GoalExecutionRequest",
            "metadata": {
                "name": self.name,
                "requestId": self.request_id,
                "idempotencyKey": self.idempotency_key,
            },
            "spec": {
                "profileRef": self.profile_ref,
                "workspaceRef": str(self.workspace_ref),
                "artifactDir": str(self.artifact_dir),
                "store": {"kind": self.store_kind, "path": str(self.store_path)},
                "planner": {"adapterRef": self.planner_adapter_ref},
                "executor": {"adapterRef": self.executor_adapter_ref},
                "gateRunner": {"adapterRef": self.gate_runner_adapter_ref},
                "runtime": {"runtimeRef": self.runtime_ref, "digest": self.runtime_digest},
                "goal": {
                    "goalRef": self.goal_ref,
                    "goalDigest": self.goal_digest,
                    "claimGraphRef": self.claim_graph_ref,
                    "claimGraphDigest": self.claim_graph_digest,
                    "requiredClaimRefs": list(self.required_claim_refs),
                },
                "registry": {
                    "nodeTypes": dict(sorted(self.registered_node_types.items())),
                    "gateRefs": dict(sorted(self.registered_gate_refs.items())),
                    "runtimeRefs": dict(sorted(self.registered_runtime_refs.items())),
                    "allowedCapabilities": list(self.allowed_capabilities),
                },
                "execution": {
                    "maxRepairCycles": self.max_repair_cycles,
                    "maxConcurrency": self.max_concurrency,
                    "branch": self.branch,
                },
                "planDraft": self.plan_draft.to_dict(),
            },
        }


@dataclass(frozen=True, slots=True)
class GoalPlanBundle:
    request: GoalExecutionRequest
    plan: PlanIR | None
    validation_report: PlanValidationReport

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "ahra/goal-plan-bundle/0.1",
            "request": self.request.to_dict(),
            "planDraft": self.request.plan_draft.to_dict(),
            "planValidationReport": self.validation_report.to_dict(),
            "planIR": self.plan.to_dict() if self.plan else None,
        }


class GoalOperationProfileRegistry:
    def __init__(self, profiles: tuple[GoalOperationProfile, ...] | None = None) -> None:
        default_profiles = profiles or (
            GoalOperationProfile(
                profile_ref=M1_PROFILE_REF,
                planner_adapter_ref=INLINE_PLANNER_REF,
                executor_adapter_ref=DETERMINISTIC_EXECUTOR_REF,
                gate_runner_adapter_ref=DETERMINISTIC_GATE_RUNNER_REF,
                runtime_ref=LOCAL_GOAL_RUNTIME_REF,
                runtime_digest=LOCAL_GOAL_RUNTIME_DIGEST,
                store_kinds=frozenset({"sqlite"}),
                executable_node_types=frozenset({"bounded_task", "repair"}),
                scheduler_node_types=frozenset({"goal_verification", "gate_verification"}),
            ),
            GoalOperationProfile(
                profile_ref=M1_REAL_PLANNER_PROFILE_REF,
                planner_adapter_ref=REAL_PLANNER_ADAPTER_REF,
                executor_adapter_ref=DETERMINISTIC_EXECUTOR_REF,
                gate_runner_adapter_ref=DETERMINISTIC_GATE_RUNNER_REF,
                runtime_ref=LOCAL_GOAL_RUNTIME_REF,
                runtime_digest=LOCAL_GOAL_RUNTIME_DIGEST,
                store_kinds=frozenset({"sqlite"}),
                executable_node_types=frozenset({"bounded_task", "repair"}),
                scheduler_node_types=frozenset({"goal_verification", "gate_verification"}),
            ),
            GoalOperationProfile(
                profile_ref=M1_REAL_EXECUTOR_PROFILE_REF,
                planner_adapter_ref=INLINE_PLANNER_REF,
                executor_adapter_ref=REAL_BOUNDED_EXECUTOR_REF,
                gate_runner_adapter_ref=DETERMINISTIC_GATE_RUNNER_REF,
                runtime_ref=LOCAL_GOAL_RUNTIME_REF,
                runtime_digest=LOCAL_GOAL_RUNTIME_DIGEST,
                store_kinds=frozenset({"sqlite"}),
                executable_node_types=frozenset({"bounded_task", "repair"}),
                scheduler_node_types=frozenset({"goal_verification", "gate_verification"}),
            ),
            GoalOperationProfile(
                profile_ref=M1_REAL_COMBINED_PROFILE_REF,
                planner_adapter_ref=REAL_PLANNER_ADAPTER_REF,
                executor_adapter_ref=REAL_BOUNDED_EXECUTOR_REF,
                gate_runner_adapter_ref=DETERMINISTIC_GATE_RUNNER_REF,
                runtime_ref=LOCAL_GOAL_RUNTIME_REF,
                runtime_digest=LOCAL_GOAL_RUNTIME_DIGEST,
                store_kinds=frozenset({"sqlite"}),
                executable_node_types=frozenset({"bounded_task", "repair"}),
                scheduler_node_types=frozenset({"goal_verification", "gate_verification"}),
            ),
        )
        self._profiles = {profile.profile_ref: profile for profile in default_profiles}

    def get(self, profile_ref: str) -> GoalOperationProfile:
        if _looks_like_legacy_profile(profile_ref):
            raise GoalOperationError(
                "legacy_profile_not_default",
                "legacy workflow profile refs are compatibility-only and cannot be used as the default Goal operation path",
                refs=(profile_ref,),
            )
        try:
            return self._profiles[profile_ref]
        except KeyError as exc:
            raise GoalOperationError("unknown_profile", f"unknown Goal operation profile: {profile_ref}", refs=(profile_ref,)) from exc


class GoalOperationService:
    def __init__(
        self,
        profiles: GoalOperationProfileRegistry | None = None,
        *,
        real_executor_driver: "AgentDriver | None" = None,
        real_executor_store_dir: Path | str | None = None,
        real_executor_workspace_provider: Any | None = None,
        real_executor_runtime_provider: Any | None = None,
        real_executor_runtime_profile_ref: str | None = None,
        real_executor_execution_policy: Any | None = None,
    ) -> None:
        self.profiles = profiles or GoalOperationProfileRegistry()
        self.real_executor_driver = real_executor_driver
        self.real_executor_store_dir = Path(real_executor_store_dir) if real_executor_store_dir else None
        self.real_executor_workspace_provider = real_executor_workspace_provider
        self.real_executor_runtime_provider = real_executor_runtime_provider
        self.real_executor_runtime_profile_ref = real_executor_runtime_profile_ref
        self.real_executor_execution_policy = real_executor_execution_policy

    def validate(self, request_path: Path | str) -> dict[str, Any]:
        bundle = self.plan_bundle(request_path)
        return {
            "schema_version": "ahra/goal-operation-validation/0.1",
            "valid": bundle.validation_report.valid,
            "goalExecutionId": bundle.request.goal_execution_id,
            "profileRef": bundle.request.profile_ref,
            "plannerAdapterRef": bundle.request.planner_adapter_ref,
            "executorAdapterRef": bundle.request.executor_adapter_ref,
            "gateRunnerAdapterRef": bundle.request.gate_runner_adapter_ref,
            "planValidationReport": bundle.validation_report.to_dict(),
            "metrics": _plan_metrics(bundle.plan),
        }

    def plan(self, request_path: Path | str) -> dict[str, Any]:
        bundle = self._require_admitted_plan(request_path)
        bundle.request.artifact_dir.mkdir(parents=True, exist_ok=True)
        _write_json(bundle.request.artifact_dir / "goal-execution-request.json", bundle.request.to_dict())
        _write_json(bundle.request.artifact_dir / "plan-draft.json", bundle.request.plan_draft.to_dict())
        _write_json(bundle.request.artifact_dir / "plan-validation-report.json", bundle.validation_report.to_dict())
        assert bundle.plan is not None
        _write_json(bundle.request.artifact_dir / "plan-ir.json", bundle.plan.to_dict())
        return {
            "schema_version": "ahra/goal-operation-plan/0.1",
            "goalExecutionId": bundle.request.goal_execution_id,
            "artifactDir": str(bundle.request.artifact_dir),
            "planId": bundle.plan.plan_id,
            "planDigest": bundle.plan.digest(),
            "executedNodeCount": 0,
            "metrics": _plan_metrics(bundle.plan),
        }

    def start(self, request_path: Path | str, *, run_once: bool = False) -> dict[str, Any]:
        bundle = self._require_admitted_plan(request_path)
        request = bundle.request
        self._ensure_runtime_dependencies(request)
        request.artifact_dir.mkdir(parents=True, exist_ok=True)
        request.workspace_ref.mkdir(parents=True, exist_ok=True)
        self.plan(request_path)
        store = SQLiteControlStore(request.store_path)
        service = PlanExecutionService(store)  # type: ignore[arg-type]
        if _goal_exists(store, request.goal_execution_id):
            raise GoalOperationError(
                "duplicate_start_idempotency_key",
                "GoalExecution already exists for this idempotency key",
                refs=(request.goal_execution_id, request.idempotency_key),
            )
        goal = service.create_goal_execution(
            goal_ref=request.goal_ref,
            goal_digest=request.goal_digest,
            claim_graph_digest=request.claim_graph_digest,
            claim_graph_ref=request.claim_graph_ref,
            goal_execution_id=request.goal_execution_id,
            max_repair_cycles=request.max_repair_cycles,
            budget_summary={"profileRef": request.profile_ref},
            workspace_ref=str(request.workspace_ref),
        )
        assert bundle.plan is not None
        execution = service.start_execution(
            bundle.plan,
            bundle.validation_report,
            goal_execution_ref=goal.goal_execution_id,
            max_concurrency=request.max_concurrency,
        )
        service.attach_plan_execution(
            goal.goal_execution_id,
            execution.plan_execution_id,
            expected_version=goal.status_version,
        )
        scheduler = self._scheduler(request, store)
        if run_once:
            ran = asyncio.run(
                scheduler.run_ready_nodes_once(
                    bundle.plan,
                    execution.plan_execution_id,
                    workspace_ref=str(request.workspace_ref),
                    branch=request.branch,
                )
            )
            latest_execution = store.get_execution(execution.plan_execution_id)
            latest_goal = store.get_goal_execution(goal.goal_execution_id)
        else:
            latest_execution = asyncio.run(
                scheduler.run_until_terminal(
                    bundle.plan,
                    execution.plan_execution_id,
                    workspace_ref=str(request.workspace_ref),
                    branch=request.branch,
                )
            )
            latest_goal = self._finish_goal_if_ready(
                service,
                goal.goal_execution_id,
                latest_execution.plan_execution_id,
                completion=_scheduler_completion(scheduler),
            )
            ran = True
        result = self.inspect(goal.goal_execution_id, db_path=request.store_path)
        report = {
            "schema_version": "ahra/goal-operation-start/0.1",
            "goalExecutionId": goal.goal_execution_id,
            "planExecutionId": execution.plan_execution_id,
            "ranReadyNodes": ran,
            "runOnce": run_once,
            "goalStatus": latest_goal.status.value,
            "planStatus": latest_execution.status.value,
            "inspect": result,
        }
        _write_json(request.artifact_dir / "goal-start-report.json", report)
        return report

    def resume(self, goal_execution_id: str, *, request_path: Path | str) -> dict[str, Any]:
        bundle = self._require_admitted_plan(request_path)
        request = bundle.request
        self._ensure_runtime_dependencies(request)
        if request.goal_execution_id != goal_execution_id:
            raise GoalOperationError(
                "goal_execution_request_mismatch",
                "request idempotency key does not match the requested durable GoalExecution id",
                refs=(goal_execution_id, request.goal_execution_id),
            )
        store = self._existing_store(request.store_path)
        service = PlanExecutionService(store)  # type: ignore[arg-type]
        goal = store.get_goal_execution(goal_execution_id)
        if goal.status.terminal:
            return {
                "schema_version": "ahra/goal-operation-resume/0.1",
                "goalExecutionId": goal_execution_id,
                "alreadyTerminal": True,
                "goalStatus": goal.status.value,
                "inspect": self.inspect(goal_execution_id, db_path=request.store_path),
            }
        if not goal.active_plan_execution_ref:
            raise GoalOperationError(
                "missing_active_plan_execution",
                "GoalExecution has no active PlanExecution to resume",
                refs=(goal_execution_id,),
            )
        recover_sqlite_control_plane(store)
        assert bundle.plan is not None
        scheduler = self._scheduler(request, store)
        execution = asyncio.run(
            scheduler.run_until_terminal(
                bundle.plan,
                goal.active_plan_execution_ref,
                workspace_ref=str(request.workspace_ref),
                branch=request.branch,
            )
        )
        latest_goal = self._finish_goal_if_ready(
            service,
            goal_execution_id,
            execution.plan_execution_id,
            completion=_scheduler_completion(scheduler),
        )
        report = {
            "schema_version": "ahra/goal-operation-resume/0.1",
            "goalExecutionId": goal_execution_id,
            "planExecutionId": execution.plan_execution_id,
            "goalStatus": latest_goal.status.value,
            "planStatus": execution.status.value,
            "inspect": self.inspect(goal_execution_id, db_path=request.store_path),
        }
        _write_json(request.artifact_dir / "goal-resume-report.json", report)
        return report

    def finish_active_plan_if_terminal(self, goal_execution_id: str, *, db_path: Path | str) -> Any:
        store = self._existing_store(db_path)
        service = PlanExecutionService(store)  # type: ignore[arg-type]
        goal = store.get_goal_execution(goal_execution_id)
        if not goal.active_plan_execution_ref:
            return goal
        execution = store.get_execution(goal.active_plan_execution_ref)
        if not execution.status.terminal:
            return goal
        return self._finish_goal_if_ready(service, goal_execution_id, execution.plan_execution_id)

    def inspect(
        self,
        goal_execution_id: str,
        *,
        db_path: Path | str,
        artifact_dir: Path | str | None = None,
    ) -> dict[str, Any]:
        store = self._existing_store(db_path)
        try:
            goal = store.get_goal_execution(goal_execution_id)
        except KeyError as exc:
            raise GoalOperationError("unknown_goal_execution", f"unknown GoalExecution: {goal_execution_id}", refs=(goal_execution_id,)) from exc
        executions = tuple(
            execution
            for execution in store.list_executions()
            if execution.goal_execution_ref == goal_execution_id or execution.plan_execution_id in goal.plan_execution_refs
        )
        node_runs = tuple(node for execution in executions for node in store.list_node_runs(execution.plan_execution_id))
        idempotency_records = store.list_idempotency_records()
        artifact_refs = _unique_refs(
            (
                *goal.artifact_refs,
                *(ref for execution in executions for ref in execution.artifact_refs),
                *(ref for node in node_runs for ref in node.artifact_refs),
                *(ref for record in idempotency_records for ref in record.result.artifact_refs),
            )
        )
        findings = _artifact_findings(artifact_refs, Path(artifact_dir) if artifact_dir else None)
        return {
            "schema_version": "ahra/goal-operation-inspect/0.1",
            "goalExecution": goal.to_dict(),
            "planExecutions": [execution.to_dict() for execution in executions],
            "nodeRuns": [node.to_dict() for node in node_runs],
            "idempotencyRecords": [record.to_dict() for record in idempotency_records],
            "recoveryEvents": list(store.list_recovery_events()),
            "artifactFindings": findings,
            "metrics": {
                "goalStatus": goal.status.value,
                "planExecutionCount": len(executions),
                "nodeRunCount": len(node_runs),
                "nodeStatusCounts": _count_by([node.status.value for node in node_runs]),
                "evidenceRefCount": len(_unique_refs((*goal.evidence_refs, *(ref for node in node_runs for ref in node.evidence_refs)))),
                "capabilityGrantRefCount": len(_unique_refs(ref for node in node_runs for ref in node.capability_grant_refs)),
                "missingArtifactCount": sum(1 for finding in findings if finding["code"] == "missing_artifact"),
            },
        }

    def cancel(self, goal_execution_id: str, *, db_path: Path | str, reason: str) -> dict[str, Any]:
        store = self._existing_store(db_path)
        service = PlanExecutionService(store)  # type: ignore[arg-type]
        goal = store.get_goal_execution(goal_execution_id)
        if goal.status.terminal:
            raise GoalOperationError(
                "cancel_terminal_goal",
                f"cannot cancel terminal GoalExecution {goal.status.value}",
                refs=(goal_execution_id,),
            )
        canceled_plan: PlanExecutionRecord | None = None
        if goal.active_plan_execution_ref:
            execution = store.get_execution(goal.active_plan_execution_ref)
            if not execution.status.terminal:
                canceled_plan = service.cancel_execution(
                    execution.plan_execution_id,
                    expected_version=execution.status_version,
                    reason=reason,
                )
        latest_goal = store.get_goal_execution(goal_execution_id)
        if latest_goal.status == GoalExecutionStatus.CANCELED:
            canceled_goal = latest_goal
        else:
            if GoalExecutionStatus.CANCELED not in GOAL_TRANSITIONS[latest_goal.status]:
                raise PlanInvalidTransitionError(f"{latest_goal.status.value} -> canceled is not allowed")
            canceled_goal = replace(
                latest_goal,
                status=GoalExecutionStatus.CANCELED,
                status_version=latest_goal.status_version + 1,
                active_plan_execution_ref=None,
                message=reason,
                updated_at=utc_now(),
            )
            canceled_goal = store.compare_and_swap_goal_execution(canceled_goal, latest_goal.status_version)
        return {
            "schema_version": "ahra/goal-operation-cancel/0.1",
            "goalExecutionId": goal_execution_id,
            "goalStatus": canceled_goal.status.value,
            "planStatus": canceled_plan.status.value if canceled_plan else None,
            "reason": reason,
        }

    def plan_bundle(self, request_path: Path | str) -> GoalPlanBundle:
        request = load_goal_execution_request(request_path, profiles=self.profiles)
        profile = self.profiles.get(request.profile_ref)
        self._validate_adapters(request, profile)
        compilation = compile_plan_draft(request.plan_draft, request.compiler_config())
        return GoalPlanBundle(request=request, plan=compilation.plan, validation_report=compilation.report)

    def _require_admitted_plan(self, request_path: Path | str) -> GoalPlanBundle:
        bundle = self.plan_bundle(request_path)
        if not bundle.validation_report.valid or bundle.plan is None:
            raise GoalOperationError(
                "plan_validation_failed",
                "PlanDraft did not compile into an admitted PlanIR",
                refs=tuple(error.code for error in bundle.validation_report.errors),
            )
        return bundle

    def _scheduler(self, request: GoalExecutionRequest, store: SQLiteControlStore) -> StaticPlanScheduler:
        registry = NodeExecutorRegistry()
        executor_release_refs = {
            "bounded_task": DETERMINISTIC_EXECUTOR_REF,
            "repair": DETERMINISTIC_EXECUTOR_REF,
        }
        if request.executor_adapter_ref == REAL_BOUNDED_EXECUTOR_REF:
            self._ensure_runtime_dependencies(request)
            from .reference_runner.bounded_task import BoundedTaskExecutor
            from .reference_runner.store import FileRunStore

            assert self.real_executor_driver is not None
            run_dir = self.real_executor_store_dir or request.artifact_dir / "bounded-task-executor"
            registry.register(
                BoundedTaskExecutor(
                    self.real_executor_driver,
                    store=FileRunStore(run_dir),
                    workspace_provider=self.real_executor_workspace_provider,
                    runtime_provider=self.real_executor_runtime_provider,
                    runtime_profile_ref=self.real_executor_runtime_profile_ref,
                    execution_policy=self.real_executor_execution_policy,
                    release_ref=REAL_BOUNDED_EXECUTOR_REF,
                )
            )
            registry.register(DeterministicFileEffectExecutor(node_type="repair", store=store))
            executor_release_refs = {
                "bounded_task": REAL_BOUNDED_EXECUTOR_REF,
                "repair": DETERMINISTIC_EXECUTOR_REF,
            }
        else:
            for node_type in ("bounded_task", "repair"):
                registry.register(DeterministicFileEffectExecutor(node_type=node_type, store=store))
        gate_registry = GateRunnerRegistry()
        gate_registry.register(DeterministicGateRunner())
        verification_executor = VerificationExecutor(gate_registry)
        verification_service = DeterministicGoalVerificationService.from_required_claim_refs(
            goal_ref=request.goal_ref,
            required_claim_refs=request.required_claim_refs,
            evidence_records=lambda: verification_executor.evidence_records,
        )
        capability_admission = _capability_admission_service(request)
        return StaticPlanScheduler(
            service=PlanExecutionService(store),  # type: ignore[arg-type]
            executor_registry=registry,
            executor_release_refs=executor_release_refs,
            verification_service=verification_service,
            verification_executor=verification_executor,
            verification_environment=EvidenceEnvironment(
                runtime_profile_digest=request.runtime_digest,
                policy_digest=canonical_fingerprint({"allowedCapabilities": list(request.allowed_capabilities)}),
                verifier_release_digest=DETERMINISTIC_GATE_RUNNER_REF,
                test_definition_digest=canonical_fingerprint(dict(request.registered_gate_refs)),
            ),
            capability_admission=capability_admission,
            max_concurrency=request.max_concurrency,
            lease_holder="scheduler:goal-operation-cli",
            lease_ttl_seconds=300,
        )

    def _ensure_runtime_dependencies(self, request: GoalExecutionRequest) -> None:
        if request.executor_adapter_ref == REAL_BOUNDED_EXECUTOR_REF and self.real_executor_driver is None:
            raise GoalOperationError(
                "real_executor_driver_unavailable",
                "real bounded Executor profile requires an injected AgentDriver before execution starts",
                refs=(request.profile_ref, request.executor_adapter_ref),
            )

    def _finish_goal_if_ready(
        self,
        service: PlanExecutionService,
        goal_execution_id: str,
        plan_execution_id: str,
        *,
        completion: CompletionGateResult | None = None,
    ) -> Any:
        goal = service.store.get_goal_execution(goal_execution_id)
        execution = service.store.get_execution(plan_execution_id)
        if not execution.status.terminal or goal.active_plan_execution_ref != plan_execution_id:
            return goal
        goal = service.finish_active_plan_execution(
            goal_execution_id,
            plan_execution_id,
            expected_version=goal.status_version,
        )
        if execution.status == PlanExecutionStatus.SUCCEEDED:
            completion = completion or CompletionGateResult(
                complete=False,
                missing_claim_refs=("completion_gate_result_unavailable",),
            )
            goal = service.complete_goal(
                goal_execution_id,
                completion_complete=completion.complete,
                expected_version=goal.status_version,
                evidence_refs=execution.evidence_refs,
                artifact_refs=execution.artifact_refs,
            )
        return goal

    def _validate_adapters(self, request: GoalExecutionRequest, profile: GoalOperationProfile) -> None:
        if request.store_kind not in profile.store_kinds:
            raise GoalOperationError("unknown_store_ref", f"unsupported Goal operation store kind: {request.store_kind}", refs=(request.store_kind,))
        if request.planner_adapter_ref != profile.planner_adapter_ref:
            raise GoalOperationError(
                "unknown_planner_adapter",
                f"unknown planner adapter for profile {profile.profile_ref}: {request.planner_adapter_ref}",
                refs=(request.planner_adapter_ref,),
            )
        if request.executor_adapter_ref != profile.executor_adapter_ref:
            raise GoalOperationError(
                "unknown_executor_adapter",
                f"unknown executor adapter for profile {profile.profile_ref}: {request.executor_adapter_ref}",
                refs=(request.executor_adapter_ref,),
            )
        if request.gate_runner_adapter_ref != profile.gate_runner_adapter_ref:
            raise GoalOperationError(
                "unknown_gate_runner",
                f"unknown GateRunner adapter for profile {profile.profile_ref}: {request.gate_runner_adapter_ref}",
                refs=(request.gate_runner_adapter_ref,),
            )
        if request.runtime_ref != profile.runtime_ref or request.runtime_digest != profile.runtime_digest:
            raise GoalOperationError(
                "unknown_runtime_ref",
                f"unknown runtime ref for profile {profile.profile_ref}: {request.runtime_ref}",
                refs=(request.runtime_ref,),
            )
        if request.registered_runtime_refs.get(request.runtime_ref) != request.runtime_digest:
            raise GoalOperationError(
                "runtime_digest_mismatch",
                "request runtime registry digest does not match the selected runtime",
                refs=(request.runtime_ref,),
            )

    def _existing_store(self, db_path: Path | str) -> SQLiteControlStore:
        path = Path(db_path)
        if not path.exists():
            raise GoalOperationError("missing_sqlite_database", f"SQLite control store does not exist: {path}", refs=(str(path),))
        return SQLiteControlStore(path)


class DeterministicGoalVerificationService:
    def __init__(
        self,
        *,
        graph: ClaimGraph | None = None,
        evidence_records: Callable[[], tuple[EvidenceV2, ...]] | None = None,
    ) -> None:
        self.graph = graph
        self._evidence_records = evidence_records or (lambda: ())

    @classmethod
    def from_required_claim_refs(
        cls,
        *,
        goal_ref: str,
        required_claim_refs: tuple[str, ...],
        evidence_records: Callable[[], tuple[EvidenceV2, ...]],
    ) -> "DeterministicGoalVerificationService":
        return cls(
            graph=_claim_graph_from_required_claim_refs(
                goal_ref=goal_ref,
                required_claim_refs=required_claim_refs,
            ),
            evidence_records=evidence_records,
        )

    def select(self, trigger: VerificationTrigger) -> VerificationSelection:
        return VerificationSelection(
            selected_gate_refs=tuple(sorted(trigger.failed_gate_refs)),
            full_gate_refs=tuple(sorted(trigger.failed_gate_refs)),
            affected_claim_refs=tuple(sorted(trigger.changed_claim_refs)),
            reused_evidence_refs=(),
            stale_evidence_refs=(),
            rationale=("deterministic_goal_operation_selection",),
        )

    def complete(self, trigger: VerificationTrigger | None = None) -> CompletionGateResult:
        if self.graph is None:
            return CompletionGateResult(
                complete=False,
                missing_claim_refs=("claim_graph_unavailable",),
            )
        return evaluate_completion(
            graph=self.graph,
            evidence_records=self._evidence_records(),
            trigger=trigger,
        )

    def defects(self) -> tuple[Any, ...]:
        return ()


class DeterministicFileEffectExecutor:
    def __init__(self, *, node_type: str, store: SQLiteControlStore) -> None:
        self._node_type = node_type
        self.store = store

    @property
    def node_type(self) -> str:
        return self._node_type

    @property
    def release_ref(self) -> str:
        return DETERMINISTIC_EXECUTOR_REF

    async def execute(self, request: NodeExecutionRequest) -> NodeExecutionResult:
        grant = _first_write_grant(request)
        relative_path = _relative_artifact_path(request)
        gateway = LocalRuntimeGateway(Path(request.workspace_ref))
        content = (
            f"goal={request.plan.goal_ref}\n"
            f"plan={request.plan.plan_id}\n"
            f"node={request.node.node_id}\n"
            f"node_run={request.run_id}\n"
        )
        audit = gateway.write_text(
            grant,
            plan_id=request.plan.plan_id,
            node_id=request.node.node_id,
            actor="executor",
            relative_path=relative_path,
            content=content,
        )
        if not audit.allowed:
            return NodeExecutionResult(
                node_run_id=request.run_id,
                plan_id=request.plan.plan_id,
                node_id=request.node.node_id,
                node_type=request.node.node_type,
                executor_release=self.release_ref,
                status=NodeExecutionStatus.REJECTED,
                terminal_failure_refs=(audit.audit_id,),
                usage=NodeExecutionUsage(model_calls=0, tool_calls=1, cost_usd=0.0),
                message=f"deterministic file effect denied: {audit.reason_code}",
                details={"failureClass": audit.reason_code, "audit": audit.to_dict()},
            )
        target = (Path(request.workspace_ref) / relative_path).resolve()
        result = NodeExecutionResult(
            node_run_id=request.run_id,
            plan_id=request.plan.plan_id,
            node_id=request.node.node_id,
            node_type=request.node.node_type,
            executor_release=self.release_ref,
            status=NodeExecutionStatus.ACCEPTED,
            artifact_refs=(f"file://{target}",),
            gate_refs=request.node.gate_refs,
            usage=NodeExecutionUsage(model_calls=0, tool_calls=1, cost_usd=0.0),
            message="Deterministic Goal operation executor wrote the requested local artifact.",
            details={
                "artifactRelativePath": relative_path,
                "audit": audit.to_dict(),
                "verificationMetadata": {"claimRefs": tuple(request.node.claim_refs)},
            },
        )
        self.store.record_idempotency_result(
            idempotency_key=_node_idempotency_key(request),
            plan_execution_id=request.run_id.split(":", 1)[0] if ":" in request.run_id else _plan_execution_ref_for_node(self.store, request.run_id),
            node_run_id=request.run_id,
            result=result,
        )
        return result


def load_goal_execution_request(
    path: Path | str,
    *,
    profiles: GoalOperationProfileRegistry | None = None,
) -> GoalExecutionRequest:
    request_path = Path(path)
    data = yaml.safe_load(request_path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise GoalOperationError("invalid_goal_request", f"GoalExecutionRequest must be a mapping: {request_path}")
    if data.get("apiVersion") != "ahra.dev/v1alpha1" or data.get("kind") != "GoalExecutionRequest":
        raise GoalOperationError("invalid_goal_request", "expected apiVersion ahra.dev/v1alpha1 and kind GoalExecutionRequest")
    metadata = _mapping(data.get("metadata"), "metadata")
    spec = _mapping(data.get("spec"), "spec")
    name = _string(metadata.get("name"), "metadata.name")
    request_id = str(metadata.get("requestId") or name)
    idempotency_key = _string(metadata.get("idempotencyKey"), "metadata.idempotencyKey")
    profile_ref = _string(spec.get("profileRef"), "spec.profileRef")
    profile = (profiles or GoalOperationProfileRegistry()).get(profile_ref)
    base = request_path.parent
    store = _mapping(spec.get("store"), "spec.store")
    planner = _mapping(spec.get("planner"), "spec.planner")
    executor = _mapping(spec.get("executor"), "spec.executor")
    gate_runner = _mapping(spec.get("gateRunner"), "spec.gateRunner")
    runtime = _mapping(spec.get("runtime"), "spec.runtime")
    goal = _mapping(spec.get("goal"), "spec.goal")
    registry = _mapping(spec.get("registry"), "spec.registry")
    execution = _mapping(spec.get("execution") or {}, "spec.execution")
    goal_digest = _digest(_string(goal.get("goalDigest"), "spec.goal.goalDigest"), "spec.goal.goalDigest")
    claim_graph_digest = _digest(_string(goal.get("claimGraphDigest"), "spec.goal.claimGraphDigest"), "spec.goal.claimGraphDigest")
    runtime_ref = _string(runtime.get("runtimeRef"), "spec.runtime.runtimeRef")
    runtime_digest = _digest(_string(runtime.get("digest"), "spec.runtime.digest"), "spec.runtime.digest")
    registered_runtime_refs = _string_mapping(registry.get("runtimeRefs") or {runtime_ref: runtime_digest}, "spec.registry.runtimeRefs")
    request = GoalExecutionRequest(
        name=name,
        request_id=request_id,
        idempotency_key=idempotency_key,
        profile_ref=profile_ref,
        workspace_ref=_resolve_path(base, _string(spec.get("workspaceRef"), "spec.workspaceRef")),
        artifact_dir=_resolve_path(base, _string(spec.get("artifactDir"), "spec.artifactDir")),
        store_kind=_string(store.get("kind"), "spec.store.kind"),
        store_path=_resolve_path(base, _string(store.get("path"), "spec.store.path")),
        planner_adapter_ref=_string(planner.get("adapterRef"), "spec.planner.adapterRef"),
        executor_adapter_ref=_string(executor.get("adapterRef"), "spec.executor.adapterRef"),
        gate_runner_adapter_ref=_string(gate_runner.get("adapterRef"), "spec.gateRunner.adapterRef"),
        runtime_ref=runtime_ref,
        runtime_digest=runtime_digest,
        goal_ref=_string(goal.get("goalRef"), "spec.goal.goalRef"),
        goal_digest=goal_digest,
        claim_graph_digest=claim_graph_digest,
        claim_graph_ref=str(goal["claimGraphRef"]) if goal.get("claimGraphRef") else None,
        required_claim_refs=_string_tuple(goal.get("requiredClaimRefs"), "spec.goal.requiredClaimRefs"),
        registered_node_types=_string_mapping(registry.get("nodeTypes"), "spec.registry.nodeTypes"),
        registered_gate_refs=_string_mapping(registry.get("gateRefs"), "spec.registry.gateRefs"),
        registered_runtime_refs=registered_runtime_refs,
        allowed_capabilities=_string_tuple(registry.get("allowedCapabilities"), "spec.registry.allowedCapabilities"),
        plan_draft=PlanDraft.from_mapping(_mapping(spec.get("planDraft"), "spec.planDraft")),
        max_repair_cycles=int(execution.get("maxRepairCycles", 2)),
        max_concurrency=int(execution.get("maxConcurrency", 1)),
        branch=str(execution.get("branch") or "main"),
    )
    _validate_request_profile_shape(request, profile)
    return request


def _validate_request_profile_shape(request: GoalExecutionRequest, profile: GoalOperationProfile) -> None:
    unknown_registry_node_types = tuple(sorted(set(request.registered_node_types) - set(profile.registered_node_types)))
    if unknown_registry_node_types:
        raise GoalOperationError(
            "unknown_node_type",
            "GoalExecutionRequest registers node types outside the selected profile",
            refs=unknown_registry_node_types,
        )
    if request.max_repair_cycles < 0:
        raise GoalOperationError("invalid_goal_request", "execution.maxRepairCycles must be non-negative")
    if request.max_concurrency < 1:
        raise GoalOperationError("invalid_goal_request", "execution.maxConcurrency must be at least 1")


def _capability_admission_service(request: GoalExecutionRequest) -> CapabilityAdmissionService:
    allowed_actions: dict[str, tuple[str, ...]] = {}
    max_spawn_limit = 0
    for node in request.plan_draft.nodes:
        for capability in node.capability_requests:
            allowed_actions.setdefault(capability.capability, tuple())
            allowed_actions[capability.capability] = _unique_refs((*allowed_actions[capability.capability], *capability.resources))
            if capability.capability == "spawn.agent":
                max_spawn_limit = max(max_spawn_limit, node.budget.max_spawned_nodes)
    return CapabilityAdmissionService(
        goal_scope=CapabilityScope(
            allowed_actions=allowed_actions,
            allowed_roles_by_action={action: ("executor",) for action in allowed_actions},
            max_spawn_limit=max_spawn_limit,
        ),
        runtime_profile=RuntimeCapabilityProfile(
            runtime_ref=request.runtime_ref,
            supported_actions=frozenset(request.allowed_capabilities),
            allowed_commands=allowed_actions.get("process.exec", ()),
        ),
        issuer="goal-operation:capability-admission",
    )


def _first_write_grant(request: NodeExecutionRequest) -> Any:
    for grant in request.capability_grants:
        if grant.action == "filesystem.write":
            return grant
    raise GoalOperationError("missing_write_grant", f"node {request.node.node_id} has no filesystem.write grant")


def _relative_artifact_path(request: NodeExecutionRequest) -> str:
    resources = tuple(grant.resources for grant in request.capability_grants if grant.action == "filesystem.write")
    flattened = tuple(resource for group in resources for resource in group)
    for resource in flattened:
        if "*" not in resource and "?" not in resource:
            return resource.replace("\\", "/")
    prefix = "outputs"
    if flattened:
        candidate = flattened[0].replace("\\", "/")
        prefix = candidate.split("*", 1)[0].rstrip("/") or "outputs"
    return f"{prefix}/{request.node.node_id}.txt".replace("//", "/")


def _node_idempotency_key(request: NodeExecutionRequest) -> str:
    return canonical_fingerprint(
        {
            "planDigest": request.plan.digest(),
            "nodeRunId": request.run_id,
            "nodeId": request.node.node_id,
            "grantDigests": [grant.digest() for grant in request.capability_grants],
        }
    )


def _plan_execution_ref_for_node(store: SQLiteControlStore, node_run_id: str) -> str:
    return store.get_node_run(node_run_id).plan_execution_id


def _goal_exists(store: SQLiteControlStore, goal_execution_id: str) -> bool:
    try:
        store.get_goal_execution(goal_execution_id)
        return True
    except KeyError:
        return False


def _claim_graph_from_required_claim_refs(*, goal_ref: str, required_claim_refs: tuple[str, ...]) -> ClaimGraph:
    claims = tuple(
        Claim(
            claim_id=claim_ref,
            claim_type=ClaimType.FUNCTIONAL,
            statement=f"{claim_ref} is required for {goal_ref}.",
            criterion_refs=(f"CRIT-{claim_ref}",),
            depends_on=(),
            risk_level=RiskLevel.R1,
            required_evidence_kinds=("gate_run",),
            gate_refs=(),
            required=True,
        )
        for claim_ref in sorted(set(required_claim_refs))
    )
    return ClaimGraph(goal_ref=goal_ref, version=1, claims=claims)


def _scheduler_completion(scheduler: StaticPlanScheduler) -> CompletionGateResult:
    if scheduler.verification_service is None:
        return CompletionGateResult(
            complete=False,
            missing_claim_refs=("verification_service_unavailable",),
        )
    return scheduler.verification_service.complete(VerificationTrigger())


def _looks_like_legacy_profile(profile_ref: str) -> bool:
    normalized = profile_ref.casefold()
    return any(token in normalized for token in ("standard-harness", "loop-engineering", "workflow"))


def _artifact_findings(artifact_refs: tuple[str, ...], artifact_dir: Path | None) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    manifest_index = _artifact_manifest_index(artifact_dir)
    for ref in artifact_refs:
        path = _artifact_ref_path(ref, artifact_dir, manifest_index)
        if path is None:
            continue
        if not path.exists():
            findings.append({"code": "missing_artifact", "severity": "error", "ref": ref, "path": str(path)})
    return findings


def _artifact_ref_path(ref: str, artifact_dir: Path | None, manifest_index: Mapping[str, Path]) -> Path | None:
    if ref.startswith("file://"):
        return Path(ref.removeprefix("file://"))
    if ref in manifest_index:
        return manifest_index[ref]
    if artifact_dir is not None:
        return artifact_dir / ref
    return None


def _artifact_manifest_index(artifact_dir: Path | None) -> dict[str, Path]:
    if artifact_dir is None:
        return {}
    manifests = [artifact_dir / "artifact-manifest.json"]
    if artifact_dir.parent.exists():
        manifests.extend(sorted(path for path in artifact_dir.parent.glob("*/artifact-manifest.json") if path not in manifests))
    index: dict[str, Path] = {}
    for manifest in manifests:
        if not manifest.exists():
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, Mapping):
            continue
        for record in data.get("artifacts", ()):
            if not isinstance(record, Mapping):
                continue
            artifact_id = record.get("artifact_id")
            uri = record.get("uri")
            if isinstance(artifact_id, str) and isinstance(uri, str):
                index[artifact_id] = _manifest_artifact_path(manifest.parent, uri)
    return index


def _manifest_artifact_path(base: Path, uri: str) -> Path:
    if uri.startswith("file://"):
        return Path(uri.removeprefix("file://"))
    if uri.startswith("local://"):
        return base / uri.removeprefix("local://")
    return base / uri


def _plan_metrics(plan: PlanIR | None) -> dict[str, Any]:
    if plan is None:
        return {"planNodeCount": 0, "gateRefCount": 0, "executableNodeCount": 0}
    return {
        "planNodeCount": len(plan.nodes),
        "gateRefCount": len(_unique_refs(ref for node in plan.nodes for ref in node.gate_refs)),
        "executableNodeCount": sum(1 for node in plan.nodes if node.node_type not in {"goal_verification", "gate_verification"}),
        "declaredCapabilityCount": sum(len(node.capability_grants) for node in plan.nodes),
    }


def _count_by(values: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _mapping(value: Any, ref: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GoalOperationError("invalid_goal_request", f"{ref} must be an object", refs=(ref,))
    return value


def _string(value: Any, ref: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GoalOperationError("invalid_goal_request", f"{ref} must be a non-empty string", refs=(ref,))
    return value


def _string_tuple(value: Any, ref: str) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        raise GoalOperationError("invalid_goal_request", f"{ref} must be a list", refs=(ref,))
    items = tuple(sorted(str(item) for item in value if str(item)))
    if not items:
        raise GoalOperationError("invalid_goal_request", f"{ref} must not be empty", refs=(ref,))
    return items


def _string_mapping(value: Any, ref: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise GoalOperationError("invalid_goal_request", f"{ref} must be an object", refs=(ref,))
    result = {str(key): str(item) for key, item in value.items()}
    if not result:
        raise GoalOperationError("invalid_goal_request", f"{ref} must not be empty", refs=(ref,))
    return result


def _digest(value: str, ref: str) -> str:
    if not value.startswith("sha256:") or len(value.removeprefix("sha256:")) != 64:
        raise GoalOperationError("invalid_digest", f"{ref} must be a sha256 digest ref", refs=(ref, value))
    try:
        int(value.removeprefix("sha256:"), 16)
    except ValueError as exc:
        raise GoalOperationError("invalid_digest", f"{ref} must be hex encoded", refs=(ref, value)) from exc
    return value


def _resolve_path(base: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _unique_refs(values: Any) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        text = str(value)
        if text not in result:
            result.append(text)
    return tuple(result)
