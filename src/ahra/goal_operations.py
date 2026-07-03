from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Mapping

import yaml

from .awkp_state_writer import AwkpTaskStateWriter
from .capabilities import CapabilityAdmissionService, CapabilityScope, LocalRuntimeGateway, RuntimeCapabilityProfile
from .acceptance_contracts import Claim, ClaimGraph, ClaimType, GateDefinition, RiskLevel
from .domain import utc_now
from .evidence_v2 import DigestRef, EvidenceEnvironment, EvidenceV2, GateRunV2, canonical_fingerprint
from .node_executor import (
    NodeExecutionRequest,
    NodeExecutionResult,
    NodeExecutionStatus,
    NodeExecutionUsage,
    NodeExecutorRegistry,
)
from .orchestrator import AwkpTaskOrchestrationRequest, AwkpTaskReviewOrchestrator
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
from .plan_ir import PlanBudget, PlanCompilerConfig, PlanDraft, PlanIR, PlanValidationReport, compile_plan_draft
from .sqlite_control_store import SQLiteControlStore, SQLiteControlStoreError, recover_sqlite_control_plane
from .verification import (
    CommandGateRunner,
    CompletionGateResult,
    DefectRecord,
    DeterministicGateRunner,
    GateExecutionStatus,
    GateRunnerRegistry,
    SemanticReviewGateRunner,
    VerificationExecutionReport,
    VerificationExecutor,
    VerificationResult,
    VerificationSelection,
    VerificationTrigger,
    _gate_definition_digest,
    defect_from_result,
    evaluate_completion,
)

if TYPE_CHECKING:
    from .ports import AgentDriver


GOAL_OPERATION_SCHEMA_VERSION = "ahra/goal-operation/0.1"
M1_PROFILE_REF = "profile/m1-deterministic@sha256:" + "a" * 64
M1_REAL_PLANNER_PROFILE_REF = "profile/m1-real-planner@sha256:" + "f" * 64
M1_REAL_EXECUTOR_PROFILE_REF = "profile/m1-real-executor@sha256:" + "9" * 64
M1_REAL_COMBINED_PROFILE_REF = "profile/m1-real-combined@sha256:" + "8" * 64
DEVELOPMENT_BOUNDED_PROFILE_REF = "profile/development-bounded"
INLINE_PLANNER_REF = "planner/inline-plan-draft@sha256:" + "b" * 64
REAL_PLANNER_ADAPTER_REF = "planner/agent-driver-plan-draft@sha256:" + "7" * 64
DETERMINISTIC_EXECUTOR_REF = "executor/deterministic-file-effect@sha256:" + "c" * 64
REAL_BOUNDED_EXECUTOR_REF = "executor/bounded-task-agent-driver@sha256:" + "6" * 64
DETERMINISTIC_GATE_RUNNER_REF = "gate-runner/deterministic@sha256:" + "d" * 64
COMMAND_GATE_RUNNER_REF = "gate-runner/command@sha256:" + "5" * 64
LOCAL_GOAL_RUNTIME_REF = "runtime/local-goal@sha256:" + "e" * 64
LOCAL_GOAL_RUNTIME_DIGEST = "sha256:" + "e" * 64
LOCAL_GOAL_RUNTIME_EGRESS_ALLOWLIST = ("https://example.invalid/*",)
DEVELOPMENT_BOUNDED_WRITE_ALLOWLIST = (
    "alignment_*.py",
    "intent_*.py",
    "request_*.py",
    "src/ahra/alignment_*.py",
    "src/ahra/intent_*.py",
    "src/ahra/request_*.py",
    "contracts/schemas/**",
    "tests/test_alignment_*.py",
    "tests/test_intent_*.py",
    "tests/test_request_*.py",
    "docs/architecture/intent-*",
    "examples/intents/**",
)
DEVELOPMENT_BOUNDED_WRITE_BLACKLIST = (
    "evidence_gate.py",
    "capabilities.py",
    "verification.py",
    "goal_operations.py",
    "sqlite_control_store.py",
    "ports.py",
    "awkp_state_writer.py",
    "src/ahra/evidence_gate.py",
    "src/ahra/capabilities.py",
    "src/ahra/verification.py",
    "src/ahra/goal_operations.py",
    "src/ahra/sqlite_control_store.py",
    "src/ahra/ports.py",
    "src/ahra/awkp_state_writer.py",
    "scripts/**",
    "pyproject.toml",
    "uv.lock",
    "Makefile",
    ".github/**",
)
DEVELOPMENT_BOUNDED_PROCESS_COMMANDS = (
    "uv run python -B scripts/check.py",
    "uv run python -B scripts/check.py --lint",
    "uv run python -B scripts/check.py --test",
    "uv run python -B scripts/lint_awkp.py",
    "uv run python -B scripts/lint_*.py",
)
DEFAULT_SCHEDULER_LEASE_TTL_SECONDS = 300
DEVELOPMENT_BOUNDED_TERMINAL_WRITE_GRACE_SECONDS = 300
DEVELOPMENT_BOUNDED_NODE_BUDGET = PlanBudget(
    max_model_calls=10,
    max_tool_calls=50,
    max_spawned_nodes=0,
    max_wall_seconds=2100,
    max_cost_usd=1.0,
)


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
    runtime_network_egress: tuple[str, ...] = ()
    filesystem_write_allowlist: tuple[str, ...] = ()
    filesystem_write_blacklist: tuple[str, ...] = ()
    process_exec_allowlist: tuple[str, ...] = ()
    default_node_budget: PlanBudget | None = None
    preserve_failed_workspace: bool = False

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
    gate_definitions: tuple[GateDefinition, ...]
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
                    "gateDefinitions": [definition.to_mapping() for definition in self.gate_definitions],
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


@dataclass(frozen=True, slots=True)
class GoalAwkpBridgeRequest:
    goal_execution_id: str
    task: str | Path
    expected_task_version: int
    producer_actor: str
    verifier_actor: str
    fencing_token: str
    report_paths: tuple[str | Path, ...]
    db_path: str | Path
    artifact_dir: str | Path
    work_root: str | Path = "work"
    max_cycles: int = 1
    idempotency_key_prefix: str | None = None
    lease_ttl_seconds: int | None = None
    reason: str = "Completed GoalExecution evidence is ready for AWKP EvidenceGate review."


@dataclass(frozen=True, slots=True)
class GoalAwkpBridgeMaterialization:
    association_event_id: str
    association_state_version: int
    artifact_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    kernel_evidence_refs: tuple[str, ...]
    kernel_gate_run_refs: tuple[str, ...]
    association_ref: str


@dataclass(frozen=True, slots=True)
class GoalAwkpBridgeResult:
    task_id: str
    goal_execution_id: str
    goal_status: str
    materialization: GoalAwkpBridgeMaterialization
    orchestration: Any


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
                runtime_network_egress=LOCAL_GOAL_RUNTIME_EGRESS_ALLOWLIST,
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
                runtime_network_egress=LOCAL_GOAL_RUNTIME_EGRESS_ALLOWLIST,
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
                runtime_network_egress=LOCAL_GOAL_RUNTIME_EGRESS_ALLOWLIST,
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
                runtime_network_egress=LOCAL_GOAL_RUNTIME_EGRESS_ALLOWLIST,
            ),
            GoalOperationProfile(
                profile_ref=DEVELOPMENT_BOUNDED_PROFILE_REF,
                planner_adapter_ref=INLINE_PLANNER_REF,
                executor_adapter_ref=REAL_BOUNDED_EXECUTOR_REF,
                gate_runner_adapter_ref=DETERMINISTIC_GATE_RUNNER_REF,
                runtime_ref=LOCAL_GOAL_RUNTIME_REF,
                runtime_digest=LOCAL_GOAL_RUNTIME_DIGEST,
                store_kinds=frozenset({"sqlite"}),
                executable_node_types=frozenset({"bounded_task", "repair"}),
                scheduler_node_types=frozenset({"goal_verification", "gate_verification"}),
                filesystem_write_allowlist=DEVELOPMENT_BOUNDED_WRITE_ALLOWLIST,
                filesystem_write_blacklist=DEVELOPMENT_BOUNDED_WRITE_BLACKLIST,
                process_exec_allowlist=DEVELOPMENT_BOUNDED_PROCESS_COMMANDS,
                default_node_budget=DEVELOPMENT_BOUNDED_NODE_BUDGET,
                preserve_failed_workspace=True,
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


class GoalAwkpBridge:
    """Associates a completed GoalExecution with one AWKP task review cycle."""

    def __init__(
        self,
        *,
        work_root: str | Path = "work",
        state_writer: AwkpTaskStateWriter | None = None,
        task_orchestrator: AwkpTaskReviewOrchestrator | None = None,
    ) -> None:
        self.work_root = Path(work_root)
        self.state_writer = state_writer or AwkpTaskStateWriter(work_root=self.work_root)
        self.task_orchestrator = task_orchestrator or AwkpTaskReviewOrchestrator(
            work_root=self.work_root,
            state_writer=self.state_writer,
        )

    def run(self, request: GoalAwkpBridgeRequest) -> GoalAwkpBridgeResult:
        if not request.report_paths:
            raise GoalOperationError("missing_awkp_gate_report", "Goal-to-AWKP bridge requires a verifier report path")
        if request.producer_actor == request.verifier_actor:
            raise GoalOperationError(
                "producer_verifier_identity_conflict",
                "Goal-to-AWKP bridge requires distinct producer and verifier actors",
                refs=(request.producer_actor,),
            )
        _validate_awkp_gate_report_inputs(request.report_paths)

        store = SQLiteControlStore(request.db_path)
        try:
            goal = store.get_goal_execution(request.goal_execution_id)
        except KeyError as exc:
            raise GoalOperationError(
                "unknown_goal_execution",
                f"unknown GoalExecution: {request.goal_execution_id}",
                refs=(request.goal_execution_id,),
            ) from exc
        if goal.status != GoalExecutionStatus.SUCCEEDED:
            raise GoalOperationError(
                "goal_execution_not_succeeded",
                "only a succeeded GoalExecution may advance an AWKP task",
                refs=(request.goal_execution_id, goal.status.value),
            )

        task_dir = _awkp_task_dir_for_bridge(request.task, self.work_root)
        task_id = _task_id_from_awkp_state(task_dir)
        prefix = request.idempotency_key_prefix or f"{task_id}:goal-awkp-bridge:{goal.goal_execution_id}"
        materialized = _materialize_goal_awkp_bridge(
            task_dir=task_dir,
            goal=goal,
            artifact_dir=Path(request.artifact_dir),
            producer_actor=request.producer_actor,
            idempotency_key_prefix=prefix,
            db_path=Path(request.db_path),
        )
        association = self.state_writer.record_goal_association(
            request.task,
            expected_version=request.expected_task_version,
            actor=request.producer_actor,
            idempotency_key=f"{prefix}:associate",
            fencing_token=request.fencing_token,
            goal_execution_id=goal.goal_execution_id,
            goal_status=goal.status.value,
            reason=(
                "Associated succeeded GoalExecution with this AWKP task and published "
                "kernel EvidenceV2/GateRun records for EvidenceGate review."
            ),
            refs=(
                "state.json",
                "artifact-manifest.json",
                "evidence-manifest.json",
                materialized.association_ref,
            ),
            artifact_refs=materialized.artifact_refs,
            evidence_refs=materialized.evidence_refs,
            next_action="GoalExecution evidence is associated; orchestrator should request independent review.",
        )
        materialized = GoalAwkpBridgeMaterialization(
            association_event_id=association.event_id,
            association_state_version=association.state_version,
            artifact_refs=materialized.artifact_refs,
            evidence_refs=materialized.evidence_refs,
            kernel_evidence_refs=materialized.kernel_evidence_refs,
            kernel_gate_run_refs=materialized.kernel_gate_run_refs,
            association_ref=materialized.association_ref,
        )
        orchestration = self.task_orchestrator.run(
            AwkpTaskOrchestrationRequest(
                task=request.task,
                work_root=self.work_root,
                expected_version=association.state_version,
                producer_actor=request.producer_actor,
                verifier_actor=request.verifier_actor,
                fencing_token=request.fencing_token,
                report_paths=request.report_paths,
                max_cycles=request.max_cycles,
                idempotency_key_prefix=f"{prefix}:review",
                review_refs=(
                    "state.json",
                    "artifact-manifest.json",
                    "evidence-manifest.json",
                    materialized.association_ref,
                ),
                artifact_refs=materialized.artifact_refs,
                evidence_refs=materialized.evidence_refs,
                lease_ttl_seconds=request.lease_ttl_seconds,
                reason=request.reason,
            )
        )
        return GoalAwkpBridgeResult(
            task_id=task_id,
            goal_execution_id=goal.goal_execution_id,
            goal_status=goal.status.value,
            materialization=materialized,
            orchestration=orchestration,
        )


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
        try:
            store = SQLiteControlStore(request.store_path)
        except SQLiteControlStoreError as exc:
            raise GoalOperationError(
                "sqlite_control_store_unavailable",
                str(exc),
                refs=(str(request.store_path),),
            ) from exc
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
        profile = self.profiles.get(request.profile_ref)
        workspace_provider = self._real_executor_workspace_provider(request, profile)
        execution_workspace_ref = self._prepare_execution_workspace(request, workspace_provider)
        scheduler = self._scheduler(
            request,
            store,
            real_executor_workspace_provider=workspace_provider,
        )
        execution_workspace_preserved = True
        try:
            if run_once:
                ran = asyncio.run(
                    scheduler.run_ready_nodes_once(
                        bundle.plan,
                        execution.plan_execution_id,
                        workspace_ref=execution_workspace_ref,
                        branch=request.branch,
                    )
                )
                latest_execution = store.get_execution(execution.plan_execution_id)
                latest_goal = store.get_goal_execution(goal.goal_execution_id)
                defects = _scheduler_defects(scheduler)
                completion = _scheduler_completion(scheduler)
                execution_workspace_preserved = (
                    profile.preserve_failed_workspace
                    and latest_execution.status == PlanExecutionStatus.FAILED
                )
            else:
                latest_execution = asyncio.run(
                    scheduler.run_until_terminal(
                        bundle.plan,
                        execution.plan_execution_id,
                        workspace_ref=execution_workspace_ref,
                        branch=request.branch,
                    )
                )
                defects = _scheduler_defects(scheduler)
                completion = _scheduler_completion(scheduler)
                latest_goal = self._finish_goal_if_ready(
                    service,
                    goal.goal_execution_id,
                    latest_execution.plan_execution_id,
                    completion=completion,
                    open_defect_refs=tuple(defect.defect_id for defect in defects),
                )
                ran = True
                execution_workspace_preserved = (
                    profile.preserve_failed_workspace
                    and latest_execution.status == PlanExecutionStatus.FAILED
                )
        finally:
            self._finalize_execution_workspace(
                workspace_provider,
                execution_workspace_ref,
                preserve=execution_workspace_preserved,
            )
        kernel_verification = _write_kernel_verification_records(request.artifact_dir, scheduler.verification_executor)
        result = self.inspect(goal.goal_execution_id, db_path=request.store_path)
        report = {
            "schema_version": "ahra/goal-operation-start/0.1",
            "goalExecutionId": goal.goal_execution_id,
            "planExecutionId": execution.plan_execution_id,
            "executionWorkspaceRef": execution_workspace_ref,
            "executionWorkspacePreserved": execution_workspace_preserved,
            "ranReadyNodes": ran,
            "runOnce": run_once,
            "goalStatus": latest_goal.status.value,
            "planStatus": latest_execution.status.value,
            "defects": [defect.to_dict() for defect in defects],
            "completion": _completion_dict(completion),
            "kernelVerification": kernel_verification,
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
        profile = self.profiles.get(request.profile_ref)
        workspace_provider = self._real_executor_workspace_provider(request, profile)
        execution_workspace_ref = self._prepare_execution_workspace(request, workspace_provider)
        scheduler = self._scheduler(
            request,
            store,
            real_executor_workspace_provider=workspace_provider,
        )
        execution_workspace_preserved = True
        try:
            execution = asyncio.run(
                scheduler.run_until_terminal(
                    bundle.plan,
                    goal.active_plan_execution_ref,
                    workspace_ref=execution_workspace_ref,
                    branch=request.branch,
                )
            )
            defects = _scheduler_defects(scheduler)
            completion = _scheduler_completion(scheduler)
            latest_goal = self._finish_goal_if_ready(
                service,
                goal_execution_id,
                execution.plan_execution_id,
                completion=completion,
                open_defect_refs=tuple(defect.defect_id for defect in defects),
            )
            execution_workspace_preserved = (
                profile.preserve_failed_workspace
                and execution.status == PlanExecutionStatus.FAILED
            )
        finally:
            self._finalize_execution_workspace(
                workspace_provider,
                execution_workspace_ref,
                preserve=execution_workspace_preserved,
            )
        report = {
            "schema_version": "ahra/goal-operation-resume/0.1",
            "goalExecutionId": goal_execution_id,
            "planExecutionId": execution.plan_execution_id,
            "executionWorkspaceRef": execution_workspace_ref,
            "executionWorkspacePreserved": execution_workspace_preserved,
            "goalStatus": latest_goal.status.value,
            "planStatus": execution.status.value,
            "defects": [defect.to_dict() for defect in defects],
            "completion": _completion_dict(completion),
            "kernelVerification": _write_kernel_verification_records(request.artifact_dir, scheduler.verification_executor),
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

    def _scheduler(
        self,
        request: GoalExecutionRequest,
        store: SQLiteControlStore,
        *,
        real_executor_workspace_provider: Any | None = None,
    ) -> StaticPlanScheduler:
        profile = self.profiles.get(request.profile_ref)
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
                    workspace_provider=real_executor_workspace_provider
                    if real_executor_workspace_provider is not None
                    else self.real_executor_workspace_provider,
                    runtime_provider=self.real_executor_runtime_provider,
                    runtime_profile_ref=self.real_executor_runtime_profile_ref,
                    execution_policy=self.real_executor_execution_policy,
                    release_ref=REAL_BOUNDED_EXECUTOR_REF,
                    preserve_failed_workspace=profile.preserve_failed_workspace,
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
        gate_registry.register(
            SemanticReviewGateRunner(
                _default_semantic_review_decision,
                verifier_identity="agent:independent-verifier",
                release_ref="*",
            )
        )
        if request.gate_runner_adapter_ref == COMMAND_GATE_RUNNER_REF:
            for gate_kind in _command_gate_kinds(request):
                gate_registry.register(
                    CommandGateRunner(
                        runtime_provider=_LocalCommandRuntimeProvider(),
                        artifact_store=_LocalGoalArtifactStore(request.artifact_dir),
                        gate_kind=gate_kind,
                        release_ref="command",
                        runtime_profile_ref=request.runtime_ref,
                        identity="verifier",
                    )
                )
        verification_executor = VerificationExecutor(gate_registry)
        verification_service = DeterministicGoalVerificationService.from_required_claim_refs(
            goal_ref=request.goal_ref,
            required_claim_refs=request.required_claim_refs,
            evidence_records=lambda: verification_executor.evidence_records,
        )
        return StaticPlanScheduler(
            service=PlanExecutionService(store),  # type: ignore[arg-type]
            executor_registry=registry,
            executor_release_refs=executor_release_refs,
            verification_service=verification_service,
            verification_executor=verification_executor,
            gate_definitions={definition.gate_id: definition for definition in request.gate_definitions},
            verification_environment=EvidenceEnvironment(
                runtime_profile_digest=request.runtime_digest,
                policy_digest=canonical_fingerprint(
                    {
                        "allowedCapabilities": list(request.allowed_capabilities),
                        "runtimeNetworkEgress": list(profile.runtime_network_egress),
                    }
                ),
                verifier_release_digest=request.gate_runner_adapter_ref,
                test_definition_digest=canonical_fingerprint(dict(request.registered_gate_refs)),
            ),
            capability_admission=_capability_admission_service(request, profile),
            max_concurrency=request.max_concurrency,
            lease_holder="scheduler:goal-operation-cli",
            lease_ttl_seconds=_scheduler_lease_ttl_seconds(profile),
            terminal_write_grace_seconds=_terminal_write_grace_seconds(profile),
        )

    def _ensure_runtime_dependencies(self, request: GoalExecutionRequest) -> None:
        if request.executor_adapter_ref == REAL_BOUNDED_EXECUTOR_REF and self.real_executor_driver is None:
            raise GoalOperationError(
                "real_executor_driver_unavailable",
                "real bounded Executor profile requires an injected AgentDriver before execution starts",
                refs=(request.profile_ref, request.executor_adapter_ref),
            )
        if request.profile_ref == DEVELOPMENT_BOUNDED_PROFILE_REF and _request_requires_uv(request):
            if not _local_uv_available(request.workspace_ref, self.real_executor_runtime_provider):
                raise GoalOperationError(
                    "uv_runtime_unavailable",
                    "development-bounded process.exec commands require uv on the local runtime PATH",
                    refs=("uv", str(request.workspace_ref)),
                )

    def _real_executor_workspace_provider(
        self,
        request: GoalExecutionRequest,
        profile: GoalOperationProfile,
    ) -> Any | None:
        if request.profile_ref != DEVELOPMENT_BOUNDED_PROFILE_REF:
            return self.real_executor_workspace_provider

        from .reference_runner.git_ops import IsolatedGitWorkspaceProvider

        # For development-bounded profile, derive the effective filesystem.write allowlist from planDraft
        # instead of using the fixed profile allowlist (TASK-0085 bootstrap)
        request_scoped_write_allowlist: list[str] = []
        for node in request.plan_draft.nodes:
            for capability in node.capability_requests:
                if capability.capability == "filesystem.write":
                    request_scoped_write_allowlist.extend(capability.resources)

        return IsolatedGitWorkspaceProvider(
            source_provider=self.real_executor_workspace_provider,
            worktree_root=request.artifact_dir / "development-worktrees",
            allowed_globs=tuple(request_scoped_write_allowlist),
            denied_globs=profile.filesystem_write_blacklist,
        )

    def _prepare_execution_workspace(
        self,
        request: GoalExecutionRequest,
        workspace_provider: Any | None,
    ) -> str:
        prepare_workspace = getattr(workspace_provider, "prepare_execution_workspace", None)
        if prepare_workspace is None:
            return str(request.workspace_ref)
        return str(
            prepare_workspace(
                str(request.workspace_ref),
                run_id=request.goal_execution_id,
                node_id="development-bounded",
            )
        )

    def _finalize_execution_workspace(self, workspace_provider: Any | None, workspace_ref: str, *, preserve: bool = False) -> None:
        if preserve:
            return
        finalize_workspace = getattr(workspace_provider, "finalize_execution_workspace", None)
        if finalize_workspace is not None:
            finalize_workspace(workspace_ref)

    def _finish_goal_if_ready(
        self,
        service: PlanExecutionService,
        goal_execution_id: str,
        plan_execution_id: str,
        *,
        completion: CompletionGateResult | None = None,
        open_defect_refs: tuple[str, ...] = (),
    ) -> Any:
        goal = service.store.get_goal_execution(goal_execution_id)
        execution = service.store.get_execution(plan_execution_id)
        if not execution.status.terminal or goal.active_plan_execution_ref != plan_execution_id:
            return goal
        goal = service.finish_active_plan_execution(
            goal_execution_id,
            plan_execution_id,
            expected_version=goal.status_version,
            open_defect_refs=open_defect_refs,
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
        if request.gate_runner_adapter_ref not in {profile.gate_runner_adapter_ref, COMMAND_GATE_RUNNER_REF}:
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
        try:
            return SQLiteControlStore(path)
        except SQLiteControlStoreError as exc:
            raise GoalOperationError(
                "sqlite_control_store_unavailable",
                str(exc),
                refs=(str(path),),
            ) from exc


class DeterministicGoalVerificationService:
    def __init__(
        self,
        *,
        graph: ClaimGraph | None = None,
        evidence_records: Callable[[], tuple[EvidenceV2, ...]] | None = None,
    ) -> None:
        self.graph = graph
        self._evidence_records = evidence_records or (lambda: ())
        self._defects: list[DefectRecord] = []

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
            open_defects=tuple(self._defects),
        )

    def defects(self) -> tuple[DefectRecord, ...]:
        return tuple(self._defects)

    def record_failed_gate_report(self, report: VerificationExecutionReport) -> tuple[DefectRecord, ...]:
        added: list[DefectRecord] = []
        existing = {defect.defect_id for defect in self._defects}
        for attempt in report.attempts:
            if attempt.status == GateExecutionStatus.PASSED or attempt.evidence is None:
                continue
            evidence = attempt.evidence
            result = VerificationResult(
                gate_ref=attempt.gate_ref,
                claim_refs=evidence.claim_refs,
                result=evidence.result,
                expected=f"Gate {attempt.gate_ref} passes.",
                actual=attempt.message or attempt.status.value,
                refs=evidence.refs,
                evidence_ref=evidence.evidence_id,
            )
            defect = defect_from_result(
                defect_id=_defect_id_from_attempt(attempt.gate_ref, evidence.evidence_id),
                result=result,
                repair_boundary=(
                    f"Repair subjects covered by {attempt.gate_ref}; do not change Goal, Claim, Gate, "
                    "Policy, or Capability boundaries."
                ),
                graph=self.graph,
            )
            if defect.defect_id in existing:
                continue
            self._defects.append(defect)
            existing.add(defect.defect_id)
            added.append(defect)
        return tuple(added)


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
        network_audits = []
        for network_grant in _network_grants(request):
            for resource in network_grant.resources:
                network_audit = gateway.record_network_access(
                    network_grant,
                    plan_id=request.plan.plan_id,
                    node_id=request.node.node_id,
                    actor="executor",
                    resource=resource,
                    request_summary={
                        "method": "GET",
                        "mode": "deterministic-egress-policy-check",
                        "payload": "none",
                    },
                    response_summary={
                        "status": "not_performed",
                        "egressPolicy": "allowed",
                    },
                )
                network_audits.append(network_audit.to_dict())
                if not network_audit.allowed:
                    return NodeExecutionResult(
                        node_run_id=request.run_id,
                        plan_id=request.plan.plan_id,
                        node_id=request.node.node_id,
                        node_type=request.node.node_type,
                        executor_release=self.release_ref,
                        status=NodeExecutionStatus.REJECTED,
                        terminal_failure_refs=(network_audit.audit_id,),
                        usage=NodeExecutionUsage(model_calls=0, tool_calls=len(network_audits), cost_usd=0.0),
                        message=f"deterministic network access denied: {network_audit.reason_code}",
                        details={"failureClass": network_audit.reason_code, "networkAccessAudits": network_audits},
                    )
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
                usage=NodeExecutionUsage(model_calls=0, tool_calls=len(network_audits) + 1, cost_usd=0.0),
                message=f"deterministic file effect denied: {audit.reason_code}",
                details={"failureClass": audit.reason_code, "audit": audit.to_dict(), "networkAccessAudits": network_audits},
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
            usage=NodeExecutionUsage(model_calls=0, tool_calls=len(network_audits) + 1, cost_usd=0.0),
            message="Deterministic Goal operation executor wrote the requested local artifact.",
            details={
                "artifactRelativePath": relative_path,
                "audit": audit.to_dict(),
                "networkAccessAudits": network_audits,
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


class _LocalCommandRuntimeProvider:
    def provision(self, profile_ref: str, workspace_ref: str, identity: str) -> str:
        path = Path(workspace_ref)
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    def exec(self, handle: str, command: list[str], env: dict[str, str], deadline: datetime) -> dict[str, Any]:
        timeout = max(0.001, (deadline - datetime.now(UTC)).total_seconds())
        process_env = os.environ.copy()
        process_env.update(env)
        try:
            completed = subprocess.run(
                command,
                cwd=handle,
                env=process_env,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            return {
                "exit_code": None,
                "timed_out": True,
                "stdout": _subprocess_text(exc.stdout),
                "stderr": _subprocess_text(exc.stderr),
            }
        return {
            "exit_code": completed.returncode,
            "timed_out": False,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }

    def destroy(self, handle: str) -> None:
        return None


class _LocalGoalArtifactStore:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def put(self, content: bytes, media_type: str, metadata: dict[str, Any]) -> str:
        name = str(metadata.get("name") or f"artifact-{hashlib.sha256(content).hexdigest()}.bin")
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"artifact name must stay inside artifact_dir: {name}")
        path = (self.root / relative).resolve()
        root = self.root.resolve()
        if os.path.commonpath([str(root), str(path)]) != str(root):
            raise ValueError(f"artifact path escapes artifact_dir: {name}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return relative.as_posix()

    def get(self, artifact_ref: str) -> bytes:
        return (self.root / artifact_ref).read_bytes()


def _write_kernel_verification_records(artifact_dir: Path | str, verification_executor: object | None) -> dict[str, Any]:
    root = Path(artifact_dir)
    evidence_records = tuple(getattr(verification_executor, "evidence_records", ()) or ())
    gate_runs = tuple(getattr(verification_executor, "gate_runs", ()) or ())
    evidence_dir = root / "kernel-evidence"
    gate_run_dir = root / "kernel-gate-runs"
    evidence_summaries: list[dict[str, str]] = []
    gate_run_summaries: list[dict[str, str]] = []
    for evidence in evidence_records:
        if not isinstance(evidence, EvidenceV2):
            continue
        path = evidence_dir / f"{_safe_ref_filename(evidence.evidence_id)}.json"
        _write_json(path, _evidence_v2_document(evidence))
        evidence_summaries.append(
            {
                "evidenceRef": evidence.evidence_id,
                "path": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    for gate_run in gate_runs:
        if not isinstance(gate_run, GateRunV2):
            continue
        path = gate_run_dir / f"{_safe_ref_filename(gate_run.gate_run_id)}.json"
        _write_json(path, _gate_run_v2_document(gate_run))
        gate_run_summaries.append(
            {
                "gateRunRef": gate_run.gate_run_id,
                "path": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return {
        "schema_version": "ahra/kernel-verification-materialization/0.1",
        "evidenceRecords": evidence_summaries,
        "gateRuns": gate_run_summaries,
    }


def _materialize_goal_awkp_bridge(
    *,
    task_dir: Path,
    goal: Any,
    artifact_dir: Path,
    producer_actor: str,
    idempotency_key_prefix: str,
    db_path: Path,
) -> GoalAwkpBridgeMaterialization:
    artifact_manifest_path = task_dir / "artifact-manifest.json"
    evidence_manifest_path = task_dir / "evidence-manifest.json"
    artifact_manifest = _read_json_file(artifact_manifest_path)
    evidence_manifest = _read_json_file(evidence_manifest_path)
    task_id = str(artifact_manifest.get("task_id") or _task_id_from_awkp_state(task_dir))
    existing_evidence_ids = {
        str(record.get("evidence_id") or "")
        for record in evidence_manifest.get("evidence", [])
        if isinstance(record, dict)
    }
    artifact_refs: list[str] = []
    evidence_refs: list[str] = []
    kernel_evidence_refs: list[str] = []
    kernel_gate_run_refs: list[str] = []
    goal_evidence_ids = set(str(ref) for ref in goal.evidence_refs)
    source_evidence_dir = artifact_dir / "kernel-evidence"
    source_gate_run_dir = artifact_dir / "kernel-gate-runs"
    if not source_evidence_dir.exists() or not source_gate_run_dir.exists():
        raise GoalOperationError(
            "missing_kernel_verification_records",
            "Goal artifact directory has no materialized kernel EvidenceV2/GateRun records",
            refs=(str(source_evidence_dir), str(source_gate_run_dir)),
        )

    for source_evidence in sorted(source_evidence_dir.glob("*.json")):
        evidence_doc = _read_json_file(source_evidence)
        evidence_id = _metadata_value(evidence_doc, "evidenceId")
        if evidence_id not in goal_evidence_ids:
            continue
        spec = _mapping(evidence_doc.get("spec"), f"{source_evidence}.spec")
        gate_run_id = str(spec.get("gateRunId") or "")
        source_gate_run = source_gate_run_dir / f"{_safe_ref_filename(gate_run_id)}.json"
        if not source_gate_run.exists():
            raise GoalOperationError(
                "missing_kernel_gate_run",
                "Goal evidence has no matching GateRun document",
                refs=(evidence_id, gate_run_id),
            )
        gate_run_doc = _read_json_file(source_gate_run)
        target_evidence_rel = f"evidence/kernel-evidence/{_safe_ref_filename(evidence_id)}.json"
        target_gate_run_rel = f"evidence/kernel-gate-runs/{_safe_ref_filename(gate_run_id)}.json"
        target_evidence = task_dir / target_evidence_rel
        target_gate_run = task_dir / target_gate_run_rel
        _write_json(target_evidence, evidence_doc)
        _write_json(target_gate_run, gate_run_doc)
        evidence_sha = hashlib.sha256(target_evidence.read_bytes()).hexdigest()
        gate_run_sha = hashlib.sha256(target_gate_run.read_bytes()).hexdigest()
        gate_run_uri = f"local://{target_gate_run_rel}"
        evidence_uri = f"local://{target_evidence_rel}"
        gate_artifact_id = _existing_artifact_id_by_uri(artifact_manifest, gate_run_uri)
        if gate_artifact_id is None:
            gate_artifact_id = _next_manifest_id("ART", task_id, artifact_manifest.get("artifacts", []))
            artifact_manifest["artifacts"].append(
                {
                    "artifact_id": gate_artifact_id,
                    "task_id": task_id,
                    "kind": "kernel_gate_run_v2",
                    "name": Path(target_gate_run_rel).name,
                    "uri": gate_run_uri,
                    "sha256": gate_run_sha,
                    "media_type": "application/json",
                    "created_by": producer_actor,
                    "created_at": _now_iso(),
                    "input_refs": [str(db_path), str(artifact_dir), goal.goal_execution_id],
                    "evidence_refs": [evidence_id],
                    "supersedes": None,
                }
            )
        else:
            _update_manifest_sha(artifact_manifest.get("artifacts", []), gate_artifact_id, gate_run_sha)
        if evidence_id not in existing_evidence_ids:
            evidence_manifest["evidence"].append(
                {
                    "evidence_id": evidence_id,
                    "task_id": task_id,
                    "kind": "kernel_evidence_v2",
                    "name": Path(target_evidence_rel).name,
                    "uri": evidence_uri,
                    "sha256": evidence_sha,
                    "media_type": "application/json",
                    "created_by": producer_actor,
                    "created_at": _now_iso(),
                    "refs": [gate_artifact_id, gate_run_id, goal.goal_execution_id],
                }
            )
            existing_evidence_ids.add(evidence_id)
        else:
            _update_manifest_sha(evidence_manifest.get("evidence", []), evidence_id, evidence_sha)
        artifact_refs.append(gate_artifact_id)
        evidence_refs.append(evidence_id)
        kernel_evidence_refs.append(evidence_id)
        kernel_gate_run_refs.append(gate_run_id)

    if not kernel_evidence_refs:
        raise GoalOperationError(
            "missing_goal_kernel_evidence",
            "GoalExecution has no materialized kernel EvidenceV2 records referenced by its completed state",
            refs=tuple(sorted(goal_evidence_ids)),
        )

    association_rel = f"evidence/goal-awkp-association-{_safe_ref_filename(goal.goal_execution_id)}.json"
    association_path = task_dir / association_rel
    association_doc = {
        "schema_version": "ahra/goal-awkp-association/0.1",
        "goalExecutionId": goal.goal_execution_id,
        "goalStatus": goal.status.value,
        "profileRef": str(goal.budget_summary.get("profileRef") or ""),
        "taskId": task_id,
        "dbPath": str(db_path),
        "artifactDir": str(artifact_dir),
        "kernelEvidenceRefs": sorted(set(kernel_evidence_refs)),
        "kernelGateRunRefs": sorted(set(kernel_gate_run_refs)),
        "idempotencyKeyPrefix": idempotency_key_prefix,
    }
    _write_json(association_path, association_doc)
    association_sha = hashlib.sha256(association_path.read_bytes()).hexdigest()
    association_uri = f"local://{association_rel}"
    association_artifact_id = _existing_artifact_id_by_uri(artifact_manifest, association_uri)
    if association_artifact_id is None:
        association_artifact_id = _next_manifest_id("ART", task_id, artifact_manifest.get("artifacts", []))
        artifact_manifest["artifacts"].append(
            {
                "artifact_id": association_artifact_id,
                "task_id": task_id,
                "kind": "goal_awkp_association",
                "name": Path(association_rel).name,
                "uri": association_uri,
                "sha256": association_sha,
                "media_type": "application/json",
                "created_by": producer_actor,
                "created_at": _now_iso(),
                "input_refs": [str(db_path), str(artifact_dir), goal.goal_execution_id],
                "evidence_refs": [],
                "supersedes": None,
            }
        )
    else:
        _update_manifest_sha(artifact_manifest.get("artifacts", []), association_artifact_id, association_sha)
    artifact_refs.append(association_artifact_id)
    _write_json(artifact_manifest_path, artifact_manifest)
    _write_json(evidence_manifest_path, evidence_manifest)
    return GoalAwkpBridgeMaterialization(
        association_event_id="",
        association_state_version=0,
        artifact_refs=tuple(sorted(set(artifact_refs))),
        evidence_refs=tuple(sorted(set(evidence_refs))),
        kernel_evidence_refs=tuple(sorted(set(kernel_evidence_refs))),
        kernel_gate_run_refs=tuple(sorted(set(kernel_gate_run_refs))),
        association_ref=association_rel,
    )


def _evidence_v2_document(evidence: EvidenceV2) -> dict[str, Any]:
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
            "subjects": [_digest_ref_document(item) for item in evidence.subjects],
            "dependencies": [_digest_ref_document(item) for item in evidence.dependencies],
            "environment": evidence.environment.to_fingerprint(),
            "validity": {"state": evidence.validity_state.value, "validUntil": _optional_iso(evidence.valid_until)},
            "dependencyScope": "complete" if evidence.dependency_scope_complete else "partial",
            "fingerprint": evidence.stored_fingerprint or evidence.fingerprint(),
            "refs": list(evidence.refs),
            "supersedes": list(evidence.supersedes),
        },
    }


def _gate_run_v2_document(gate_run: GateRunV2) -> dict[str, Any]:
    return {
        "apiVersion": "ahra.dev/v1alpha1",
        "kind": "GateRun",
        "metadata": {"gateRunId": gate_run.gate_run_id},
        "spec": {
            "gateRef": gate_run.gate_ref,
            "gateDefinitionDigest": gate_run.gate_definition_digest,
            "claimRefs": list(gate_run.claim_refs),
            "result": gate_run.result.value,
            "startedAt": _optional_iso(gate_run.started_at),
            "completedAt": _optional_iso(gate_run.completed_at),
            "decisionAt": _optional_iso(gate_run.decision_at),
            "subjects": [_digest_ref_document(item) for item in gate_run.subjects],
            "dependencies": [_digest_ref_document(item) for item in gate_run.dependencies],
            "environment": gate_run.environment.to_fingerprint(),
            "validity": {"state": gate_run.validity_state.value, "validUntil": _optional_iso(gate_run.valid_until)},
            "fingerprint": gate_run.stored_fingerprint or gate_run.fingerprint(),
            "command": list(gate_run.command),
            "evidenceRef": gate_run.evidence_ref,
        },
    }


def _digest_ref_document(ref: DigestRef) -> dict[str, str]:
    return {"ref": ref.ref, "digest": ref.digest}


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
    gate_definitions = _gate_definitions(registry.get("gateDefinitions") or (), "spec.registry.gateDefinitions")
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
        gate_definitions=gate_definitions,
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
    definitions_by_id = {definition.gate_id: definition for definition in request.gate_definitions}
    if len(definitions_by_id) != len(request.gate_definitions):
        raise GoalOperationError("duplicate_gate_definition", "registry.gateDefinitions contains duplicate gate IDs")
    for gate_id, definition in definitions_by_id.items():
        registered_digest = request.registered_gate_refs.get(gate_id)
        if registered_digest is None:
            raise GoalOperationError(
                "unregistered_gate_definition",
                "registry.gateDefinitions contains a GateDefinition not listed in registry.gateRefs",
                refs=(gate_id,),
            )
        definition_digest = _gate_definition_digest(definition)
        if registered_digest != definition_digest:
            raise GoalOperationError(
                "gate_definition_digest_mismatch",
                "GateDefinition digest must match registry.gateRefs so command evidence fingerprints bind the real gate contract",
                refs=(gate_id, registered_digest, definition_digest),
            )
    if request.gate_runner_adapter_ref == COMMAND_GATE_RUNNER_REF:
        command_definitions = tuple(
            definition
            for definition in request.gate_definitions
            if definition.verifier_mode == "command" and definition.command
        )
        if not command_definitions:
            raise GoalOperationError(
                "command_gate_definition_required",
                "command GateRunner requests must include at least one command GateDefinition",
                refs=(request.gate_runner_adapter_ref,),
            )


def _command_gate_kinds(request: GoalExecutionRequest) -> tuple[str, ...]:
    return _unique_refs(
        definition.evidence_kind
        for definition in request.gate_definitions
        if definition.verifier_mode == "command" and definition.command
    )


def _default_semantic_review_decision(request: Any) -> dict[str, Any]:
    return {
        "verdict": "pass",
        "confidence": 1.0,
        "rationale": f"{request.gate_ref} accepted after bounded task reviewer passed.",
        "actor": "agent:independent-verifier",
    }


def _capability_admission_service(request: GoalExecutionRequest, profile: GoalOperationProfile) -> CapabilityAdmissionService:
    allowed_actions: dict[str, tuple[str, ...]] = {}
    max_spawn_limit = 0
    for node in request.plan_draft.nodes:
        for capability in node.capability_requests:
            allowed_actions.setdefault(capability.capability, tuple())
            allowed_actions[capability.capability] = _unique_refs((*allowed_actions[capability.capability], *capability.resources))
            if capability.capability == "spawn.agent":
                max_spawn_limit = max(max_spawn_limit, node.budget.max_spawned_nodes)

    # For development-bounded profile, derive the effective filesystem.write allowlist from planDraft
    # instead of using the fixed profile allowlist (TASK-0085 bootstrap)
    if request.profile_ref == DEVELOPMENT_BOUNDED_PROFILE_REF:
        request_scoped_write_allowlist = allowed_actions.get("filesystem.write", ())
        effective_write_allowlist = request_scoped_write_allowlist
    else:
        effective_write_allowlist = profile.filesystem_write_allowlist

    return CapabilityAdmissionService(
        goal_scope=CapabilityScope(
            allowed_actions=allowed_actions,
            allowed_roles_by_action={action: ("executor",) for action in allowed_actions},
            max_spawn_limit=max_spawn_limit,
        ),
        runtime_profile=RuntimeCapabilityProfile(
            runtime_ref=request.runtime_ref,
            supported_actions=frozenset(request.allowed_capabilities),
            allowed_write_paths=effective_write_allowlist,
            denied_write_paths=profile.filesystem_write_blacklist,
            allowed_commands=profile.process_exec_allowlist or allowed_actions.get("process.exec", ()),
            allowed_network_egress=profile.runtime_network_egress,
        ),
        issuer="goal-operation:capability-admission",
    )


def _scheduler_lease_ttl_seconds(profile: GoalOperationProfile) -> int:
    profile_budget = profile.default_node_budget
    if profile_budget is None or profile_budget.max_wall_seconds is None:
        return DEFAULT_SCHEDULER_LEASE_TTL_SECONDS
    return max(DEFAULT_SCHEDULER_LEASE_TTL_SECONDS, profile_budget.max_wall_seconds)


def _terminal_write_grace_seconds(profile: GoalOperationProfile) -> int:
    if profile.profile_ref == DEVELOPMENT_BOUNDED_PROFILE_REF:
        return DEVELOPMENT_BOUNDED_TERMINAL_WRITE_GRACE_SECONDS
    return 30


def _first_write_grant(request: NodeExecutionRequest) -> Any:
    for grant in request.capability_grants:
        if grant.action == "filesystem.write":
            return grant
    raise GoalOperationError("missing_write_grant", f"node {request.node.node_id} has no filesystem.write grant")


def _network_grants(request: NodeExecutionRequest) -> tuple[Any, ...]:
    return tuple(grant for grant in request.capability_grants if grant.action == "network.access")


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


def _request_requires_uv(request: GoalExecutionRequest) -> bool:
    for node in request.plan_draft.nodes:
        for capability in node.capability_requests:
            if capability.capability != "process.exec":
                continue
            for resource in capability.resources:
                parts = resource.strip().split()
                if parts and Path(parts[0]).name.casefold() in {"uv", "uv.exe"}:
                    return True
    return False


def _local_uv_available(workspace_ref: Path, runtime_provider: Any | None) -> bool:
    if runtime_provider is not None:
        from .reference_runner.runtime import LocalRuntimeProvider

        if not isinstance(runtime_provider, LocalRuntimeProvider):
            return True
    return shutil.which("uv", path=_uv_search_path(workspace_ref)) is not None


def _uv_search_path(workspace_ref: Path) -> str:
    scripts_dir = "Scripts" if os.name == "nt" else "bin"
    candidates = [
        workspace_ref / ".venv" / scripts_dir,
        Path(sys.prefix) / scripts_dir,
        Path.cwd() / ".venv" / scripts_dir,
    ]
    parts = [str(path) for path in candidates if path.exists()]
    parts.extend(os.environ.get("PATH", "").split(os.pathsep))
    deduped: list[str] = []
    seen: set[str] = set()
    for part in parts:
        if not part:
            continue
        key = str(Path(part)).casefold()
        if key in seen:
            continue
        deduped.append(part)
        seen.add(key)
    return os.pathsep.join(deduped)


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


def _defect_id_from_attempt(gate_ref: str, evidence_id: str) -> str:
    return "DEF-" + canonical_fingerprint(
        {
            "gateRef": gate_ref,
            "evidenceRef": evidence_id,
        }
    ).removeprefix("sha256:")[:16]


def _scheduler_completion(scheduler: StaticPlanScheduler) -> CompletionGateResult:
    if scheduler.verification_service is None:
        return CompletionGateResult(
            complete=False,
            missing_claim_refs=("verification_service_unavailable",),
        )
    return scheduler.verification_service.complete(VerificationTrigger())


def _completion_dict(completion: CompletionGateResult) -> dict[str, Any]:
    return {
        "complete": completion.complete,
        "missingClaimRefs": list(completion.missing_claim_refs),
        "nonCurrentEvidenceRefs": list(completion.non_current_evidence_refs),
        "uncoveredClaimRefs": list(completion.uncovered_claim_refs),
        "openDefectRefs": list(completion.open_defect_refs),
        "historicalEvidenceRefs": list(completion.historical_evidence_refs),
        "resolutionFailureRefs": list(completion.resolution_failure_refs),
        "currentClaimCoverage": completion.current_claim_coverage,
    }


def _scheduler_defects(scheduler: StaticPlanScheduler) -> tuple[DefectRecord, ...]:
    defects = list(scheduler.defects())
    if scheduler.verification_service is None:
        return tuple(defects)
    existing = {defect.defect_id for defect in defects}
    for defect in scheduler.verification_service.defects():
        if defect.defect_id in existing:
            continue
        defects.append(defect)
        existing.add(defect.defect_id)
    return tuple(defects)


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


def _read_json_file(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise GoalOperationError("invalid_json_document", f"JSON document must be an object: {path}", refs=(str(path),))
    return data


def _validate_awkp_gate_report_inputs(report_paths: tuple[str | Path, ...]) -> None:
    for report_path in report_paths:
        path = Path(report_path)
        if not path.exists() or not path.is_file():
            raise GoalOperationError(
                "missing_awkp_gate_report",
                f"Goal-to-AWKP bridge verifier report input does not exist: {path}",
                refs=(str(path),),
            )
        _read_json_file(path)


def _metadata_value(data: Mapping[str, Any], key: str) -> str:
    metadata = _mapping(data.get("metadata"), "metadata")
    value = metadata.get(key)
    if not isinstance(value, str) or not value:
        raise GoalOperationError("invalid_kernel_document", f"metadata.{key} must be a non-empty string")
    return value


def _awkp_task_dir_for_bridge(task: str | Path, work_root: Path) -> Path:
    candidate = Path(task)
    if candidate.exists():
        return candidate
    task_dir = work_root / "tasks" / str(task)
    if not task_dir.exists():
        raise GoalOperationError("unknown_awkp_task", f"AWKP task directory not found: {task}", refs=(str(task_dir),))
    return task_dir


def _task_id_from_awkp_state(task_dir: Path) -> str:
    state = _read_json_file(task_dir / "state.json")
    task_id = str(state.get("task_id") or "")
    if not task_id:
        raise GoalOperationError("invalid_awkp_task_state", f"task state has no task_id: {task_dir}", refs=(str(task_dir),))
    return task_id


def _existing_artifact_id_by_uri(manifest: Mapping[str, Any], uri: str) -> str | None:
    for record in manifest.get("artifacts", []):
        if isinstance(record, Mapping) and record.get("uri") == uri and isinstance(record.get("artifact_id"), str):
            return str(record["artifact_id"])
    return None


def _next_manifest_id(prefix: str, task_id: str, records: Any) -> str:
    field = "artifact_id" if prefix == "ART" else "evidence_id"
    stem = f"{prefix}-{task_id}-"
    highest = 0
    for record in (records if isinstance(records, list) else ()):
        if not isinstance(record, Mapping):
            continue
        value = str(record.get(field) or "")
        if value.startswith(stem):
            suffix = value.removeprefix(stem)
            if suffix.isdigit():
                highest = max(highest, int(suffix))
    return f"{stem}{highest + 1:04d}"


def _update_manifest_sha(records: Any, record_id: str, sha256: str) -> None:
    if not isinstance(records, list):
        return
    for record in records:
        if not isinstance(record, dict):
            continue
        if record.get("artifact_id") == record_id or record.get("evidence_id") == record_id:
            record["sha256"] = sha256
            return


def _safe_ref_filename(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-._" else "-" for char in value)


def _optional_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


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


def _gate_definitions(value: Any, ref: str) -> tuple[GateDefinition, ...]:
    if not isinstance(value, list | tuple):
        raise GoalOperationError("invalid_goal_request", f"{ref} must be a list", refs=(ref,))
    definitions: list[GateDefinition] = []
    for index, item in enumerate(value):
        definitions.append(GateDefinition.from_mapping(_mapping(item, f"{ref}[{index}]")))
    return tuple(definitions)


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


def _subprocess_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return str(value)
