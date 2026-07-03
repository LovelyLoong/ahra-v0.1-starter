from __future__ import annotations

import fnmatch
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from ahra.capabilities import CapabilityGrant as RuntimeCapabilityGrant, LocalRuntimeGateway
from ahra.evidence_v2 import canonical_fingerprint
from ahra.node_executor import (
    NodeExecutionRequest,
    NodeExecutionResult,
    NodeExecutionStatus,
    NodeExecutionUsage,
)
from ahra.plan_ir import (
    CapabilityGrant as PlanCapabilityGrant,
    CapabilityRequest as PlanCapabilityRequest,
    PlanBudget,
    PlanEdge,
    PlanIR,
    PlanNodeIR,
    PlanNodeType,
    PlanOutputContract,
    RetryPolicy,
)
from ahra.ports import AgentDriver

from .checks import INTERNAL_ARTIFACT_EXISTS_COMMAND, effective_check_argv
from .git_ops import LocalGitWorkspaceProvider
from .models import (
    DEFAULT_MAX_ATTEMPTS,
    ChangePolicy,
    CheckSpec,
    ExecutionPolicy,
    TaskRunResult,
    TaskSpec,
    WorkflowOutcome,
)
from .runtime import LocalRuntimeProvider
from .store import ReferenceRunStore
from .task_harness import TaskHarness


BOUNDED_TASK_EXECUTOR_RELEASE = (
    "bounded-task-executor@sha256:"
    "8e6fdc5c2d4d41f7aeb965d2bd9b57f91f6f4272fe910f48fcb21ff5b03bcf40"
)
CODE_CHANGE_SCHEMA_REF = "ahra/artifact/code-change/0.1"
DEVELOPMENT_BOUNDED_PROFILE_REF = "profile/development-bounded"
SEMANTIC_REVIEW_REQUIRED_FAILURE = "semantic_review_required"


class CapabilityRuntimeProvider:
    def __init__(
        self,
        *,
        runtime_provider,
        runtime_gateway: LocalRuntimeGateway,
        capability_grants: tuple[RuntimeCapabilityGrant, ...],
        plan_id: str,
        node_id: str,
        actor: str = "executor",
    ) -> None:
        self.runtime_provider = runtime_provider
        self.runtime_gateway = runtime_gateway
        self.capability_grants = capability_grants
        self.plan_id = plan_id
        self.node_id = node_id
        self.actor = actor

    def provision(self, profile_ref: str, workspace_ref: str, identity: str) -> str:
        return self.runtime_provider.provision(profile_ref, workspace_ref, identity)

    def exec(self, handle: str, command: list[str], env: dict[str, str], deadline: datetime) -> dict[str, Any]:
        command_tuple = tuple(command)
        grant = _grant_for_command(self.capability_grants, command_tuple)
        if grant is None:
            return _denied_exec("capability grant missing for process.exec:" + " ".join(command_tuple))

        result: dict[str, Any] = {}

        def runner(_: tuple[str, ...]) -> dict[str, Any]:
            nonlocal result
            result = dict(self.runtime_provider.exec(handle, list(command_tuple), env, deadline))
            return result

        audit = self.runtime_gateway.run_command(
            grant,
            plan_id=self.plan_id,
            node_id=self.node_id,
            actor=self.actor,
            command=command_tuple,
            runner=runner,
        )
        if not audit.allowed:
            return _denied_exec(f"capability denied process.exec:{audit.reason_code}")
        return result

    def snapshot(self, handle: str) -> str:
        return self.runtime_provider.snapshot(handle)

    def cancel(self, handle: str, execution_id: str) -> None:
        self.runtime_provider.cancel(handle, execution_id)

    def destroy(self, handle: str) -> None:
        self.runtime_provider.destroy(handle)


class BoundedTaskExecutor:
    def __init__(
        self,
        driver: AgentDriver,
        *,
        store: ReferenceRunStore,
        workspace_provider=None,
        runtime_provider=None,
        runtime_profile_ref: str | None = None,
        execution_policy: ExecutionPolicy | None = None,
        release_ref: str = BOUNDED_TASK_EXECUTOR_RELEASE,
        preserve_failed_workspace: bool = False,
    ) -> None:
        self.driver = driver
        self.store = store
        self.workspace_provider = workspace_provider or LocalGitWorkspaceProvider()
        self.runtime_provider = runtime_provider or LocalRuntimeProvider()
        self.runtime_profile_ref = runtime_profile_ref
        self.execution_policy = execution_policy or ExecutionPolicy()
        self._release_ref = release_ref
        self.preserve_failed_workspace = preserve_failed_workspace

    @property
    def node_type(self) -> str:
        return PlanNodeType.BOUNDED_TASK.value

    @property
    def release_ref(self) -> str:
        return self._release_ref

    async def execute(self, request: NodeExecutionRequest) -> NodeExecutionResult:
        _, node_result = await self.execute_task(request)
        return node_result

    async def execute_task(
        self,
        request: NodeExecutionRequest,
    ) -> tuple[TaskRunResult, NodeExecutionResult]:
        if request.node.node_type != PlanNodeType.BOUNDED_TASK.value:
            raise ValueError(f"BoundedTaskExecutor cannot execute node type {request.node.node_type}")
        if request.node.terminal_goal_verification:
            raise ValueError("bounded_task executor cannot execute terminal Goal verification nodes")
        _validate_runtime_grants(request)

        task = _task_from_request(request)
        workspace = Path(self.workspace_provider.resolve_path(request.workspace_ref))
        gateway = LocalRuntimeGateway(workspace)
        runtime = CapabilityRuntimeProvider(
            runtime_provider=self.runtime_provider,
            runtime_gateway=gateway,
            capability_grants=request.capability_grants,
            plan_id=request.plan.plan_id,
            node_id=request.node.node_id,
        )
        semantic_review_enabled = _semantic_review_declared(request.node)
        node_run_id = f"NRUN-{uuid4().hex}"
        self.store.event(
            "node_run_started",
            run_id=request.run_id,
            node_run_id=node_run_id,
            plan_id=request.plan.plan_id,
            node_id=request.node.node_id,
            node_type=request.node.node_type,
            executor_release=self.release_ref,
            gate_refs=list(request.node.gate_refs),
            semantic_review_enabled=semantic_review_enabled,
        )
        if _requires_semantic_code_review(request.node, self.runtime_profile_ref) and not semantic_review_enabled:
            message = (
                "development-bounded code-change output requires an independent semantic review gate"
            )
            terminal_ref, evidence_ref = _write_executor_terminal_failure(
                store=self.store,
                task=task,
                request=request,
                node_run_id=node_run_id,
                failure_class=SEMANTIC_REVIEW_REQUIRED_FAILURE,
                message=message,
                workspace=workspace,
            )
            node_result = NodeExecutionResult(
                node_run_id=node_run_id,
                plan_id=request.plan.plan_id,
                node_id=request.node.node_id,
                node_type=request.node.node_type,
                executor_release=self.release_ref,
                status=NodeExecutionStatus.REJECTED,
                evidence_refs=(evidence_ref,),
                terminal_failure_refs=(terminal_ref,),
                usage=NodeExecutionUsage(model_calls=0, tool_calls=0, cost_usd=0.0),
                message=message,
                details={
                    "failureClass": SEMANTIC_REVIEW_REQUIRED_FAILURE,
                    "semanticReviewEnabled": semantic_review_enabled,
                    "runtimeProfileRef": self.runtime_profile_ref,
                },
            )
            self.store.event(
                "node_run_finished",
                run_id=request.run_id,
                node_run_id=node_run_id,
                plan_id=request.plan.plan_id,
                node_id=request.node.node_id,
                status=node_result.status.value,
                artifact_refs=list(node_result.artifact_refs),
                evidence_refs=list(node_result.evidence_refs),
                terminal_failure_refs=list(node_result.terminal_failure_refs),
                task_completed_state_update_attempted=False,
            )
            return TaskRunResult(
                run_id=request.run_id,
                task_id=task.id,
                status=WorkflowOutcome.REJECTED,
                checkpoint="",
                workspace=str(workspace),
                branch=request.branch,
                artifact_dir=str(self.store.run_dir),
                attempts=(),
                commit=None,
                message=message,
            ), node_result

        preflight_denial = _preflight_literal_write_resources(
            request=request,
            gateway=gateway,
            actor="executor",
        )
        if preflight_denial is not None:
            node_result = NodeExecutionResult(
                node_run_id=node_run_id,
                plan_id=request.plan.plan_id,
                node_id=request.node.node_id,
                node_type=request.node.node_type,
                executor_release=self.release_ref,
                status=NodeExecutionStatus.REJECTED,
                terminal_failure_refs=(preflight_denial.audit_id,),
                usage=NodeExecutionUsage(model_calls=0, tool_calls=1, cost_usd=0.0),
                message=f"bounded task write preflight denied: {preflight_denial.reason_code}",
                details={"failureClass": preflight_denial.reason_code, "audit": preflight_denial.to_dict()},
            )
            self.store.event(
                "node_run_finished",
                run_id=request.run_id,
                node_run_id=node_run_id,
                plan_id=request.plan.plan_id,
                node_id=request.node.node_id,
                status=node_result.status.value,
                artifact_refs=list(node_result.artifact_refs),
                evidence_refs=list(node_result.evidence_refs),
                terminal_failure_refs=list(node_result.terminal_failure_refs),
                task_completed_state_update_attempted=False,
            )
            return TaskRunResult(
                run_id=request.run_id,
                task_id=task.id,
                status=WorkflowOutcome.REJECTED,
                checkpoint="",
                workspace=str(workspace),
                branch=request.branch,
                artifact_dir=str(self.store.run_dir),
                attempts=(),
                commit=None,
                message=node_result.message,
            ), node_result

        execution_policy = _execution_policy_for_node(self.execution_policy, request.node)
        task_result = await TaskHarness(
            self.driver,
            workspace_provider=self.workspace_provider,
            runtime_provider=runtime,
            runtime_profile_ref=self.runtime_profile_ref,
            execution_policy=execution_policy,
            runtime_gateway=gateway,
            capability_grants=request.capability_grants,
            plan_id=request.plan.plan_id,
            node_id=request.node.node_id,
            semantic_review_enabled=semantic_review_enabled,
            preserve_failed_workspace=self.preserve_failed_workspace,
        ).run_task(
            task=task,
            workspace_ref=request.workspace_ref,
            branch=request.branch,
            run_id=request.run_id,
            store=self.store,
            parent_policy=request.payload.get("parent_policy"),
        )

        produced_artifact_refs = _manifest_refs(
            self.store.run_dir,
            "artifact-manifest.json",
            "artifacts",
            "artifact_id",
            task.id,
        )
        produced_evidence_refs = _manifest_refs(
            self.store.run_dir,
            "evidence-manifest.json",
            "evidence",
            "evidence_id",
            task.id,
        )
        gate_record = self.store.write_evidence(
            f"nodes/{request.node.node_id}/node-gates.json",
            _node_gate_summary(request, task_result, semantic_review_enabled),
            task_id=task.id,
            kind="node_gate_summary",
            refs=[request.node.node_id, request.plan.plan_id],
        )
        terminal_failure_refs = _terminal_failure_refs(self.store.run_dir, task.id, task_result)
        node_result = NodeExecutionResult(
            node_run_id=node_run_id,
            plan_id=request.plan.plan_id,
            node_id=request.node.node_id,
            node_type=request.node.node_type,
            executor_release=self.release_ref,
            status=_node_status(task_result.status),
            artifact_refs=produced_artifact_refs,
            evidence_refs=(*produced_evidence_refs, gate_record["evidence_id"]),
            gate_refs=request.node.gate_refs,
            terminal_failure_refs=terminal_failure_refs,
            task_completed_state_update_attempted=False,
            usage=_node_usage(
                task_result,
                task,
                semantic_review_enabled=semantic_review_enabled,
            ),
            message=task_result.message,
            details={
                "taskId": task_result.task_id,
                "taskStatus": task_result.status.value,
                "commit": task_result.commit,
                "semanticReviewEnabled": semantic_review_enabled,
                "executionPolicy": _execution_policy_dict(execution_policy),
            },
        )
        node_artifact = self.store.write_artifact(
            f"nodes/{request.node.node_id}/node-run.json",
            node_result.to_dict(),
            task_id=task.id,
            kind="node_run",
            media_type="application/json",
            created_by=f"node-executor:{self.release_ref}",
            input_refs=[request.plan.plan_id, request.node.node_id, request.run_id],
            evidence_refs=[gate_record["evidence_id"]],
        )
        node_result = replace(
            node_result,
            artifact_refs=(node_artifact["artifact_id"], *node_result.artifact_refs),
        )
        self.store.event(
            "node_run_finished",
            run_id=request.run_id,
            node_run_id=node_run_id,
            plan_id=request.plan.plan_id,
            node_id=request.node.node_id,
            status=node_result.status.value,
            artifact_refs=list(node_result.artifact_refs),
            evidence_refs=list(node_result.evidence_refs),
            task_completed_state_update_attempted=False,
        )
        return task_result, node_result


def _execution_policy_for_node(base: ExecutionPolicy, node: PlanNodeIR) -> ExecutionPolicy:
    max_attempts = min(base.max_attempts, max(1, node.retry_policy.max_attempts))
    base = replace(base, max_attempts=max_attempts)
    budget_seconds = _node_wall_timeout_seconds(node)
    if budget_seconds is None:
        return base
    budget_seconds = max(1, int(budget_seconds))
    attempt_wall_timeout_seconds = min(base.attempt_wall_timeout_seconds, budget_seconds)
    run_deadline_seconds = min(base.run_deadline_seconds, budget_seconds)
    idle_timeout_seconds = min(base.idle_timeout_seconds, attempt_wall_timeout_seconds)
    heartbeat_interval_seconds = min(base.heartbeat_interval_seconds, idle_timeout_seconds)
    startup_timeout_seconds = min(base.startup_timeout_seconds, attempt_wall_timeout_seconds)
    return replace(
        base,
        startup_timeout_seconds=startup_timeout_seconds,
        idle_timeout_seconds=idle_timeout_seconds,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
        attempt_wall_timeout_seconds=attempt_wall_timeout_seconds,
        run_deadline_seconds=run_deadline_seconds,
    )


def _node_wall_timeout_seconds(node: PlanNodeIR) -> int | None:
    candidates = [
        value for value in (node.timeout_seconds, node.budget.max_wall_seconds) if value is not None
    ]
    if not candidates:
        return None
    return min(candidates)


def _execution_policy_dict(policy: ExecutionPolicy) -> dict[str, int]:
    return {
        "maxAttempts": policy.max_attempts,
        "startupTimeoutSeconds": policy.startup_timeout_seconds,
        "idleTimeoutSeconds": policy.idle_timeout_seconds,
        "heartbeatIntervalSeconds": policy.heartbeat_interval_seconds,
        "attemptWallTimeoutSeconds": policy.attempt_wall_timeout_seconds,
        "runDeadlineSeconds": policy.run_deadline_seconds,
    }


def build_standard_harness_compatibility_request(
    *,
    task: TaskSpec,
    workspace: Path,
    workspace_ref: str,
    branch: str,
    run_id: str,
    runtime_ref: str | None = None,
) -> NodeExecutionRequest:
    plan, node = compatibility_plan_for_task(
        task=task,
        workspace=workspace,
        run_id=run_id,
        runtime_ref=runtime_ref,
    )
    grants = runtime_grants_for_node(plan, node)
    return NodeExecutionRequest(
        plan=plan,
        node=node,
        capability_grants=grants,
        workspace_ref=workspace_ref,
        branch=branch,
        run_id=run_id,
        payload={
            "task": task,
            "compatibilityMode": "standard-harness",
        },
    )


def compatibility_plan_for_task(
    *,
    task: TaskSpec,
    workspace: Path,
    run_id: str,
    runtime_ref: str | None = None,
) -> tuple[PlanIR, PlanNodeIR]:
    runtime = runtime_ref or "runtime/local-worktree@sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
    command_resources = tuple(
        " ".join(effective_check_argv(workspace, check.argv))
        for check in task.checks
        if check.argv[0] != INTERNAL_ARTIFACT_EXISTS_COMMAND
    )
    capability_grants = [PlanCapabilityGrant.from_request(PlanCapabilityRequest("filesystem.write", task.policy.allowed_globs))]
    if command_resources:
        capability_grants.append(
            PlanCapabilityGrant.from_request(PlanCapabilityRequest("process.exec", command_resources))
        )
    gate_refs = ("GATE-bounded-task-l0", "GATE-bounded-task-review")
    node = PlanNodeIR(
        node_id=f"NODE-{task.id}",
        node_type=PlanNodeType.BOUNDED_TASK.value,
        objective=task.objective,
        claim_refs=tuple(f"CLAIM-{_stable_ref(item)}" for item in task.acceptance_criteria),
        depends_on=(),
        input_refs=(task.id,),
        expected_outputs=(
            PlanOutputContract(
                name="node-run",
                schema_ref="ahra/node-run/0.1",
                delivery_role="artifact",
                artifact_required=True,
            ),
        ),
        capability_grants=tuple(capability_grants),
        gate_refs=gate_refs,
        gate_digests=tuple(canonical_fingerprint({"gateRef": gate_ref}) for gate_ref in gate_refs),
        runtime_ref=runtime,
        runtime_digest=canonical_fingerprint({"runtimeRef": runtime}),
        budget=PlanBudget(
            max_model_calls=max(1, task.max_turns),
            max_tool_calls=max(1, len(task.checks) + 1),
            max_spawned_nodes=0,
            max_cost_usd=0.0,
        ),
        retry_policy=RetryPolicy(
            max_attempts=min(max(task.max_attempts, 1), DEFAULT_MAX_ATTEMPTS),
            retryable_failure_classes=("transient_process_failure",),
            idempotency_key_required=False,
        ),
        timeout_seconds=None,
        compensation_ref=None,
        side_effect="idempotent",
        terminal_goal_verification=False,
        canonical_order=0,
    )
    plan = PlanIR(
        plan_id="PLAN-" + canonical_fingerprint({"taskId": task.id, "runId": run_id}).removeprefix("sha256:")[:16],
        version=1,
        goal_ref=f"GOAL-{_stable_ref(task.id)}",
        goal_digest=canonical_fingerprint({"taskObjective": task.objective}),
        claim_graph_digest=canonical_fingerprint({"criteria": list(task.acceptance_criteria)}),
        nodes=(node,),
        edges=(),
        compiler_version="standard-harness-compat/0.1",
        validation_report_ref=None,
    )
    return plan, node


def runtime_grants_for_node(
    plan: PlanIR,
    node: PlanNodeIR,
    *,
    issued_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> tuple[RuntimeCapabilityGrant, ...]:
    """Legacy standard-harness compatibility shim.

    The dynamic-kernel default Scheduler must use CapabilityAdmissionService and
    must not call this helper.
    """
    issued = issued_at or datetime.now(UTC)
    expires = expires_at or issued + timedelta(hours=2)
    grants: list[RuntimeCapabilityGrant] = []
    for grant in node.capability_grants:
        suffix = canonical_fingerprint(
            {
                "plan": plan.plan_id,
                "node": node.node_id,
                "capability": grant.capability,
                "resources": list(grant.resources),
            }
        ).removeprefix("sha256:")[:16]
        grants.append(
            RuntimeCapabilityGrant(
                grant_id=f"CGRANT-{suffix}",
                request_id=f"CREQ-{suffix}",
                plan_id=plan.plan_id,
                node_id=node.node_id,
                role="executor",
                capability=grant.capability,
                action=grant.capability,
                resources=grant.resources,
                scope=grant.resources,
                expires_at=expires,
                issued_at=issued,
                issuer="harness:bounded-task-node-executor",
                policy_decision_id=f"PDEC-{suffix}",
            )
        )
    return tuple(grants)


def _task_from_request(request: NodeExecutionRequest) -> TaskSpec:
    task = request.payload.get("task")
    if isinstance(task, TaskSpec):
        return task
    write_resources = _filesystem_write_resources(request.node)
    process_commands = _process_exec_resources(request.node)
    process_check_commands = _checkable_process_exec_resources(process_commands)
    artifact_paths = _literal_artifact_paths(write_resources)
    output_requirements = _expected_output_requirements(request.node)
    required_artifacts = tuple(f"Create a non-empty artifact file at {path}." for path in artifact_paths)
    acceptance = _unique(
        (
            *(request.node.claim_refs or (request.node.objective,)),
            *(f"Required artifact exists and is non-empty: {path}" for path in artifact_paths),
            *(f"Expected output is delivered: {output.name}" for output in request.node.expected_outputs),
        )
    )
    requirements = _unique(
        (
            *required_artifacts,
            *output_requirements,
            *(
                (f"Return WorkReport.changed_files containing: {', '.join(artifact_paths)}",)
                if artifact_paths and not process_check_commands
                else ()
            ),
            *(
                (f"Run only granted process.exec verification commands: {', '.join(process_check_commands)}.",)
                if process_check_commands
                else ()
            ),
            *(
                (
                    "Do not run shell or process verification commands; AHRA deterministic gates verify required artifacts after WorkReport.",
                )
                if artifact_paths and not process_check_commands
                else ()
            ),
            *(
                (f"Modify only granted filesystem.write resources: {', '.join(write_resources)}",)
                if write_resources
                else ()
            ),
        )
    )
    objective = request.node.objective
    if artifact_paths:
        objective = f"{objective} Required artifact path(s): {', '.join(artifact_paths)}."
    return TaskSpec(
        id=request.node.node_id.removeprefix("NODE-"),
        title=request.node.objective,
        objective=objective,
        acceptance_criteria=acceptance,
        scope=_unique(
            (
                f"plan:{request.plan.plan_id}",
                f"node:{request.node.node_id}",
                *(f"input:{input_ref}" for input_ref in request.node.input_refs),
            )
        ),
        requirements=requirements,
        checks=(
            *(tuple(_required_artifact_check(path) for path in artifact_paths)),
            *(tuple(_process_exec_check(command) for command in process_check_commands)),
        ),
        policy=ChangePolicy(
            allowed_globs=write_resources or ("**",),
            protected_globs=(),
            sensitive_globs=(),
        ),
    )


def _filesystem_write_resources(node: PlanNodeIR) -> tuple[str, ...]:
    return _unique(
        tuple(
            resource.replace("\\", "/").strip().lstrip("/")
            for grant in node.capability_grants
            if grant.capability == "filesystem.write"
            for resource in grant.resources
            if resource
        )
    )


def _process_exec_resources(node: PlanNodeIR) -> tuple[str, ...]:
    return _unique(
        tuple(
            resource.strip()
            for grant in node.capability_grants
            if grant.capability == "process.exec"
            for resource in grant.resources
            if resource
        )
    )


def _checkable_process_exec_resources(commands: tuple[str, ...]) -> tuple[str, ...]:
    return _unique(tuple(command for command in commands if _is_checkable_process_exec(command)))


def _is_checkable_process_exec(command: str) -> bool:
    tokens = tuple(token.strip("\"'").replace("\\", "/") for token in command.split())
    if not tokens:
        return False
    return any(
        token == "scripts/check.py"
        or token == "./scripts/check.py"
        or token == "scripts/lint_awkp.py"
        or token == "./scripts/lint_awkp.py"
        or fnmatch.fnmatch(token, "scripts/lint_*.py")
        or fnmatch.fnmatch(token, "./scripts/lint_*.py")
        for token in tokens
    )


def _literal_artifact_paths(resources: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        resource
        for resource in resources
        if resource
        and resource != "**"
        and not resource.endswith("/")
        and not any(char in resource for char in "*?[]")
    )


def _expected_output_requirements(node: PlanNodeIR) -> tuple[str, ...]:
    requirements: list[str] = []
    for output in node.expected_outputs:
        parts = [f"Expected output {output.name}"]
        if output.schema_ref:
            parts.append(f"schemaRef={output.schema_ref}")
        if output.delivery_role:
            parts.append(f"deliveryRole={output.delivery_role}")
        parts.append(f"artifactRequired={output.artifact_required}")
        requirements.append(", ".join(parts) + ".")
    return _unique(tuple(requirements))


def _required_artifact_check(path: str) -> CheckSpec:
    return CheckSpec(
        name=f"required artifact exists: {path}",
        argv=(INTERNAL_ARTIFACT_EXISTS_COMMAND, path),
        timeout_seconds=30,
    )


def _process_exec_check(command: str) -> CheckSpec:
    return CheckSpec(
        name=f"granted process.exec: {command}",
        argv=tuple(command.split()),
        timeout_seconds=300,
    )


def _preflight_literal_write_resources(
    *,
    request: NodeExecutionRequest,
    gateway: LocalRuntimeGateway,
    actor: str,
):
    grants = tuple(
        grant
        for grant in request.capability_grants
        if grant.action == "filesystem.write" and grant.denied_resources
    )
    if not grants:
        return None
    resources = _literal_artifact_paths(_filesystem_write_resources(request.node))
    for relative_path in resources:
        grant = _grant_for_resource(grants, relative_path)
        if grant is None:
            continue
        record = gateway.authorize_write_path(
            grant,
            plan_id=request.plan.plan_id,
            node_id=request.node.node_id,
            actor=actor,
            relative_path=relative_path,
        )
        if not record.allowed:
            return record
    return None


def _grant_for_resource(
    grants: tuple[RuntimeCapabilityGrant, ...],
    relative_path: str,
) -> RuntimeCapabilityGrant | None:
    normalized = relative_path.replace("\\", "/")
    for grant in grants:
        if grant.action == "filesystem.write" and any(
            _resource_matches(normalized, pattern)
            for pattern in grant.resources
        ):
            return grant
    return None


def _resource_matches(resource: str, pattern: str) -> bool:
    normalized_pattern = pattern.replace("\\", "/")
    return resource == normalized_pattern or fnmatch.fnmatch(resource, normalized_pattern)


def _unique(items: tuple[str, ...]) -> tuple[str, ...]:
    unique: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = item.strip()
        if value and value not in seen:
            unique.append(value)
            seen.add(value)
    return tuple(unique)


def _validate_runtime_grants(request: NodeExecutionRequest) -> None:
    for grant in request.capability_grants:
        if grant.plan_id != request.plan.plan_id:
            raise ValueError(f"capability grant {grant.grant_id} is bound to a different plan")
        if grant.node_id != request.node.node_id:
            raise ValueError(f"capability grant {grant.grant_id} is bound to a different node")
        if grant.role != "executor":
            raise ValueError(f"capability grant {grant.grant_id} is not bound to executor role")


def _semantic_review_declared(node: PlanNodeIR) -> bool:
    return any("review" in gate_ref.lower() or "semantic" in gate_ref.lower() for gate_ref in node.gate_refs)


def _requires_semantic_code_review(node: PlanNodeIR, runtime_profile_ref: str | None) -> bool:
    return (
        runtime_profile_ref == DEVELOPMENT_BOUNDED_PROFILE_REF
        and any(output.schema_ref == CODE_CHANGE_SCHEMA_REF for output in node.expected_outputs)
    )


def _write_executor_terminal_failure(
    *,
    store: ReferenceRunStore,
    task: TaskSpec,
    request: NodeExecutionRequest,
    node_run_id: str,
    failure_class: str,
    message: str,
    workspace: Path,
) -> tuple[str, str]:
    path = f"tasks/{task.id}/terminal-failure.json"
    record = store.write_evidence(
        path,
        {
            "schema_version": "ahra/workflow-terminal-failure/0.1",
            "task_id": task.id,
            "run_id": request.run_id,
            "plan_id": request.plan.plan_id,
            "node_id": request.node.node_id,
            "node_run_id": node_run_id,
            "status": WorkflowOutcome.REJECTED.value,
            "failure_class": failure_class,
            "summary": message,
            "attempt_count": 0,
            "last_error": message,
            "workspace": str(workspace),
            "branch": request.branch,
            "checkpoint": "",
            "artifact_dir": str(store.run_dir),
            "refs": [request.plan.plan_id, request.node.node_id, node_run_id],
        },
        task_id=task.id,
        kind="terminal_failure",
        refs=[request.plan.plan_id, request.node.node_id, node_run_id],
    )
    store.event(
        "terminal_failure_recorded",
        task_id=task.id,
        status=WorkflowOutcome.REJECTED.value,
        attempt_count=0,
        evidence_id=record["evidence_id"],
    )
    return path, str(record["evidence_id"])


def _node_status(status: WorkflowOutcome) -> NodeExecutionStatus:
    return {
        WorkflowOutcome.ACCEPTED: NodeExecutionStatus.ACCEPTED,
        WorkflowOutcome.NEEDS_HUMAN: NodeExecutionStatus.NEEDS_HUMAN,
        WorkflowOutcome.REJECTED: NodeExecutionStatus.REJECTED,
        WorkflowOutcome.ERROR: NodeExecutionStatus.ERROR,
        WorkflowOutcome.BLOCKED: NodeExecutionStatus.BLOCKED,
        WorkflowOutcome.COMPLETE: NodeExecutionStatus.ACCEPTED,
        WorkflowOutcome.AWAITING_PLAN_APPROVAL: NodeExecutionStatus.NEEDS_HUMAN,
    }[status]


def _node_usage(
    result: TaskRunResult,
    task: TaskSpec,
    *,
    semantic_review_enabled: bool,
) -> NodeExecutionUsage:
    model_calls = 0
    for attempt in result.attempts:
        if attempt.work_report is not None:
            model_calls += 1
        if semantic_review_enabled and attempt.review is not None:
            model_calls += 1
    external_check_count = sum(
        1 for check in task.checks if check.argv[0] != INTERNAL_ARTIFACT_EXISTS_COMMAND
    )
    return NodeExecutionUsage(
        model_calls=model_calls,
        tool_calls=max(1, external_check_count + 1),
        spawned_nodes=0,
        cost_usd=0.0,
    )


def _node_gate_summary(
    request: NodeExecutionRequest,
    task_result: TaskRunResult,
    semantic_review_enabled: bool,
) -> dict[str, Any]:
    attempts = []
    for attempt in task_result.attempts:
        attempts.append(
            {
                "attempt": attempt.attempt,
                "deterministicPassed": attempt.deterministic.passed if attempt.deterministic else False,
                "requiredChecksPassed": attempt.deterministic.required_checks_passed if attempt.deterministic else False,
                "checkExecutionStatus": attempt.deterministic.check_execution_status if attempt.deterministic else None,
                "checkSkipReason": attempt.deterministic.check_skip_reason if attempt.deterministic else None,
                "agentReportedVerificationCommands": (
                    list(attempt.deterministic.agent_reported_verification_commands)
                    if attempt.deterministic
                    else []
                ),
                "reviewVerdict": attempt.review.verdict.value if attempt.review else None,
                "error": attempt.error,
            }
        )
    return {
        "schema_version": "ahra/node-gate-summary/0.1",
        "plan_id": request.plan.plan_id,
        "node_id": request.node.node_id,
        "node_type": request.node.node_type,
        "gate_refs": list(request.node.gate_refs),
        "l0_gates": [
            {
                "gate_ref": gate_ref,
                "kind": "deterministic",
            }
            for gate_ref in request.node.gate_refs
            if "l0" in gate_ref.lower() or "deterministic" in gate_ref.lower()
        ],
        "semantic_review_enabled": semantic_review_enabled,
        "status": task_result.status.value,
        "attempts": attempts,
    }


def _terminal_failure_refs(run_dir: Path, task_id: str, result: TaskRunResult) -> tuple[str, ...]:
    if result.status not in {WorkflowOutcome.ERROR, WorkflowOutcome.REJECTED, WorkflowOutcome.BLOCKED}:
        return ()
    path = run_dir / "tasks" / task_id / "terminal-failure.json"
    if not path.exists():
        return ()
    return (path.relative_to(run_dir).as_posix(),)


def _manifest_refs(run_dir: Path, manifest_name: str, collection: str, ref_key: str, task_id: str) -> tuple[str, ...]:
    manifest_path = run_dir / manifest_name
    if not manifest_path.exists():
        return ()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    refs = []
    for record in data.get(collection, []):
        if record.get("task_id") == task_id and record.get(ref_key):
            refs.append(str(record[ref_key]))
    return tuple(refs)


def _grant_for_command(
    grants: tuple[RuntimeCapabilityGrant, ...],
    command: tuple[str, ...],
) -> RuntimeCapabilityGrant | None:
    command_text = " ".join(command)
    for grant in grants:
        if grant.action == "process.exec" and command_text in grant.resources:
            return grant
    return None


def _denied_exec(message: str) -> dict[str, Any]:
    return {
        "exit_code": None,
        "timed_out": False,
        "stdout": "",
        "stderr": message,
    }


def _stable_ref(value: str) -> str:
    digest = canonical_fingerprint({"value": value}).removeprefix("sha256:")[:16]
    return digest
