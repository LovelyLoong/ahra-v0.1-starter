from __future__ import annotations

import json
import hashlib
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml
from jsonschema import Draft202012Validator, FormatChecker

from ahra.ports import AgentDriver, AgentDriverRegistry
from ahra.workflow_modules import WorkflowModuleRegistry, load_workflow_module_registry

from .git_ops import LocalGitWorkspaceProvider, WorktreeManager
from .loop_engineering import LoopEngine
from .models import (
    ChangePolicy,
    CheckSpec,
    GoalRunResult,
    GoalSpec,
    NextStepDecision,
    PlanAction,
    TaskRunResult,
    TaskSpec,
    WorkflowOutcome,
    to_jsonable,
)
from .runtime import LocalRuntimeProvider
from .standard_harness import TaskHarness
from .store import FileRunStore

ALLOWED_APPROVAL_MODES = {"manual", "auto", "disabled"}
SCHEMA_PATH = Path(__file__).resolve().parents[3] / "contracts/schemas/workflow-run-request.schema.json"
RESUME_SCHEMA_PATH = Path(__file__).resolve().parents[3] / "contracts/schemas/workflow-resume-request.schema.json"
REFERENCE_MODULE_PATHS = (
    Path(__file__).resolve().parents[3] / "examples/workflow_modules/standard-harness.yaml",
    Path(__file__).resolve().parents[3] / "examples/workflow_modules/loop-engineering.yaml",
)


@dataclass(frozen=True, slots=True)
class WorkflowRunRequest:
    name: str
    module_id: str
    workspace_ref: str
    driver_ref: str
    store_ref: str
    approval_mode: str
    runtime_profile_ref: str | None = None
    task: TaskSpec | None = None
    goal: GoalSpec | None = None
    artifact_dir: str | None = None
    run_id: str | None = None
    branch: str | None = None
    base_commit: str | None = None


@dataclass(frozen=True, slots=True)
class PlanApprovalDecision:
    actor: str
    approved: bool
    reason: str
    plan_artifact: str
    expected_plan_sha256: str
    approved_task_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WorkflowResumeRequest:
    name: str
    run_id: str
    module_id: str
    workspace_ref: str
    driver_ref: str
    store_ref: str
    artifact_dir: str
    approval: PlanApprovalDecision
    branch: str | None = None
    base_commit: str | None = None


@dataclass(frozen=True, slots=True)
class WorkflowRunEnvelope:
    run_id: str
    module_id: str
    driver_ref: str
    status: str
    artifact_dir: str
    result: Any


def load_workflow_run_request(path: Path) -> WorkflowRunRequest:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"workflow run request must be an object: {path}")
    return workflow_run_request_from_document(document, base_dir=path.parent)


def load_workflow_resume_request(path: Path) -> WorkflowResumeRequest:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"workflow resume request must be an object: {path}")
    return workflow_resume_request_from_document(document)


def workflow_run_request_from_document(
    document: dict[str, Any],
    *,
    base_dir: Path | None = None,
) -> WorkflowRunRequest:
    _validate_document_schema(document)
    if document.get("apiVersion") != "ahra.dev/v1alpha1":
        raise ValueError("workflow run request apiVersion must be ahra.dev/v1alpha1")
    if document.get("kind") != "WorkflowRunRequest":
        raise ValueError("workflow run request kind must be WorkflowRunRequest")
    metadata = document.get("metadata")
    spec = document.get("spec")
    if not isinstance(metadata, dict) or not isinstance(spec, dict):
        raise ValueError("workflow run request requires metadata and spec")
    input_spec = spec.get("input")
    if not isinstance(input_spec, dict):
        raise ValueError("workflow run request spec.input must be an object")

    task = _load_task_input(input_spec, base_dir)
    goal = _load_goal_input(input_spec, base_dir)
    if task and goal:
        raise ValueError("workflow run request input cannot include both task and goal")

    return WorkflowRunRequest(
        name=str(metadata["name"]),
        module_id=str(spec["moduleId"]),
        workspace_ref=str(spec["workspaceRef"]),
        driver_ref=str(spec["driverRef"]),
        store_ref=str(spec["storeRef"]),
        approval_mode=str(spec["approvalMode"]),
        runtime_profile_ref=(
            str(spec["runtimeProfileRef"]) if spec.get("runtimeProfileRef") else None
        ),
        task=task,
        goal=goal,
        artifact_dir=str(spec["artifactDir"]) if spec.get("artifactDir") else None,
        run_id=str(spec["runId"]) if spec.get("runId") else None,
        branch=str(spec["branch"]) if spec.get("branch") else None,
        base_commit=str(spec["baseCommit"]) if spec.get("baseCommit") else None,
    )


def workflow_resume_request_from_document(document: dict[str, Any]) -> WorkflowResumeRequest:
    _validate_document_schema(document, RESUME_SCHEMA_PATH, "workflow resume request")
    if document.get("apiVersion") != "ahra.dev/v1alpha1":
        raise ValueError("workflow resume request apiVersion must be ahra.dev/v1alpha1")
    if document.get("kind") != "WorkflowResumeRequest":
        raise ValueError("workflow resume request kind must be WorkflowResumeRequest")
    metadata = document.get("metadata")
    spec = document.get("spec")
    if not isinstance(metadata, dict) or not isinstance(spec, dict):
        raise ValueError("workflow resume request requires metadata and spec")
    approval = spec["approval"]
    return WorkflowResumeRequest(
        name=str(metadata["name"]),
        run_id=str(spec["runId"]),
        module_id=str(spec["moduleId"]),
        workspace_ref=str(spec["workspaceRef"]),
        driver_ref=str(spec["driverRef"]),
        store_ref=str(spec["storeRef"]),
        artifact_dir=str(spec["artifactDir"]),
        approval=PlanApprovalDecision(
            actor=str(approval["actor"]),
            approved=bool(approval["approved"]),
            reason=str(approval["reason"]),
            plan_artifact=str(approval["planArtifact"]),
            expected_plan_sha256=str(approval["expectedPlanSha256"]),
            approved_task_ids=tuple(str(item) for item in approval.get("approvedTaskIds", ())),
        ),
        branch=str(spec["branch"]) if spec.get("branch") else None,
        base_commit=str(spec["baseCommit"]) if spec.get("baseCommit") else None,
    )


async def run_workflow(
    request: WorkflowRunRequest,
    *,
    drivers: AgentDriverRegistry,
    module_registry: WorkflowModuleRegistry | None = None,
    workspace_provider=None,
    runtime_provider=None,
) -> WorkflowRunEnvelope:
    validate_workflow_run_request(request)
    module_registry = module_registry or load_reference_workflow_module_registry()
    module = module_registry.get(request.module_id)
    handler = _REFERENCE_WORKFLOW_HANDLERS.get(module.module_id)
    if handler is None:
        raise ValueError(f"reference runner has no implementation for workflow module: {module.module_id}")
    if request.store_ref != "local-file":
        raise ValueError(f"unsupported storeRef for reference runner: {request.store_ref}")
    driver = drivers.get(request.driver_ref)
    should_isolate_workspace = workspace_provider is None
    workspace_provider = workspace_provider or LocalGitWorkspaceProvider()
    runtime_provider = runtime_provider or LocalRuntimeProvider()
    run_id = request.run_id or f"RUN-{uuid4().hex}"
    artifact_dir = Path(request.artifact_dir or f".runtime/ahra-runs/{run_id}")
    store = FileRunStore(artifact_dir)
    branch = request.branch or "ahra/reference-runner"
    base_commit = request.base_commit or workspace_provider.current_head(request.workspace_ref)
    execution_workspace_ref = request.workspace_ref
    workspace_record: dict[str, Any] | None = None
    if should_isolate_workspace:
        workspace_record = _create_isolated_workspace(
            request=request,
            run_id=run_id,
            store=store,
            branch=branch,
            base_commit=base_commit,
        )
        execution_workspace_ref = str(workspace_record["effective_workspace_ref"])
        branch = str(workspace_record["branch"])
        base_commit = str(workspace_record["base_commit"])
    effective_request = replace(
        request,
        run_id=run_id,
        branch=branch,
        base_commit=base_commit,
        artifact_dir=str(store.run_dir),
    )

    subject_id = _subject_id(effective_request)
    store.write_artifact(
        "workflow-run-request.json",
        effective_request,
        task_id=subject_id,
        kind="workflow_run_request",
        media_type="application/json",
        created_by="workflow-runner:reference",
        input_refs=[effective_request.module_id, effective_request.driver_ref],
    )
    if workspace_record is not None:
        store.write_artifact(
            "workspace.json",
            workspace_record,
            task_id=subject_id,
            kind="isolated_workspace",
            media_type="application/json",
            created_by="workflow-runner:reference",
            input_refs=[run_id, effective_request.workspace_ref, base_commit],
        )

    result = await handler(
        request=effective_request,
        driver=driver,
        workspace_provider=workspace_provider,
        runtime_provider=runtime_provider,
        execution_workspace_ref=execution_workspace_ref,
        branch=branch,
        base_commit=base_commit,
        run_id=run_id,
        store=store,
    )

    store.write_artifact(
        "workflow-run-result.json",
        result,
        task_id=subject_id,
        kind="workflow_run_result",
        media_type="application/json",
        created_by="workflow-runner:reference",
        input_refs=[run_id, request.module_id],
    )
    return WorkflowRunEnvelope(
        run_id=run_id,
        module_id=effective_request.module_id,
        driver_ref=effective_request.driver_ref,
        status=str(result.status),
        artifact_dir=str(store.run_dir),
        result=result,
    )


async def resume_workflow(
    request: WorkflowResumeRequest,
    *,
    drivers: AgentDriverRegistry,
    module_registry: WorkflowModuleRegistry | None = None,
    workspace_provider=None,
    runtime_provider=None,
) -> WorkflowRunEnvelope:
    validate_workflow_resume_request(request)
    module_registry = module_registry or load_reference_workflow_module_registry()
    module = module_registry.get(request.module_id)
    if module.module_id != "loop-engineering":
        raise ValueError(f"reference runner can only resume loop-engineering runs: {module.module_id}")
    if request.store_ref != "local-file":
        raise ValueError(f"unsupported storeRef for reference runner: {request.store_ref}")
    driver = drivers.get(request.driver_ref)
    artifact_dir = Path(request.artifact_dir)
    if not artifact_dir.exists():
        raise ValueError(f"workflow artifactDir does not exist: {artifact_dir}")
    if not artifact_dir.is_dir():
        raise ValueError(f"workflow artifactDir must be a directory: {artifact_dir}")
    run_request_path = artifact_dir / "workflow-run-request.json"
    run_result_path = artifact_dir / "workflow-run-result.json"
    if not run_request_path.exists() or not run_result_path.exists():
        raise ValueError("workflow artifactDir is missing start request or result artifacts")

    stored_request = _workflow_run_request_from_jsonable(
        json.loads(run_request_path.read_text(encoding="utf-8"))
    )
    _ensure_resume_matches_start(request, stored_request)
    if stored_request.goal is None:
        raise ValueError("stored loop-engineering request is missing goal input")
    stored_result = json.loads(run_result_path.read_text(encoding="utf-8"))
    if stored_result.get("status") != str(WorkflowOutcome.AWAITING_PLAN_APPROVAL):
        raise ValueError("workflow run is not awaiting plan approval")

    plan_path = _artifact_path(artifact_dir, request.approval.plan_artifact)
    plan_bytes = plan_path.read_bytes()
    actual_sha256 = hashlib.sha256(plan_bytes).hexdigest()
    if actual_sha256 != request.approval.expected_plan_sha256:
        raise ValueError("approved plan SHA-256 does not match stored plan artifact")
    decision = _next_step_from_mapping(json.loads(plan_bytes.decode("utf-8")))
    selected_tasks = _select_approved_tasks(decision, request.approval.approved_task_ids)

    workspace_provider = workspace_provider or LocalGitWorkspaceProvider()
    runtime_provider = runtime_provider or LocalRuntimeProvider()
    store = FileRunStore(artifact_dir)
    subject_id = stored_request.goal.id if stored_request.goal else request.run_id
    approval_record = {
        "run_id": request.run_id,
        "module_id": request.module_id,
        "actor": request.approval.actor,
        "approved": request.approval.approved,
        "reason": request.approval.reason,
        "plan_artifact": request.approval.plan_artifact,
        "plan_sha256": actual_sha256,
        "approved_task_ids": request.approval.approved_task_ids,
    }
    store.write_artifact(
        f"approvals/{request.run_id}-plan-decision.json",
        approval_record,
        task_id=subject_id,
        kind="plan_approval_decision",
        media_type="application/json",
        created_by="workflow-runner:reference",
        input_refs=[request.run_id, request.approval.plan_artifact],
    )
    store.write_evidence(
        f"approvals/{request.run_id}-plan-decision-evidence.json",
        approval_record,
        task_id=subject_id,
        kind="plan_approval_decision",
        refs=[request.run_id, request.approval.plan_artifact],
    )

    completed = tuple(_task_result_from_mapping(item) for item in stored_result.get("completed_tasks", ()))
    branch = stored_request.branch or request.branch or "ahra/reference-runner"
    base_commit = stored_request.base_commit or request.base_commit
    execution_workspace_ref = _stored_execution_workspace_ref(stored_result)
    if base_commit is None:
        base_commit = workspace_provider.current_head(execution_workspace_ref)

    if not request.approval.approved:
        result = GoalRunResult(
            run_id=request.run_id,
            goal_id=subject_id,
            status=WorkflowOutcome.BLOCKED,
            branch=branch,
            workspace=workspace_provider.resolve_path(execution_workspace_ref),
            artifact_dir=str(store.run_dir),
            completed_tasks=completed,
            next_step=decision,
            final_commit=workspace_provider.current_head(execution_workspace_ref),
            message=f"Plan approval rejected by {request.approval.actor}: {request.approval.reason}",
        )
        store.write_artifact(
            "workflow-resume-result.json",
            result,
            task_id=subject_id,
            kind="workflow_resume_result",
            media_type="application/json",
            created_by="workflow-runner:reference",
            input_refs=[request.run_id, request.approval.plan_artifact],
        )
        return WorkflowRunEnvelope(
            run_id=request.run_id,
            module_id=request.module_id,
            driver_ref=request.driver_ref,
            status=str(result.status),
            artifact_dir=str(store.run_dir),
            result=result,
        )

    if not selected_tasks:
        raise ValueError("approved plan contains no selected tasks")

    store.write_artifact(
        "workflow-resume-request.json",
        request,
        task_id=subject_id,
        kind="workflow_resume_request",
        media_type="application/json",
        created_by="workflow-runner:reference",
        input_refs=[request.run_id, request.approval.plan_artifact],
    )
    result = await LoopEngine(
        driver,
        workspace_provider=workspace_provider,
        runtime_provider=runtime_provider,
        runtime_profile_ref=stored_request.runtime_profile_ref,
    ).run_goal(
        goal=_apply_approval_mode(stored_request.goal, stored_request.approval_mode),
        workspace_ref=execution_workspace_ref,
        branch=branch,
        base_commit=base_commit,
        run_id=request.run_id,
        store=store,
        pending_tasks=selected_tasks,
        completed_tasks=completed,
        known_task_ids=_known_task_ids(stored_request.goal, completed, selected_tasks),
        start_cycle=_next_cycle_from_plan_artifact(store.run_dir, plan_path),
    )
    store.write_artifact(
        "workflow-resume-result.json",
        result,
        task_id=subject_id,
        kind="workflow_resume_result",
        media_type="application/json",
        created_by="workflow-runner:reference",
        input_refs=[request.run_id, request.approval.plan_artifact],
    )
    return WorkflowRunEnvelope(
        run_id=request.run_id,
        module_id=request.module_id,
        driver_ref=request.driver_ref,
        status=str(result.status),
        artifact_dir=str(store.run_dir),
        result=result,
    )


def load_reference_workflow_module_registry() -> WorkflowModuleRegistry:
    return load_workflow_module_registry(list(REFERENCE_MODULE_PATHS))


def validate_workflow_run_request(request: WorkflowRunRequest) -> None:
    if request.approval_mode not in ALLOWED_APPROVAL_MODES:
        raise ValueError(
            "workflow run request approvalMode must be one of: "
            + ", ".join(sorted(ALLOWED_APPROVAL_MODES))
        )
    if request.task and request.goal:
        raise ValueError("workflow run request cannot include both task and goal input")
    if request.module_id == "standard-harness":
        if request.task is None:
            raise ValueError("standard-harness requires task input")
        if request.goal is not None:
            raise ValueError("standard-harness cannot receive goal input")
    if request.module_id == "loop-engineering":
        if request.goal is None:
            raise ValueError("loop-engineering requires goal input")
        if request.task is not None:
            raise ValueError("loop-engineering cannot receive task input")


def validate_workflow_resume_request(request: WorkflowResumeRequest) -> None:
    if request.module_id != "loop-engineering":
        raise ValueError("workflow resume request only supports loop-engineering")
    if request.store_ref != "local-file":
        raise ValueError(f"unsupported storeRef for reference runner: {request.store_ref}")
    if not request.run_id.startswith("RUN-"):
        raise ValueError("workflow resume request runId must start with RUN-")
    if not request.artifact_dir:
        raise ValueError("workflow resume request artifactDir is required")
    if not request.approval.actor:
        raise ValueError("workflow resume request approval actor is required")
    if not request.approval.reason:
        raise ValueError("workflow resume request approval reason is required")
    if not request.approval.plan_artifact:
        raise ValueError("workflow resume request approval planArtifact is required")
    if not re.fullmatch(r"[a-f0-9]{64}", request.approval.expected_plan_sha256):
        raise ValueError("workflow resume request approval expectedPlanSha256 must be a SHA-256 hex digest")
    if len(set(request.approval.approved_task_ids)) != len(request.approval.approved_task_ids):
        raise ValueError("workflow resume request approvedTaskIds must be unique")


async def _run_standard_harness(
    *,
    request: WorkflowRunRequest,
    driver: AgentDriver,
    workspace_provider,
    runtime_provider,
    execution_workspace_ref: str,
    branch: str,
    base_commit: str,
    run_id: str,
    store: FileRunStore,
) -> Any:
    if request.task is None:
        raise ValueError("standard-harness requires task input")
    return await TaskHarness(
        driver,
        workspace_provider=workspace_provider,
        runtime_provider=runtime_provider,
        runtime_profile_ref=request.runtime_profile_ref,
    ).run_task(
        task=request.task,
        workspace_ref=execution_workspace_ref,
        branch=branch,
        run_id=run_id,
        store=store,
    )


async def _run_loop_engineering(
    *,
    request: WorkflowRunRequest,
    driver: AgentDriver,
    workspace_provider,
    runtime_provider,
    execution_workspace_ref: str,
    branch: str,
    base_commit: str,
    run_id: str,
    store: FileRunStore,
) -> Any:
    if request.goal is None:
        raise ValueError("loop-engineering requires goal input")
    goal = _apply_approval_mode(request.goal, request.approval_mode)
    return await LoopEngine(
        driver,
        workspace_provider=workspace_provider,
        runtime_provider=runtime_provider,
        runtime_profile_ref=request.runtime_profile_ref,
    ).run_goal(
        goal=goal,
        workspace_ref=execution_workspace_ref,
        branch=branch,
        base_commit=base_commit,
        run_id=run_id,
        store=store,
    )


_REFERENCE_WORKFLOW_HANDLERS = {
    "standard-harness": _run_standard_harness,
    "loop-engineering": _run_loop_engineering,
}


def _validate_document_schema(
    document: dict[str, Any],
    schema_path: Path = SCHEMA_PATH,
    label: str = "workflow run request",
) -> None:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.path))
    if errors:
        first = errors[0]
        path = "/".join(map(str, first.path)) or "<root>"
        raise ValueError(f"{label} schema validation failed at {path}: {first.message}")


def _apply_approval_mode(goal: GoalSpec, approval_mode: str) -> GoalSpec:
    if approval_mode == "manual":
        return replace(goal, auto_execute_proposed_tasks=False)
    if approval_mode == "auto":
        return replace(goal, auto_execute_proposed_tasks=True)
    if approval_mode == "disabled":
        return replace(goal, dynamic_planning=False, auto_execute_proposed_tasks=False)
    raise ValueError(f"unsupported approvalMode: {approval_mode}")


def _load_task_input(input_spec: dict[str, Any], base_dir: Path | None) -> TaskSpec | None:
    if "task" in input_spec:
        return _task_from_mapping(_unwrap_named(input_spec["task"], "task"))
    if "taskRef" in input_spec:
        return _task_from_mapping(_load_ref(input_spec["taskRef"], base_dir, "task"))
    return None


def _load_goal_input(input_spec: dict[str, Any], base_dir: Path | None) -> GoalSpec | None:
    if "goal" in input_spec:
        return _goal_from_mapping(_unwrap_named(input_spec["goal"], "goal"))
    if "goalRef" in input_spec:
        return _goal_from_mapping(_load_ref(input_spec["goalRef"], base_dir, "goal"))
    return None


def _load_ref(ref: Any, base_dir: Path | None, key: str) -> dict[str, Any]:
    path = Path(str(ref))
    if not path.is_absolute() and base_dir is not None:
        path = base_dir / path
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    return _unwrap_named(document, key)


def _unwrap_named(value: Any, key: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{key} input must be an object")
    nested = value.get(key)
    if isinstance(nested, dict):
        return nested
    return value


def _task_from_mapping(data: dict[str, Any]) -> TaskSpec:
    return TaskSpec(
        id=str(data["id"]),
        title=str(data["title"]),
        objective=str(data["objective"]),
        acceptance_criteria=tuple(data["acceptance_criteria"]),
        scope=tuple(data.get("scope", ())),
        requirements=tuple(data.get("requirements", ())),
        non_goals=tuple(data.get("non_goals", ())),
        checks=tuple(_check_from_mapping(item) for item in data.get("checks", ())),
        policy=_policy_from_mapping(data.get("policy", {})),
        max_attempts=int(data.get("max_attempts", 2)),
        max_turns=int(data.get("max_turns", 25)),
    )


def _goal_from_mapping(data: dict[str, Any]) -> GoalSpec:
    return GoalSpec(
        id=str(data["id"]),
        title=str(data["title"]),
        objective=str(data["objective"]),
        success_criteria=tuple(data["success_criteria"]),
        boundaries=tuple(data.get("boundaries", ())),
        policy=_policy_from_mapping(data.get("policy", {})),
        tasks=tuple(_task_from_mapping(item) for item in data.get("tasks", ())),
        global_checks=tuple(_check_from_mapping(item) for item in data.get("global_checks", ())),
        max_cycles=int(data.get("max_cycles", 3)),
        max_total_tasks=int(data.get("max_total_tasks", 12)),
        dynamic_planning=bool(data.get("dynamic_planning", False)),
        auto_execute_proposed_tasks=bool(data.get("auto_execute_proposed_tasks", False)),
    )


def _check_from_mapping(data: dict[str, Any]) -> CheckSpec:
    return CheckSpec(
        name=str(data["name"]),
        argv=tuple(str(item) for item in data["argv"]),
        cwd=str(data.get("cwd", ".")),
        timeout_seconds=int(data.get("timeout_seconds", 300)),
        required=bool(data.get("required", True)),
        env={str(key): str(value) for key, value in data.get("env", {}).items()},
    )


def _policy_from_mapping(data: dict[str, Any]) -> ChangePolicy:
    default_policy = ChangePolicy()
    return ChangePolicy(
        allowed_globs=tuple(data.get("allowed_globs", default_policy.allowed_globs)),
        protected_globs=tuple(data.get("protected_globs", default_policy.protected_globs)),
        sensitive_globs=tuple(data.get("sensitive_globs", default_policy.sensitive_globs)),
        max_changed_files=int(data.get("max_changed_files", 30)),
        max_added_lines=int(data.get("max_added_lines", 1200)),
        max_deleted_lines=int(data.get("max_deleted_lines", 800)),
        allow_no_changes=bool(data.get("allow_no_changes", False)),
    )


def _workflow_run_request_from_jsonable(data: dict[str, Any]) -> WorkflowRunRequest:
    return WorkflowRunRequest(
        name=str(data["name"]),
        module_id=str(data["module_id"]),
        workspace_ref=str(data["workspace_ref"]),
        driver_ref=str(data["driver_ref"]),
        store_ref=str(data["store_ref"]),
        approval_mode=str(data["approval_mode"]),
        runtime_profile_ref=(
            str(data["runtime_profile_ref"]) if data.get("runtime_profile_ref") else None
        ),
        task=_task_from_mapping(data["task"]) if data.get("task") else None,
        goal=_goal_from_mapping(data["goal"]) if data.get("goal") else None,
        artifact_dir=str(data["artifact_dir"]) if data.get("artifact_dir") else None,
        run_id=str(data["run_id"]) if data.get("run_id") else None,
        branch=str(data["branch"]) if data.get("branch") else None,
        base_commit=str(data["base_commit"]) if data.get("base_commit") else None,
    )


def _task_result_from_mapping(data: dict[str, Any]) -> TaskRunResult:
    return TaskRunResult(
        run_id=str(data["run_id"]),
        task_id=str(data["task_id"]),
        status=WorkflowOutcome(str(data["status"])),
        checkpoint=str(data["checkpoint"]),
        workspace=str(data["workspace"]),
        branch=str(data["branch"]),
        artifact_dir=str(data["artifact_dir"]),
        commit=str(data["commit"]) if data.get("commit") else None,
        attempts=(),
        message=str(data.get("message", "")),
    )


def _next_step_from_mapping(data: dict[str, Any]) -> NextStepDecision:
    return NextStepDecision(
        action=PlanAction(str(data["action"])),
        rationale=str(data["rationale"]),
        proposed_tasks=tuple(_task_from_mapping(item) for item in data.get("proposed_tasks", ())),
        human_questions=tuple(str(item) for item in data.get("human_questions", ())),
    )


def _ensure_resume_matches_start(
    request: WorkflowResumeRequest,
    stored_request: WorkflowRunRequest,
) -> None:
    if stored_request.run_id and stored_request.run_id != request.run_id:
        raise ValueError("workflow resume request runId does not match stored run request")
    for field_name in ("module_id", "workspace_ref", "driver_ref", "store_ref"):
        if getattr(stored_request, field_name) != getattr(request, field_name):
            raise ValueError(f"workflow resume request {field_name} does not match stored run request")
    if stored_request.artifact_dir:
        stored_dir = Path(stored_request.artifact_dir).resolve()
        requested_dir = Path(request.artifact_dir).resolve()
        if stored_dir != requested_dir:
            raise ValueError("workflow resume request artifactDir does not match stored run request")
    if request.branch and stored_request.branch and request.branch != stored_request.branch:
        raise ValueError("workflow resume request branch conflicts with stored run request")
    if request.base_commit and stored_request.base_commit and request.base_commit != stored_request.base_commit:
        raise ValueError("workflow resume request baseCommit conflicts with stored run request")


def _create_isolated_workspace(
    *,
    request: WorkflowRunRequest,
    run_id: str,
    store: FileRunStore,
    branch: str,
    base_commit: str,
) -> dict[str, Any]:
    source_path = Path(request.workspace_ref).resolve()
    worktree_path = store.run_dir / "workspace"
    workspace = WorktreeManager(source_path).create(
        run_id=run_id,
        label=branch,
        base_ref=base_commit,
        destination=worktree_path,
        branch_name=request.branch,
    )
    return {
        "run_id": run_id,
        "isolation": "git-worktree",
        "source_workspace_ref": str(source_path),
        "effective_workspace_ref": str(workspace.path),
        "branch": workspace.branch,
        "base_commit": workspace.base_commit,
    }


def _stored_execution_workspace_ref(stored_result: dict[str, Any]) -> str:
    workspace = stored_result.get("workspace")
    if not isinstance(workspace, str) or not workspace:
        raise ValueError("stored workflow result is missing effective workspace")
    path = Path(workspace)
    if not path.exists():
        raise ValueError(f"stored workflow workspace does not exist: {workspace}")
    if not path.is_dir():
        raise ValueError(f"stored workflow workspace is not a directory: {workspace}")
    return str(path.resolve())


def _artifact_path(run_dir: Path, artifact_ref: str) -> Path:
    base = run_dir.resolve()
    candidate = Path(artifact_ref)
    path = candidate if candidate.is_absolute() else base / candidate
    path = path.resolve()
    if not path.is_relative_to(base):
        raise ValueError(f"workflow resume planArtifact escapes artifactDir: {artifact_ref}")
    if not path.exists():
        raise ValueError(f"workflow resume planArtifact does not exist: {artifact_ref}")
    if not path.is_file():
        raise ValueError(f"workflow resume planArtifact must be a file: {artifact_ref}")
    return path


def _select_approved_tasks(
    decision: NextStepDecision,
    approved_task_ids: tuple[str, ...],
) -> tuple[TaskSpec, ...]:
    if decision.action != PlanAction.ADD_TASKS:
        raise ValueError("workflow resume can only approve ADD_TASKS planner decisions")
    if not approved_task_ids:
        return decision.proposed_tasks
    available = {task.id: task for task in decision.proposed_tasks}
    missing = [task_id for task_id in approved_task_ids if task_id not in available]
    if missing:
        raise ValueError(f"workflow resume approved unknown task IDs: {missing}")
    requested = set(approved_task_ids)
    return tuple(task for task in decision.proposed_tasks if task.id in requested)


def _known_task_ids(
    goal: GoalSpec,
    completed_tasks: tuple[TaskRunResult, ...],
    approved_tasks: tuple[TaskSpec, ...],
) -> set[str]:
    ids = {task.id for task in goal.tasks}
    ids.update(result.task_id for result in completed_tasks)
    ids.update(task.id for task in approved_tasks)
    return ids


def _next_cycle_from_plan_artifact(run_dir: Path, plan_path: Path) -> int:
    relative = plan_path.resolve().relative_to(run_dir.resolve())
    parts = relative.parts
    if len(parts) >= 3 and parts[0] == "cycles" and parts[2] == "next-step.json":
        return int(parts[1]) + 1
    cycle_dirs = [
        int(path.name)
        for path in (run_dir / "cycles").glob("*")
        if path.is_dir() and path.name.isdigit()
    ]
    return (max(cycle_dirs) + 1) if cycle_dirs else 1


def _subject_id(request: WorkflowRunRequest) -> str:
    if request.task:
        return request.task.id
    if request.goal:
        return request.goal.id
    return request.name


def workflow_run_request_to_jsonable(request: WorkflowRunRequest) -> dict[str, Any]:
    return to_jsonable(request)
