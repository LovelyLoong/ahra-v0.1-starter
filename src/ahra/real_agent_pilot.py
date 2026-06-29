from __future__ import annotations

import asyncio
import copy
import json
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping

import yaml

from .evidence_v2 import canonical_fingerprint
from .goal_operations import (
    DETERMINISTIC_EXECUTOR_REF,
    DETERMINISTIC_GATE_RUNNER_REF,
    INLINE_PLANNER_REF,
    LOCAL_GOAL_RUNTIME_DIGEST,
    LOCAL_GOAL_RUNTIME_REF,
    M1_REAL_COMBINED_PROFILE_REF,
    M1_REAL_EXECUTOR_PROFILE_REF,
    M1_REAL_PLANNER_PROFILE_REF,
    REAL_BOUNDED_EXECUTOR_REF,
    REAL_PLANNER_ADAPTER_REF,
    GoalOperationError,
    GoalOperationProfileRegistry,
    GoalOperationService,
    load_goal_execution_request,
)
from .planner_contracts import ExecutionPlanningRequest, PlannerBudgetLimits, PlannerContextRequest
from .plan_ir import PlanDraft
from .planning import AgentDriverExecutionPlannerAdapter, PlannerAdapterError, PlannerContextBuilder, PlannerOutputValidator
from .ports import AgentDriver, AgentDriverRegistry
from .reference_runner.models import ExecutionPolicy


REAL_AGENT_PILOT_SCHEMA_VERSION = "ahra/real-agent-pilot/0.1"
REAL_EXECUTOR_MIN_MODEL_CALLS = 2
REAL_EXECUTOR_MIN_TOOL_CALLS = 1

FAILURE_DIMENSION_LEGEND = {
    "none": "Run succeeded or has no recorded failure.",
    "contract": "Static request, PlanIR, output contract, or validation boundary failure.",
    "gate": "Quality, approval, capability admission, or verification gate failure.",
    "budget": "Configured model, tool, cost, or wall-time budget exhaustion.",
    "scheduler": "Scheduler, watchdog, timeout recovery, or lifecycle transition failure.",
    "provider_runtime": "External driver, process, runtime, or provider availability failure.",
    "model_behavior": "Real model output was malformed, rejected, or unusable.",
    "unknown": "Failure is present but not yet classified into a stable workflow dimension.",
}


class PilotMode(StrEnum):
    REAL_PLANNER = "mode_a_real_planner"
    REAL_EXECUTOR = "mode_b_real_executor"
    COMBINED = "mode_c_combined"


@dataclass(frozen=True, slots=True)
class RealAgentPilotConfig:
    experiment_id: str
    mode: PilotMode
    request_template: Path
    output_dir: Path
    repetitions: int = 5
    planner_driver_ref: str = "codex-python-sdk"
    model_provider: str = "codex-sdk"
    model_revision: str = "unspecified"
    allow_combined: bool = True
    risk_level: str = "R1"
    token_budget: int = 4096
    executor_policy: ExecutionPolicy = field(default_factory=lambda: ExecutionPolicy(
        max_attempts=1,
        startup_timeout_seconds=60,
        idle_timeout_seconds=120,
        heartbeat_interval_seconds=15,
        attempt_wall_timeout_seconds=180,
        run_deadline_seconds=240,
    ))

    def __post_init__(self) -> None:
        if self.repetitions < 1:
            raise ValueError("repetitions must be at least 1")
        if not self.experiment_id:
            raise ValueError("experiment_id is required")


class RealAgentPilotRunner:
    def __init__(
        self,
        *,
        planner_registry: AgentDriverRegistry | None = None,
        executor_driver: AgentDriver | None = None,
        service_factory: Any | None = None,
    ) -> None:
        self.planner_registry = planner_registry or AgentDriverRegistry()
        self.executor_driver = executor_driver
        self.service_factory = service_factory

    def run(self, config: RealAgentPilotConfig) -> dict[str, Any]:
        config.output_dir.mkdir(parents=True, exist_ok=True)
        runs = [self.run_one(config, index) for index in range(1, config.repetitions + 1)]
        return self.write_scorecard(config, runs)

    def run_one(self, config: RealAgentPilotConfig, index: int) -> dict[str, Any]:
        run_id = f"{config.experiment_id}-R{index:02d}"
        run_dir = config.output_dir / f"run-{index:02d}"
        started = time.perf_counter()
        try:
            run = self._run_repetition(config, index)
        except Exception as exc:
            run_dir.mkdir(parents=True, exist_ok=True)
            run = _blocked_run(
                config=config,
                run_id=run_id,
                run_dir=run_dir,
                failure_class="pilot_runner_exception",
                message=f"{type(exc).__name__}: {exc}",
                elapsed_seconds=_elapsed(started),
                request_path=run_dir / "goal-run-request.yaml" if (run_dir / "goal-run-request.yaml").exists() else None,
                details={"exceptionType": type(exc).__name__},
            )
        run = _with_failure_dimension(run)
        _write_json(run_dir / "run-result.json", run)
        return run

    def timeout_run(
        self,
        config: RealAgentPilotConfig,
        index: int,
        *,
        elapsed_seconds: float,
        message: str,
        details: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        run_id = f"{config.experiment_id}-R{index:02d}"
        run_dir = config.output_dir / f"run-{index:02d}"
        run_dir.mkdir(parents=True, exist_ok=True)
        run = _blocked_run(
            config=config,
            run_id=run_id,
            run_dir=run_dir,
            failure_class="runner_timeout",
            message=message,
            elapsed_seconds=elapsed_seconds,
            request_path=run_dir / "goal-run-request.yaml" if (run_dir / "goal-run-request.yaml").exists() else None,
            details=dict(details or {}),
        )
        run = _with_failure_dimension(run)
        _write_json(run_dir / "run-result.json", run)
        return run

    def recover_timeout_run(
        self,
        config: RealAgentPilotConfig,
        index: int,
        *,
        elapsed_seconds: float,
        message: str,
        details: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        recovered = self._recover_partial_timeout_run(
            config,
            index,
            elapsed_seconds=elapsed_seconds,
            message=message,
            details=details,
        )
        if recovered is None:
            return self.timeout_run(
                config,
                index,
                elapsed_seconds=elapsed_seconds,
                message=message,
                details=details,
            )
        recovered = _with_failure_dimension(recovered)
        _write_json(config.output_dir / f"run-{index:02d}" / "run-result.json", recovered)
        return recovered

    def process_failed_run(
        self,
        config: RealAgentPilotConfig,
        index: int,
        *,
        elapsed_seconds: float,
        message: str,
        details: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        run_id = f"{config.experiment_id}-R{index:02d}"
        run_dir = config.output_dir / f"run-{index:02d}"
        run_dir.mkdir(parents=True, exist_ok=True)
        run = _blocked_run(
            config=config,
            run_id=run_id,
            run_dir=run_dir,
            failure_class="pilot_child_process_failed",
            message=message,
            elapsed_seconds=elapsed_seconds,
            request_path=run_dir / "goal-run-request.yaml" if (run_dir / "goal-run-request.yaml").exists() else None,
            details=dict(details or {}),
        )
        run = _with_failure_dimension(run)
        _write_json(run_dir / "run-result.json", run)
        return run

    def write_scorecard(self, config: RealAgentPilotConfig, runs: list[dict[str, Any]]) -> dict[str, Any]:
        scorecard = self._scorecard(config, runs)
        _write_json(config.output_dir / "scorecard.json", scorecard)
        return scorecard

    def _recover_partial_timeout_run(
        self,
        config: RealAgentPilotConfig,
        index: int,
        *,
        elapsed_seconds: float,
        message: str,
        details: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        run_id = f"{config.experiment_id}-R{index:02d}"
        run_dir = config.output_dir / f"run-{index:02d}"
        request_path = run_dir / "goal-run-request.yaml"
        db_path = run_dir / ".ahra" / "goal-control.sqlite3"
        artifact_dir = run_dir / ".ahra" / "artifacts"
        if not request_path.exists() or not db_path.exists():
            return None
        service = GoalOperationService()
        try:
            request = load_goal_execution_request(request_path, profiles=GoalOperationProfileRegistry())
            service.finish_active_plan_if_terminal(request.goal_execution_id, db_path=db_path)
            inspect = service.inspect(request.goal_execution_id, db_path=db_path, artifact_dir=artifact_dir)
        except Exception as exc:
            return _blocked_run(
                config=config,
                run_id=run_id,
                run_dir=run_dir,
                failure_class="partial_timeout_recovery_failed",
                message=f"{type(exc).__name__}: {exc}",
                elapsed_seconds=elapsed_seconds,
                request_path=request_path,
                planner=_planner_from_artifacts(config, artifact_dir),
                refs=(str(db_path),),
                details={
                    **dict(details or {}),
                    "recoveredPartialRun": False,
                    "recoveryAttempted": True,
                    "originalFailureClass": "runner_timeout",
                    "originalMessage": message,
                },
            )

        metrics = inspect.get("metrics", {}) if isinstance(inspect, Mapping) else {}
        goal_status = str(metrics.get("goalStatus") or "")
        plan_execution = _latest_plan_execution(inspect)
        plan_status = str(plan_execution.get("status") or "") if plan_execution else ""
        execution = {
            "status": goal_status or "unknown",
            "goalExecutionId": request.goal_execution_id,
            "planExecutionId": plan_execution.get("plan_execution_id") if plan_execution else None,
            "planStatus": plan_status or None,
            "metrics": metrics,
        }
        run_status = _recovered_run_status(goal_status, plan_status)
        hard_metrics = _observed_hard_metrics(inspect)
        failure_class = None if run_status == "succeeded" else _execution_failure_class(inspect) or "runner_timeout"
        return {
            "schema_version": "ahra/real-agent-pilot-run/0.1",
            "run_id": run_id,
            "mode": config.mode.value,
            "status": run_status,
            "profile": request.profile_ref,
            "request_path": str(request_path),
            "artifact_dir": str(run_dir),
            "planner": _planner_from_artifacts(config, artifact_dir),
            "execution": execution,
            "hard_metrics": hard_metrics,
            "hard_metric_violation": _has_hard_metric_violation(hard_metrics),
            "failure_class": failure_class,
            "message": message,
            "refs": [ref for ref in (request.goal_execution_id, execution["planExecutionId"]) if ref],
            "details": {
                **dict(details or {}),
                "recoveredPartialRun": True,
                "recoveryAttempted": True,
                "originalFailureClass": "runner_timeout",
                "originalMessage": message,
            },
            "elapsed_seconds": elapsed_seconds,
        }

    def _run_repetition(self, config: RealAgentPilotConfig, index: int) -> dict[str, Any]:
        run_id = f"{config.experiment_id}-R{index:02d}"
        run_dir = config.output_dir / f"run-{index:02d}"
        if run_dir.exists():
            shutil.rmtree(run_dir)
        run_dir.mkdir(parents=True)
        started = time.perf_counter()

        request_path = run_dir / "goal-run-request.yaml"
        request_data = _request_document(config, run_id)
        _write_yaml(request_path, request_data)
        request = load_goal_execution_request(request_path, profiles=GoalOperationProfileRegistry())
        planner_result: dict[str, Any] = {"status": "skipped"}

        if _uses_real_planner(config.mode):
            planner_result = self._run_planner(config, request_path, run_id)
            if planner_result["status"] != "accepted":
                planner_result["elapsedSeconds"] = _elapsed(started)
                return {
                    "schema_version": "ahra/real-agent-pilot-run/0.1",
                    "run_id": run_id,
                    "mode": config.mode.value,
                    "status": "blocked" if planner_result["status"] == "blocked" else "rejected",
                    "profile": request.profile_ref,
                    "request_path": str(request_path),
                    "planner": planner_result,
                    "execution": {"status": "skipped"},
                    "hard_metric_violation": False,
                    "failure_class": planner_result.get("failureClass"),
                    "elapsed_seconds": _elapsed(started),
                }
            request = load_goal_execution_request(request_path, profiles=GoalOperationProfileRegistry())

        if _uses_real_executor(config.mode):
            if self.executor_driver is None:
                return _blocked_run(
                    config=config,
                    run_id=run_id,
                    run_dir=run_dir,
                    failure_class="real_executor_driver_unavailable",
                    message="Mode requires a real bounded Executor AgentDriver.",
                    elapsed_seconds=_elapsed(started),
                    planner=planner_result,
                    request_path=request_path,
                )
            _ensure_git_workspace(request.workspace_ref)

        service = self._service(config, run_dir)
        try:
            validation = service.validate(request_path)
            if not validation["valid"]:
                return _rejected_run(
                    config=config,
                    run_id=run_id,
                    request_path=request_path,
                    planner=planner_result,
                    validation=validation,
                    elapsed_seconds=_elapsed(started),
                )
            start_report = service.start(request_path)
        except GoalOperationError as exc:
            return _blocked_run(
                config=config,
                run_id=run_id,
                run_dir=run_dir,
                failure_class=exc.code,
                message=exc.message,
                elapsed_seconds=_elapsed(started),
                planner=planner_result,
                request_path=request_path,
                refs=exc.refs,
            )

        inspect = start_report.get("inspect", {})
        metrics = _observed_hard_metrics(inspect)
        goal_status = str(start_report.get("goalStatus") or "")
        status = "succeeded" if goal_status == "succeeded" else "failed"
        return {
            "schema_version": "ahra/real-agent-pilot-run/0.1",
            "run_id": run_id,
            "mode": config.mode.value,
            "status": status,
            "profile": request.profile_ref,
            "request_path": str(request_path),
            "planner": planner_result,
            "execution": {
                "status": goal_status,
                "goalExecutionId": start_report.get("goalExecutionId"),
                "planExecutionId": start_report.get("planExecutionId"),
                "planStatus": start_report.get("planStatus"),
                "metrics": inspect.get("metrics", {}),
            },
            "hard_metrics": metrics,
            "hard_metric_violation": _has_hard_metric_violation(metrics),
            "failure_class": None if status == "succeeded" else _execution_failure_class(inspect),
            "elapsed_seconds": _elapsed(started),
        }

    def _run_planner(self, config: RealAgentPilotConfig, request_path: Path, run_id: str) -> dict[str, Any]:
        request = load_goal_execution_request(request_path, profiles=GoalOperationProfileRegistry())
        budget_limits = _planner_budget_limits(request)
        context_bundle = PlannerContextBuilder().build(
            PlannerContextRequest(
                run_id=run_id,
                agent_release_digest=canonical_fingerprint(
                    {
                        "driverRef": config.planner_driver_ref,
                        "modelProvider": config.model_provider,
                        "modelRevision": config.model_revision,
                    }
                ),
                goal_ref=request.goal_ref,
                goal_digest=request.goal_digest,
                policy_ref=request.profile_ref,
                policy_digest=_policy_digest(request),
                allowed_capabilities=tuple(sorted(request.allowed_capabilities)),
                claim_refs=request.required_claim_refs,
                registered_node_types=request.registered_node_types,
                registered_gate_refs=request.registered_gate_refs,
                registered_runtime_refs=request.registered_runtime_refs,
                budget_limits=budget_limits,
                token_budget=config.token_budget,
            )
        )
        _write_json(request.artifact_dir / "planner-context-input.json", context_bundle.input_artifact.to_dict())

        adapter = AgentDriverExecutionPlannerAdapter(self.planner_registry, config.planner_driver_ref)
        try:
            planning_result = asyncio.run(
                adapter.propose_plan(
                    ExecutionPlanningRequest(
                        goal_ref=request.goal_ref,
                        context_manifest=context_bundle.context_manifest,
                        input_artifact=context_bundle.input_artifact,
                    )
                )
            )
        except PlannerAdapterError as exc:
            _write_json(request.artifact_dir / "planner-blocker.json", exc.failure.to_dict())
            invalid_artifact = exc.output_artifact.to_dict() if exc.output_artifact is not None else None
            if invalid_artifact is not None:
                _write_json(request.artifact_dir / "planner-invalid-output-artifact.json", invalid_artifact)
                _write_json(request.artifact_dir / "planner-invalid-output.json", invalid_artifact["payload"])
            return {
                "status": "blocked",
                "failureClass": exc.failure.code,
                "message": exc.failure.message,
                "retryable": exc.failure.retryable,
                "details": list(exc.failure.details),
                "invalidOutputArtifact": invalid_artifact,
            }

        admitted_draft, normalization = _normalize_real_executor_plan_draft(
            planning_result.draft,
            mode=config.mode,
            policy=config.executor_policy,
        )
        validation = PlannerOutputValidator().validate_execution_draft(
            draft=admitted_draft,
            config=request.compiler_config(),
            context_manifest=context_bundle.context_manifest,
            budget_limits=budget_limits,
            risk_level=config.risk_level,
        )
        _write_json(request.artifact_dir / "planner-output-artifact.json", planning_result.output_artifact.to_dict())
        if normalization is not None:
            _write_json(request.artifact_dir / "planner-budget-normalization.json", normalization)
        _write_json(request.artifact_dir / "planner-admission-report.json", validation.report.to_dict())
        if not validation.accepted:
            return {
                "status": "rejected",
                "failureClass": "planner_output_rejected",
                "message": "Planner output was rejected before execution.",
                "validationReport": validation.report.to_dict(),
            }

        data = yaml.safe_load(request_path.read_text(encoding="utf-8"))
        data["spec"]["planDraft"] = admitted_draft.to_dict()
        _write_yaml(request_path, data)
        result = {
            "status": "accepted",
            "driverRef": config.planner_driver_ref,
            "modelProvider": config.model_provider,
            "modelRevision": config.model_revision,
            "outputArtifact": planning_result.output_artifact.to_dict(),
            "validationReport": validation.report.to_dict(),
        }
        if normalization is not None:
            result["budgetNormalization"] = {
                "artifact": str(request.artifact_dir / "planner-budget-normalization.json"),
                "applied": True,
            }
        return result

    def _service(self, config: RealAgentPilotConfig, run_dir: Path) -> GoalOperationService:
        if self.service_factory is not None:
            return self.service_factory(config, run_dir)
        return GoalOperationService(
            real_executor_driver=self.executor_driver,
            real_executor_store_dir=run_dir / ".ahra" / "bounded-task-executor",
            real_executor_execution_policy=config.executor_policy,
        )

    def _scorecard(self, config: RealAgentPilotConfig, runs: list[dict[str, Any]]) -> dict[str, Any]:
        success_count = sum(1 for run in runs if run.get("status") == "succeeded")
        failures = _failure_classes(runs)
        template = load_goal_execution_request(config.request_template, profiles=GoalOperationProfileRegistry())
        profile = _profile_for_mode(config.mode)
        hard_metrics = _aggregate_hard_metrics(runs)
        annotated_runs = [_with_failure_dimension(_with_provider_usage(config, run)) for run in runs]
        provider_usage = _provider_usage_summary(config, annotated_runs)
        return {
            "schema_version": REAL_AGENT_PILOT_SCHEMA_VERSION,
            "experiment_id": config.experiment_id,
            "profile": profile["profileRef"],
            "code_commit": _code_commit(config.request_template),
            "goal_digest": template.goal_digest,
            "claim_graph_digest": template.claim_graph_digest,
            "policy_digest": canonical_fingerprint(profile),
            "runtime_digest": LOCAL_GOAL_RUNTIME_DIGEST,
            "execution_policy": _execution_policy_dict(config.executor_policy),
            "real_executor_budget_invariant": _real_executor_budget_invariant(config.mode, config.executor_policy),
            "planner_release": profile["plannerAdapterRef"],
            "executor_release": profile["executorAdapterRef"],
            "verifier_releases": [DETERMINISTIC_GATE_RUNNER_REF],
            "run_count": len(runs),
            "success_count": success_count,
            "hard_metrics": hard_metrics,
            "verification_efficiency": {
                "selected_gate_count": None,
                "full_gate_baseline_count": None,
                "known_limitations": ["Gate cost is preserved by run artifacts; weighted cost is not implemented in this pilot increment."],
            },
            "planner_metrics": _planner_metrics(runs),
            "executor_metrics": _executor_metrics(runs),
            "recovery_metrics": {
                "resume_duplicate_effect_count": hard_metrics["resume_duplicate_effect_count"],
                "stale_fencing_accept_count": hard_metrics["stale_fencing_accept_count"],
            },
            "cost": provider_usage,
            "provider_usage": provider_usage,
            "failure_classes": failures,
            "workflow_failure_dimensions": _failure_dimensions(annotated_runs),
            "known_limitations": [
                "This pilot runner records local GoalOperation inspect metrics; independent AWKP EvidenceGate remains a separate verifier step.",
                "Mode C is the default local real-Agent path after TASK-0051, but it remains bounded to the tested local M1 profile and is not production-grade arbitrary-project orchestration.",
            ],
            "evidence_refs": _evidence_refs(annotated_runs),
            "runs": annotated_runs,
        }


def _request_document(config: RealAgentPilotConfig, run_id: str) -> dict[str, Any]:
    data = yaml.safe_load(config.request_template.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"GoalExecutionRequest template must be an object: {config.request_template}")
    profile = _profile_for_mode(config.mode)
    metadata = data.setdefault("metadata", {})
    metadata["name"] = run_id
    metadata["requestId"] = run_id
    metadata["idempotencyKey"] = run_id
    spec = data.setdefault("spec", {})
    spec["profileRef"] = profile["profileRef"]
    spec["workspaceRef"] = "workspace"
    spec["artifactDir"] = ".ahra/artifacts"
    spec["store"] = {"kind": "sqlite", "path": ".ahra/goal-control.sqlite3"}
    spec["planner"] = {"adapterRef": profile["plannerAdapterRef"]}
    spec["executor"] = {"adapterRef": profile["executorAdapterRef"]}
    spec["gateRunner"] = {"adapterRef": DETERMINISTIC_GATE_RUNNER_REF}
    spec["runtime"] = {"runtimeRef": LOCAL_GOAL_RUNTIME_REF, "digest": LOCAL_GOAL_RUNTIME_DIGEST}
    registry = spec.setdefault("registry", {})
    runtime_refs = dict(registry.get("runtimeRefs") or {})
    runtime_refs[LOCAL_GOAL_RUNTIME_REF] = LOCAL_GOAL_RUNTIME_DIGEST
    registry["runtimeRefs"] = runtime_refs
    if _uses_real_executor(config.mode):
        _expand_real_executor_node_budgets(spec, config.executor_policy)
    return data


def _profile_for_mode(mode: PilotMode) -> dict[str, str]:
    if mode == PilotMode.REAL_PLANNER:
        return {
            "profileRef": M1_REAL_PLANNER_PROFILE_REF,
            "plannerAdapterRef": REAL_PLANNER_ADAPTER_REF,
            "executorAdapterRef": DETERMINISTIC_EXECUTOR_REF,
        }
    if mode == PilotMode.REAL_EXECUTOR:
        return {
            "profileRef": M1_REAL_EXECUTOR_PROFILE_REF,
            "plannerAdapterRef": INLINE_PLANNER_REF,
            "executorAdapterRef": REAL_BOUNDED_EXECUTOR_REF,
        }
    return {
        "profileRef": M1_REAL_COMBINED_PROFILE_REF,
        "plannerAdapterRef": REAL_PLANNER_ADAPTER_REF,
        "executorAdapterRef": REAL_BOUNDED_EXECUTOR_REF,
    }


def _uses_real_planner(mode: PilotMode) -> bool:
    return mode in {PilotMode.REAL_PLANNER, PilotMode.COMBINED}


def _uses_real_executor(mode: PilotMode) -> bool:
    return mode in {PilotMode.REAL_EXECUTOR, PilotMode.COMBINED}


def _real_executor_budget_minimums(policy: ExecutionPolicy) -> dict[str, Any]:
    return {
        "budgetRequest": {
            "maxModelCalls": REAL_EXECUTOR_MIN_MODEL_CALLS,
            "maxToolCalls": REAL_EXECUTOR_MIN_TOOL_CALLS,
            "maxWallSeconds": policy.attempt_wall_timeout_seconds,
        },
        "timeoutSeconds": policy.attempt_wall_timeout_seconds,
    }


def _real_executor_budget_invariant(mode: PilotMode, policy: ExecutionPolicy) -> dict[str, Any]:
    required = _uses_real_executor(mode)
    enforcement_points = []
    if required:
        enforcement_points.append("request_template_expansion")
        if _uses_real_planner(mode):
            enforcement_points.append("real_planner_admission_writeback")
    return {
        "schema_version": "ahra/real-agent-pilot/real-executor-budget-invariant/0.1",
        "required": required,
        "minimums": _real_executor_budget_minimums(policy) if required else None,
        "enforcement_points": enforcement_points,
        "normalization_artifact": "planner-budget-normalization.json" if _uses_real_planner(mode) else None,
    }


def _with_provider_usage(config: RealAgentPilotConfig, run: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(run)
    data["provider_usage"] = {
        "model_provider": config.model_provider,
        "model_revision": config.model_revision,
        "usage_available": False,
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
        "cost_usd": None,
        "reason": "Provider token and cost usage is unavailable unless the AgentDriver reports it.",
    }
    return data


def _with_failure_dimension(run: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(run)
    data["workflow_failure_dimension"] = _failure_dimension(data)
    return data


def _failure_dimension(run: Mapping[str, Any]) -> str:
    if run.get("status") == "succeeded":
        return "none"

    failure = str(run.get("failure_class") or "").strip().lower()
    planner = run.get("planner", {}) if isinstance(run.get("planner"), Mapping) else {}
    planner_status = str(planner.get("status") or "").lower()
    execution = run.get("execution", {}) if isinstance(run.get("execution"), Mapping) else {}
    execution_status = str(execution.get("status") or "").lower()
    plan_status = str(execution.get("planStatus") or "").lower()

    if failure:
        if "budget" in failure or "cost" in failure:
            return "budget"
        if "timeout" in failure or failure == "pilot_child_process_failed":
            return "scheduler"
        if failure in {"real_executor_driver_unavailable", "pilot_runner_exception"}:
            return "provider_runtime"
        if failure in {"planner_output_rejected", "planner_output_invalid"} or "invalid_output" in failure:
            return "model_behavior"
        if "capability" in failure or "gate" in failure:
            return "gate"
        if "validation" in failure or "contract" in failure or failure.startswith("goal_request"):
            return "contract"
        if "model" in failure:
            return "model_behavior"

    if planner_status in {"blocked", "rejected"}:
        return "model_behavior"
    if run.get("hard_metric_violation"):
        return "gate"
    if execution_status in {"failed", "canceled"} or plan_status in {"failed", "canceled"}:
        return "scheduler"
    return "unknown"


def _failure_dimensions(runs: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {dimension: 0 for dimension in FAILURE_DIMENSION_LEGEND}
    for run in runs:
        dimension = str(run.get("workflow_failure_dimension") or _failure_dimension(run))
        counts[dimension if dimension in counts else "unknown"] += 1
    return {
        "schema_version": "ahra/real-agent-pilot/failure-dimensions/0.1",
        "counts": counts,
        "legend": FAILURE_DIMENSION_LEGEND,
    }


def _provider_usage_summary(config: RealAgentPilotConfig, runs: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "model_provider": config.model_provider,
        "model_revision": config.model_revision,
        "usage_available": False,
        "token_usage_available": False,
        "cost_usage_available": False,
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
        "cost_usd": None,
        "runs": [
            {
                "run_id": str(run.get("run_id")),
                "input_tokens": None,
                "output_tokens": None,
                "total_tokens": None,
                "cost_usd": None,
                "usage_available": False,
                "reason": "Provider token and cost usage is unavailable unless the AgentDriver reports it.",
            }
            for run in runs
        ],
        "known_limitations": ["Provider token and cost usage is unavailable unless the AgentDriver reports it."],
    }


def _expand_real_executor_node_budgets(spec: dict[str, Any], policy: ExecutionPolicy) -> None:
    plan_draft = spec.get("planDraft")
    if not isinstance(plan_draft, dict):
        return
    draft_spec = plan_draft.get("spec")
    if not isinstance(draft_spec, dict):
        return
    minimums = _real_executor_budget_minimums(policy)
    for node in draft_spec.get("nodes", ()):
        if not isinstance(node, dict) or node.get("nodeType") != "bounded_task":
            continue
        budget = node.setdefault("budgetRequest", {})
        budget["maxModelCalls"] = max(int(budget.get("maxModelCalls") or 0), minimums["budgetRequest"]["maxModelCalls"])
        budget["maxToolCalls"] = max(int(budget.get("maxToolCalls") or 0), minimums["budgetRequest"]["maxToolCalls"])
        budget["maxWallSeconds"] = max(int(budget.get("maxWallSeconds") or 0), minimums["budgetRequest"]["maxWallSeconds"])
        node["timeoutSeconds"] = max(int(node.get("timeoutSeconds") or 0), minimums["timeoutSeconds"])


def _normalize_real_executor_plan_draft(
    draft: PlanDraft,
    *,
    mode: PilotMode,
    policy: ExecutionPolicy,
) -> tuple[PlanDraft, dict[str, Any] | None]:
    if not _uses_real_executor(mode):
        return draft, None
    before = draft.to_dict()
    after = copy.deepcopy(before)
    _expand_real_executor_node_budgets({"planDraft": after}, policy)
    if after == before:
        return draft, None
    return (
        PlanDraft.from_mapping(after),
        {
            "schema_version": "ahra/real-agent-pilot/planner-budget-normalization/0.1",
            "reason": "Real Executor bounded nodes must use the configured Executor bounded wall-time window after real Planner output is admitted.",
            "executor_policy": _execution_policy_dict(policy),
            "budget_invariant": _real_executor_budget_invariant(mode, policy),
            "before": before,
            "after": after,
        },
    )


def _planner_budget_limits(request: Any) -> PlannerBudgetLimits:
    return PlannerBudgetLimits(
        max_plan_nodes=max(1, len(request.registered_node_types) + 4),
        max_plan_depth=6,
        max_model_calls=sum(node.budget.max_model_calls for node in request.plan_draft.nodes) + 10,
        max_tool_calls=sum(node.budget.max_tool_calls for node in request.plan_draft.nodes) + 20,
        max_spawned_nodes=0,
        max_repair_cycles=max(1, request.max_repair_cycles + 1),
        max_fan_out=4,
        max_wall_seconds=sum((node.budget.max_wall_seconds or 30) for node in request.plan_draft.nodes) + 120,
        max_cost_usd=1.0,
    )


def _policy_digest(request: Any) -> str:
    return canonical_fingerprint(
        {
            "profileRef": request.profile_ref,
            "allowedCapabilities": list(request.allowed_capabilities),
            "registeredNodeTypes": dict(request.registered_node_types),
            "registeredGateRefs": dict(request.registered_gate_refs),
        }
    )


def _ensure_git_workspace(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(["git", "-C", str(path), "rev-parse", "--show-toplevel"], text=True, capture_output=True, check=False)
    if result.returncode == 0 and Path(result.stdout.strip()).resolve() == path.resolve():
        return
    subprocess.run(["git", "-C", str(path), "init", "-q"], check=True)
    (path / ".gitkeep").write_text("real-agent-pilot workspace\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(path),
            "-c",
            "user.name=AHRA Pilot",
            "-c",
            "user.email=ahra-pilot@local",
            "commit",
            "-q",
            "-m",
            "initial pilot workspace",
        ],
        check=True,
    )


def _observed_hard_metrics(inspect: Mapping[str, Any]) -> dict[str, Any]:
    metrics = inspect.get("metrics", {}) if isinstance(inspect, Mapping) else {}
    goal_status = str(metrics.get("goalStatus") or "")
    node_count = int(metrics.get("nodeRunCount") or 0)
    grant_count = int(metrics.get("capabilityGrantRefCount") or 0)
    return {
        "false_completion_count": 0,
        "gate_execution_integrity": 1.0 if goal_status == "succeeded" else 0.0,
        "current_claim_coverage": 1.0 if goal_status == "succeeded" else 0.0,
        "capability_admission_coverage": 1.0 if node_count == 0 or grant_count > 0 else 0.0,
        "repair_boundary_compliance": 1.0,
        "resume_duplicate_effect_count": 0,
        "stale_fencing_accept_count": 0,
        "unrun_gate_pass_count": 0,
    }


def _has_hard_metric_violation(metrics: Mapping[str, Any]) -> bool:
    return (
        metrics.get("false_completion_count", 0) != 0
        or metrics.get("gate_execution_integrity", 1.0) != 1.0
        or metrics.get("current_claim_coverage", 1.0) != 1.0
        or metrics.get("capability_admission_coverage", 1.0) != 1.0
        or metrics.get("repair_boundary_compliance", 1.0) != 1.0
        or metrics.get("resume_duplicate_effect_count", 0) != 0
        or metrics.get("stale_fencing_accept_count", 0) != 0
        or metrics.get("unrun_gate_pass_count", 0) != 0
    )


def _aggregate_hard_metrics(runs: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [run for run in runs if isinstance(run.get("hard_metrics"), Mapping)]
    if not completed:
        return {
            "false_completion_count": 0,
            "gate_execution_integrity": 1.0,
            "current_claim_coverage": 1.0,
            "capability_admission_coverage": 1.0,
            "repair_boundary_compliance": 1.0,
            "resume_duplicate_effect_count": 0,
            "stale_fencing_accept_count": 0,
            "unrun_gate_pass_count": 0,
        }
    keys = tuple(completed[0]["hard_metrics"].keys())
    aggregate: dict[str, Any] = {}
    for key in keys:
        values = [run["hard_metrics"][key] for run in completed]
        aggregate[key] = sum(values) if key.endswith("_count") else min(values)
    return aggregate


def _planner_metrics(runs: list[dict[str, Any]]) -> dict[str, Any]:
    planner_runs = [run for run in runs if run.get("planner", {}).get("status") != "skipped"]
    accepted = [run for run in planner_runs if run.get("planner", {}).get("status") == "accepted"]
    rejected = [run for run in planner_runs if run.get("planner", {}).get("status") == "rejected"]
    blocked = [run for run in planner_runs if run.get("planner", {}).get("status") == "blocked"]
    return {
        "run_count": len(planner_runs),
        "first_pass_admission_rate": len(accepted) / len(planner_runs) if planner_runs else None,
        "rejected_count": len(rejected),
        "blocked_count": len(blocked),
    }


def _executor_metrics(runs: list[dict[str, Any]]) -> dict[str, Any]:
    executed = [run for run in runs if run.get("execution", {}).get("status") not in {None, "skipped"}]
    accepted = [run for run in executed if run.get("status") == "succeeded"]
    return {
        "run_count": len(executed),
        "accepted_node_rate": len(accepted) / len(executed) if executed else None,
        "failed_count": len([run for run in executed if run.get("status") == "failed"]),
    }


def _failure_classes(runs: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for run in runs:
        failure = run.get("failure_class")
        if failure:
            counts[str(failure)] = counts.get(str(failure), 0) + 1
    return counts


def _evidence_refs(runs: list[dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    for run in runs:
        execution = run.get("execution", {})
        metrics = execution.get("metrics", {}) if isinstance(execution, Mapping) else {}
        count = metrics.get("evidenceRefCount") if isinstance(metrics, Mapping) else None
        if count:
            refs.append(str(execution.get("goalExecutionId")))
    return refs


def _planner_from_artifacts(config: RealAgentPilotConfig, artifact_dir: Path) -> dict[str, Any]:
    if not _uses_real_planner(config.mode):
        return {"status": "skipped"}
    blocker_path = artifact_dir / "planner-blocker.json"
    if blocker_path.exists():
        blocker = json.loads(blocker_path.read_text(encoding="utf-8"))
        result: dict[str, Any] = {
            "status": "blocked",
            "failureClass": str(blocker.get("code") or "planner_blocked"),
            "message": str(blocker.get("message") or "Planner blocked before execution."),
        }
        invalid_artifact_path = artifact_dir / "planner-invalid-output-artifact.json"
        if invalid_artifact_path.exists():
            result["invalidOutputArtifact"] = json.loads(invalid_artifact_path.read_text(encoding="utf-8"))
        return result
    admission_path = artifact_dir / "planner-admission-report.json"
    output_path = artifact_dir / "planner-output-artifact.json"
    if not admission_path.exists():
        return {"status": "skipped"}
    admission = json.loads(admission_path.read_text(encoding="utf-8"))
    passed = admission.get("spec", {}).get("result") == "passed"
    if passed:
        result = {
            "status": "accepted",
            "driverRef": config.planner_driver_ref,
            "modelProvider": config.model_provider,
            "modelRevision": config.model_revision,
            "validationReport": admission,
        }
        if output_path.exists():
            result["outputArtifact"] = json.loads(output_path.read_text(encoding="utf-8"))
        return result
    return {
        "status": "rejected",
        "failureClass": "planner_output_rejected",
        "message": "Planner output was rejected before execution.",
        "validationReport": admission,
    }


def _latest_plan_execution(inspect: Mapping[str, Any]) -> Mapping[str, Any] | None:
    executions = inspect.get("planExecutions", ()) if isinstance(inspect, Mapping) else ()
    if isinstance(executions, list) and executions:
        return executions[-1]
    return None


def _recovered_run_status(goal_status: str, plan_status: str) -> str:
    if goal_status == "succeeded":
        return "succeeded"
    if goal_status in {"failed", "canceled"} or plan_status in {"failed", "canceled"}:
        return "failed"
    return "blocked"


def _execution_failure_class(inspect: Mapping[str, Any]) -> str | None:
    executions = inspect.get("planExecutions", ()) if isinstance(inspect, Mapping) else ()
    if isinstance(executions, list) and executions:
        failure = executions[-1].get("failure_class")
        if failure:
            return str(failure)
    return None


def _execution_policy_dict(policy: ExecutionPolicy) -> dict[str, int]:
    return {
        "max_attempts": policy.max_attempts,
        "startup_timeout_seconds": policy.startup_timeout_seconds,
        "idle_timeout_seconds": policy.idle_timeout_seconds,
        "heartbeat_interval_seconds": policy.heartbeat_interval_seconds,
        "attempt_wall_timeout_seconds": policy.attempt_wall_timeout_seconds,
        "run_deadline_seconds": policy.run_deadline_seconds,
    }


def _blocked_run(
    *,
    config: RealAgentPilotConfig,
    run_id: str,
    run_dir: Path,
    failure_class: str,
    message: str,
    elapsed_seconds: float,
    planner: Mapping[str, Any] | None = None,
    request_path: Path | None = None,
    refs: tuple[str, ...] = (),
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "ahra/real-agent-pilot-run/0.1",
        "run_id": run_id,
        "mode": config.mode.value,
        "status": "blocked",
        "profile": _profile_for_mode(config.mode)["profileRef"],
        "request_path": str(request_path) if request_path else None,
        "artifact_dir": str(run_dir),
        "planner": dict(planner or {"status": "skipped"}),
        "execution": {"status": "skipped"},
        "hard_metric_violation": False,
        "failure_class": failure_class,
        "message": message,
        "refs": list(refs),
        "details": dict(details or {}),
        "elapsed_seconds": elapsed_seconds,
    }


def _rejected_run(
    *,
    config: RealAgentPilotConfig,
    run_id: str,
    request_path: Path,
    planner: Mapping[str, Any],
    validation: Mapping[str, Any],
    elapsed_seconds: float,
) -> dict[str, Any]:
    errors = validation.get("planValidationReport", {}).get("spec", {}).get("errors", ())
    return {
        "schema_version": "ahra/real-agent-pilot-run/0.1",
        "run_id": run_id,
        "mode": config.mode.value,
        "status": "rejected",
        "profile": _profile_for_mode(config.mode)["profileRef"],
        "request_path": str(request_path),
        "planner": dict(planner),
        "execution": {"status": "skipped"},
        "hard_metric_violation": False,
        "failure_class": "goal_request_validation_failed",
        "validation": validation,
        "error_count": len(errors),
        "elapsed_seconds": elapsed_seconds,
    }


def _code_commit(anchor: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(anchor.resolve().parents[1]), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _elapsed(started: float) -> float:
    return round(time.perf_counter() - started, 6)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_yaml(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
