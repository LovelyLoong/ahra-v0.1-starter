from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Mapping

from .capabilities import CapabilityGrant as RuntimeCapabilityGrant
from .domain import Lease, utc_now
from .evidence_v2 import canonical_fingerprint
from .node_executor import (
    NodeExecutionRequest,
    NodeExecutionResult,
    NodeExecutionStatus,
    NodeExecutionUsage,
    NodeExecutorRegistry,
)
from .plan_ir import PlanIR, PlanNodeIR, PlanNodeType, PlanValidationReport
from .ports import SchedulerPort, VerificationServicePort
from .verification import VerificationTrigger


class PlanExecutionError(RuntimeError):
    pass


class PlanAdmissionError(PlanExecutionError):
    pass


class PlanVersionConflictError(PlanExecutionError):
    pass


class PlanInvalidTransitionError(PlanExecutionError):
    pass


class PlanLeaseConflictError(PlanExecutionError):
    pass


class PlanExecutionStatus(StrEnum):
    ADMITTED = "admitted"
    RUNNING = "running"
    VERIFYING = "verifying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELING = "canceling"
    CANCELED = "canceled"

    @property
    def terminal(self) -> bool:
        return self in {self.SUCCEEDED, self.FAILED, self.CANCELED}


class NodeRunStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    ADMITTED = "admitted"
    RUNNING = "running"
    VERIFYING = "verifying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PAUSED_INPUT = "paused_input"
    PAUSED_AUTH = "paused_auth"
    TIMED_OUT = "timed_out"
    CANCELED = "canceled"

    @property
    def terminal(self) -> bool:
        return self in {self.SUCCEEDED, self.FAILED, self.TIMED_OUT, self.CANCELED}


PLAN_TRANSITIONS: dict[PlanExecutionStatus, frozenset[PlanExecutionStatus]] = {
    PlanExecutionStatus.ADMITTED: frozenset(
        {PlanExecutionStatus.RUNNING, PlanExecutionStatus.FAILED, PlanExecutionStatus.CANCELED}
    ),
    PlanExecutionStatus.RUNNING: frozenset(
        {
            PlanExecutionStatus.VERIFYING,
            PlanExecutionStatus.FAILED,
            PlanExecutionStatus.CANCELING,
            PlanExecutionStatus.CANCELED,
        }
    ),
    PlanExecutionStatus.VERIFYING: frozenset(
        {PlanExecutionStatus.SUCCEEDED, PlanExecutionStatus.FAILED, PlanExecutionStatus.CANCELING}
    ),
    PlanExecutionStatus.CANCELING: frozenset({PlanExecutionStatus.CANCELED}),
    PlanExecutionStatus.SUCCEEDED: frozenset(),
    PlanExecutionStatus.FAILED: frozenset(),
    PlanExecutionStatus.CANCELED: frozenset(),
}

NODE_TRANSITIONS: dict[NodeRunStatus, frozenset[NodeRunStatus]] = {
    NodeRunStatus.PENDING: frozenset({NodeRunStatus.READY, NodeRunStatus.CANCELED}),
    NodeRunStatus.READY: frozenset({NodeRunStatus.ADMITTED, NodeRunStatus.CANCELED}),
    NodeRunStatus.ADMITTED: frozenset({NodeRunStatus.RUNNING, NodeRunStatus.CANCELED}),
    NodeRunStatus.RUNNING: frozenset(
        {
            NodeRunStatus.VERIFYING,
            NodeRunStatus.FAILED,
            NodeRunStatus.PAUSED_INPUT,
            NodeRunStatus.PAUSED_AUTH,
            NodeRunStatus.TIMED_OUT,
            NodeRunStatus.CANCELED,
        }
    ),
    NodeRunStatus.VERIFYING: frozenset(
        {NodeRunStatus.SUCCEEDED, NodeRunStatus.FAILED, NodeRunStatus.CANCELED}
    ),
    NodeRunStatus.PAUSED_INPUT: frozenset({NodeRunStatus.RUNNING, NodeRunStatus.CANCELED}),
    NodeRunStatus.PAUSED_AUTH: frozenset({NodeRunStatus.RUNNING, NodeRunStatus.CANCELED}),
    NodeRunStatus.SUCCEEDED: frozenset(),
    NodeRunStatus.FAILED: frozenset(),
    NodeRunStatus.TIMED_OUT: frozenset(),
    NodeRunStatus.CANCELED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class PlanCheckpointRecord:
    checkpoint_id: str
    plan_execution_id: str
    plan_id: str
    plan_digest: str
    plan_status: PlanExecutionStatus
    node_statuses: Mapping[str, str]
    node_budgets: Mapping[str, Mapping[str, Any]]
    node_usage: Mapping[str, Mapping[str, Any]]
    artifact_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "ahra/plan-checkpoint/0.1",
            "checkpoint_id": self.checkpoint_id,
            "plan_execution_id": self.plan_execution_id,
            "plan_id": self.plan_id,
            "plan_digest": self.plan_digest,
            "plan_status": self.plan_status.value,
            "node_statuses": dict(self.node_statuses),
            "node_budgets": {node_run_id: dict(budget) for node_run_id, budget in self.node_budgets.items()},
            "node_usage": {node_run_id: dict(usage) for node_run_id, usage in self.node_usage.items()},
            "artifact_refs": list(self.artifact_refs),
            "evidence_refs": list(self.evidence_refs),
            "created_at": _iso(self.created_at),
        }


@dataclass(frozen=True, slots=True)
class NodeRunRecord:
    node_run_id: str
    plan_execution_id: str
    plan_id: str
    plan_digest: str
    node_id: str
    node_type: str
    attempt: int
    status: NodeRunStatus
    status_version: int
    dependency_node_refs: tuple[str, ...]
    gate_refs: tuple[str, ...]
    budget: Mapping[str, Any] = field(default_factory=dict)
    usage: Mapping[str, Any] = field(default_factory=dict)
    artifact_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    terminal_failure_refs: tuple[str, ...] = ()
    executor_release: str | None = None
    lease: Lease | None = None
    failure_class: str | None = None
    message: str = ""
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schema_version": "ahra/node-run-state/0.1",
            "node_run_id": self.node_run_id,
            "plan_execution_id": self.plan_execution_id,
            "plan_id": self.plan_id,
            "plan_digest": self.plan_digest,
            "node_id": self.node_id,
            "node_type": self.node_type,
            "attempt": self.attempt,
            "status": self.status.value,
            "status_version": self.status_version,
            "dependency_node_refs": list(self.dependency_node_refs),
            "gate_refs": list(self.gate_refs),
            "budget": dict(self.budget),
            "usage": dict(self.usage),
            "artifact_refs": list(self.artifact_refs),
            "evidence_refs": list(self.evidence_refs),
            "terminal_failure_refs": list(self.terminal_failure_refs),
            "executor_release": self.executor_release,
            "lease": _lease_to_dict(self.lease),
            "failure_class": self.failure_class,
            "message": self.message,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
        }
        return data


@dataclass(frozen=True, slots=True)
class PlanExecutionRecord:
    plan_execution_id: str
    plan_id: str
    plan_version: int
    plan_digest: str
    goal_ref: str
    validation_report_ref: str
    validation_report_digest: str
    status: PlanExecutionStatus
    status_version: int
    max_concurrency: int
    budget_summary: Mapping[str, Any]
    node_run_refs: tuple[str, ...]
    task_ref: str | None = None
    lease: Lease | None = None
    checkpoint_ref: str | None = None
    artifact_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    trace_refs: tuple[str, ...] = ()
    handoff_refs: tuple[str, ...] = ()
    cancel_requested: bool = False
    deadline_at: datetime | None = None
    failure_class: str | None = None
    message: str = ""
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "ahra/plan-execution/0.1",
            "plan_execution_id": self.plan_execution_id,
            "plan_id": self.plan_id,
            "plan_version": self.plan_version,
            "plan_digest": self.plan_digest,
            "goal_ref": self.goal_ref,
            "task_ref": self.task_ref,
            "validation_report_ref": self.validation_report_ref,
            "validation_report_digest": self.validation_report_digest,
            "status": self.status.value,
            "status_version": self.status_version,
            "max_concurrency": self.max_concurrency,
            "budget_summary": dict(self.budget_summary),
            "node_run_refs": list(self.node_run_refs),
            "lease": _lease_to_dict(self.lease),
            "checkpoint_ref": self.checkpoint_ref,
            "artifact_refs": list(self.artifact_refs),
            "evidence_refs": list(self.evidence_refs),
            "trace_refs": list(self.trace_refs),
            "handoff_refs": list(self.handoff_refs),
            "cancel_requested": self.cancel_requested,
            "deadline_at": _iso(self.deadline_at) if self.deadline_at else None,
            "failure_class": self.failure_class,
            "message": self.message,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
        }


@dataclass(frozen=True, slots=True)
class AwkpTaskProjection:
    task_id: str
    goal_ref: str
    plan_execution_id: str
    plan_status: PlanExecutionStatus
    task_state_recommendation: str
    artifact_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    authority_refs: Mapping[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "ahra/awkp-task-projection/0.1",
            "task_id": self.task_id,
            "goal_ref": self.goal_ref,
            "plan_execution_id": self.plan_execution_id,
            "plan_status": self.plan_status.value,
            "task_state_recommendation": self.task_state_recommendation,
            "artifact_refs": list(self.artifact_refs),
            "evidence_refs": list(self.evidence_refs),
            "authority_refs": dict(self.authority_refs),
        }


@dataclass(frozen=True, slots=True)
class ReconcilerFinding:
    code: str
    severity: str
    message: str
    refs: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "refs": list(self.refs),
        }


class InMemoryPlanExecutionStore:
    def __init__(self) -> None:
        self._executions: dict[str, PlanExecutionRecord] = {}
        self._nodes: dict[str, NodeRunRecord] = {}
        self._checkpoints: dict[str, PlanCheckpointRecord] = {}
        self._lock = threading.RLock()

    def create_execution(
        self,
        execution: PlanExecutionRecord,
        node_runs: tuple[NodeRunRecord, ...],
    ) -> None:
        with self._lock:
            if execution.plan_execution_id in self._executions:
                raise PlanVersionConflictError(f"plan execution already exists: {execution.plan_execution_id}")
            duplicate_nodes = [node.node_run_id for node in node_runs if node.node_run_id in self._nodes]
            if duplicate_nodes:
                raise PlanVersionConflictError(f"node run already exists: {duplicate_nodes[0]}")
            self._executions[execution.plan_execution_id] = execution
            for node in node_runs:
                self._nodes[node.node_run_id] = node

    def get_execution(self, plan_execution_id: str) -> PlanExecutionRecord:
        with self._lock:
            try:
                return self._executions[plan_execution_id]
            except KeyError as exc:
                raise KeyError(plan_execution_id) from exc

    def compare_and_swap_execution(
        self,
        execution: PlanExecutionRecord,
        expected_version: int,
    ) -> PlanExecutionRecord:
        with self._lock:
            current = self.get_execution(execution.plan_execution_id)
            if current.status_version != expected_version:
                raise PlanVersionConflictError(
                    f"expected execution version {expected_version}, current {current.status_version}"
                )
            if execution.status_version != expected_version + 1:
                raise PlanVersionConflictError("execution status_version must increment exactly once")
            self._executions[execution.plan_execution_id] = execution
            return execution

    def put_node_run(self, node_run: NodeRunRecord) -> None:
        with self._lock:
            if node_run.node_run_id in self._nodes:
                raise PlanVersionConflictError(f"node run already exists: {node_run.node_run_id}")
            self._nodes[node_run.node_run_id] = node_run

    def get_node_run(self, node_run_id: str) -> NodeRunRecord:
        with self._lock:
            try:
                return self._nodes[node_run_id]
            except KeyError as exc:
                raise KeyError(node_run_id) from exc

    def compare_and_swap_node(
        self,
        node_run: NodeRunRecord,
        expected_version: int,
    ) -> NodeRunRecord:
        with self._lock:
            current = self.get_node_run(node_run.node_run_id)
            if current.status_version != expected_version:
                raise PlanVersionConflictError(
                    f"expected node version {expected_version}, current {current.status_version}"
                )
            if node_run.status_version != expected_version + 1:
                raise PlanVersionConflictError("node status_version must increment exactly once")
            self._nodes[node_run.node_run_id] = node_run
            return node_run

    def list_node_runs(self, plan_execution_id: str) -> tuple[NodeRunRecord, ...]:
        with self._lock:
            nodes = [node for node in self._nodes.values() if node.plan_execution_id == plan_execution_id]
        return tuple(sorted(nodes, key=lambda node: (node.node_id, node.attempt)))

    def put_checkpoint(self, checkpoint: PlanCheckpointRecord) -> None:
        with self._lock:
            self._checkpoints[checkpoint.checkpoint_id] = checkpoint

    def get_checkpoint(self, checkpoint_ref: str) -> PlanCheckpointRecord:
        checkpoint_id = checkpoint_ref.removeprefix("checkpoint://")
        with self._lock:
            try:
                return self._checkpoints[checkpoint_id]
            except KeyError as exc:
                raise KeyError(checkpoint_ref) from exc


class PlanExecutionService:
    def __init__(self, store: InMemoryPlanExecutionStore) -> None:
        self.store = store

    def start_execution(
        self,
        plan: PlanIR,
        validation_report: PlanValidationReport,
        *,
        task_ref: str | None = None,
        max_concurrency: int = 1,
        deadline_at: datetime | None = None,
        now: datetime | None = None,
    ) -> PlanExecutionRecord:
        _assert_admitted_plan(plan, validation_report)
        if max_concurrency < 1:
            raise PlanAdmissionError("max_concurrency must be at least 1")
        now = now or utc_now()
        plan_digest = plan.digest()
        plan_execution_id = _plan_execution_id(plan)
        node_runs = tuple(
            NodeRunRecord(
                node_run_id=_node_run_id(plan_execution_id, node.node_id, 1),
                plan_execution_id=plan_execution_id,
                plan_id=plan.plan_id,
                plan_digest=plan_digest,
                node_id=node.node_id,
                node_type=node.node_type,
                attempt=1,
                status=NodeRunStatus.PENDING,
                status_version=0,
                dependency_node_refs=node.depends_on,
                gate_refs=node.gate_refs,
                budget=node.budget.to_dict(),
                created_at=now,
                updated_at=now,
            )
            for node in plan.nodes
        )
        execution = PlanExecutionRecord(
            plan_execution_id=plan_execution_id,
            plan_id=plan.plan_id,
            plan_version=plan.version,
            plan_digest=plan_digest,
            goal_ref=plan.goal_ref,
            validation_report_ref=validation_report.report_id,
            validation_report_digest=canonical_fingerprint(validation_report.to_dict()),
            status=PlanExecutionStatus.ADMITTED,
            status_version=0,
            max_concurrency=max_concurrency,
            budget_summary=_plan_budget_summary(plan),
            node_run_refs=tuple(node.node_run_id for node in node_runs),
            task_ref=task_ref,
            trace_refs=(f"TRACE-{plan_execution_id}",),
            deadline_at=deadline_at,
            message="Admitted immutable PlanIR is ready for static scheduling.",
            created_at=now,
            updated_at=now,
        )
        self.store.create_execution(execution, node_runs)
        self._checkpoint(execution.plan_execution_id, now=now)
        return self.store.get_execution(execution.plan_execution_id)

    def acquire_plan_lease(
        self,
        plan_execution_id: str,
        *,
        holder: str,
        ttl_seconds: int,
        expected_version: int,
        now: datetime | None = None,
    ) -> PlanExecutionRecord:
        now = now or utc_now()
        current = self.store.get_execution(plan_execution_id)
        _ensure_active_state(current.status)
        if current.lease and current.lease.active_at(now) and current.lease.holder != holder:
            raise PlanLeaseConflictError("active plan execution lease is held by another worker")
        next_token = (current.lease.fencing_token + 1) if current.lease else 1
        return self.store.compare_and_swap_execution(
            replace(
                current,
                lease=Lease(
                    holder=holder,
                    fencing_token=next_token,
                    heartbeat_at=now,
                    expires_at=now + timedelta(seconds=ttl_seconds),
                ),
                status_version=current.status_version + 1,
                updated_at=now,
            ),
            expected_version,
        )

    def transition_execution(
        self,
        plan_execution_id: str,
        to_status: PlanExecutionStatus,
        *,
        expected_version: int,
        holder: str | None = None,
        fencing_token: int | None = None,
        failure_class: str | None = None,
        message: str = "",
        artifact_refs: tuple[str, ...] | None = None,
        evidence_refs: tuple[str, ...] | None = None,
        handoff_refs: tuple[str, ...] | None = None,
        now: datetime | None = None,
    ) -> PlanExecutionRecord:
        now = now or utc_now()
        current = self.store.get_execution(plan_execution_id)
        if to_status not in PLAN_TRANSITIONS[current.status]:
            raise PlanInvalidTransitionError(f"{current.status.value} -> {to_status.value} is not allowed")
        _check_lease(current.lease, holder, fencing_token, now)
        updated = replace(
            current,
            status=to_status,
            status_version=current.status_version + 1,
            lease=None if to_status.terminal else current.lease,
            artifact_refs=_merge_refs(current.artifact_refs, artifact_refs or ()),
            evidence_refs=_merge_refs(current.evidence_refs, evidence_refs or ()),
            handoff_refs=_merge_refs(current.handoff_refs, handoff_refs or ()),
            failure_class=failure_class,
            message=message or current.message,
            updated_at=now,
        )
        result = self.store.compare_and_swap_execution(updated, expected_version)
        self._checkpoint(plan_execution_id, now=now)
        return self.store.get_execution(result.plan_execution_id)

    def acquire_node_lease(
        self,
        node_run_id: str,
        *,
        holder: str,
        ttl_seconds: int,
        expected_version: int,
        now: datetime | None = None,
    ) -> NodeRunRecord:
        now = now or utc_now()
        current = self.store.get_node_run(node_run_id)
        if current.status.terminal:
            raise PlanLeaseConflictError(f"cannot lease terminal node {current.status.value}")
        if current.lease and current.lease.active_at(now) and current.lease.holder != holder:
            raise PlanLeaseConflictError("active node lease is held by another worker")
        next_token = (current.lease.fencing_token + 1) if current.lease else 1
        return self.store.compare_and_swap_node(
            replace(
                current,
                lease=Lease(
                    holder=holder,
                    fencing_token=next_token,
                    heartbeat_at=now,
                    expires_at=now + timedelta(seconds=ttl_seconds),
                ),
                status_version=current.status_version + 1,
                updated_at=now,
            ),
            expected_version,
        )

    def transition_node(
        self,
        node_run_id: str,
        to_status: NodeRunStatus,
        *,
        expected_version: int,
        holder: str | None = None,
        fencing_token: int | None = None,
        executor_release: str | None = None,
        artifact_refs: tuple[str, ...] = (),
        evidence_refs: tuple[str, ...] = (),
        terminal_failure_refs: tuple[str, ...] = (),
        usage: Mapping[str, Any] | None = None,
        failure_class: str | None = None,
        message: str = "",
        now: datetime | None = None,
    ) -> NodeRunRecord:
        now = now or utc_now()
        current = self.store.get_node_run(node_run_id)
        if to_status not in NODE_TRANSITIONS[current.status]:
            raise PlanInvalidTransitionError(f"{current.status.value} -> {to_status.value} is not allowed")
        _check_lease(current.lease, holder, fencing_token, now)
        updated = replace(
            current,
            status=to_status,
            status_version=current.status_version + 1,
            executor_release=executor_release or current.executor_release,
            artifact_refs=_merge_refs(current.artifact_refs, artifact_refs),
            evidence_refs=_merge_refs(current.evidence_refs, evidence_refs),
            terminal_failure_refs=_merge_refs(current.terminal_failure_refs, terminal_failure_refs),
            usage=dict(usage) if usage is not None else current.usage,
            failure_class=failure_class,
            message=message or current.message,
            lease=None if to_status.terminal else current.lease,
            updated_at=now,
        )
        result = self.store.compare_and_swap_node(updated, expected_version)
        self._checkpoint(result.plan_execution_id, now=now)
        return result

    def create_retry_node(self, previous: NodeRunRecord, *, now: datetime | None = None) -> NodeRunRecord:
        now = now or utc_now()
        next_attempt = previous.attempt + 1
        retry = NodeRunRecord(
            node_run_id=_node_run_id(previous.plan_execution_id, previous.node_id, next_attempt),
            plan_execution_id=previous.plan_execution_id,
            plan_id=previous.plan_id,
            plan_digest=previous.plan_digest,
            node_id=previous.node_id,
            node_type=previous.node_type,
            attempt=next_attempt,
            status=NodeRunStatus.PENDING,
            status_version=0,
            dependency_node_refs=previous.dependency_node_refs,
            gate_refs=previous.gate_refs,
            budget=dict(previous.budget),
            created_at=now,
            updated_at=now,
            message=f"Retry after {previous.node_run_id}: {previous.failure_class or 'failed'}",
        )
        self.store.put_node_run(retry)
        execution = self.store.get_execution(previous.plan_execution_id)
        updated = replace(
            execution,
            node_run_refs=(*execution.node_run_refs, retry.node_run_id),
            status_version=execution.status_version + 1,
            updated_at=now,
        )
        self.store.compare_and_swap_execution(updated, execution.status_version)
        self._checkpoint(previous.plan_execution_id, now=now)
        return retry

    def cancel_execution(
        self,
        plan_execution_id: str,
        *,
        expected_version: int,
        holder: str | None = None,
        fencing_token: int | None = None,
        reason: str = "cancellation requested",
        now: datetime | None = None,
    ) -> PlanExecutionRecord:
        now = now or utc_now()
        current = self.store.get_execution(plan_execution_id)
        if current.status.terminal:
            return current
        _check_lease(current.lease, holder, fencing_token, now)
        canceling = replace(
            current,
            status=PlanExecutionStatus.CANCELING,
            status_version=current.status_version + 1,
            cancel_requested=True,
            message=reason,
            updated_at=now,
        )
        self.store.compare_and_swap_execution(canceling, expected_version)
        for node in self.store.list_node_runs(plan_execution_id):
            latest = self.store.get_node_run(node.node_run_id)
            if not latest.status.terminal:
                self.store.compare_and_swap_node(
                    replace(
                        latest,
                        status=NodeRunStatus.CANCELED,
                        status_version=latest.status_version + 1,
                        lease=None,
                        message=reason,
                        updated_at=now,
                    ),
                    latest.status_version,
                )
        canceled = replace(
            self.store.get_execution(plan_execution_id),
            status=PlanExecutionStatus.CANCELED,
            status_version=canceling.status_version + 1,
            lease=None,
            message=reason,
            handoff_refs=_merge_refs(current.handoff_refs, (f"HANDOFF-{plan_execution_id}-canceled",)),
            updated_at=now,
        )
        result = self.store.compare_and_swap_execution(canceled, canceling.status_version)
        self._checkpoint(plan_execution_id, now=now)
        return self.store.get_execution(result.plan_execution_id)

    def _checkpoint(self, plan_execution_id: str, *, now: datetime | None = None) -> PlanCheckpointRecord:
        now = now or utc_now()
        execution = self.store.get_execution(plan_execution_id)
        nodes = self.store.list_node_runs(plan_execution_id)
        artifact_refs = tuple(ref for node in nodes for ref in node.artifact_refs)
        evidence_refs = tuple(ref for node in nodes for ref in node.evidence_refs)
        checkpoint_id = "CHK-" + canonical_fingerprint(
            {
                "planExecution": plan_execution_id,
                "status": execution.status.value,
                "version": execution.status_version,
                "nodes": {node.node_run_id: node.status.value for node in nodes},
            }
        ).removeprefix("sha256:")[:16]
        checkpoint = PlanCheckpointRecord(
            checkpoint_id=checkpoint_id,
            plan_execution_id=plan_execution_id,
            plan_id=execution.plan_id,
            plan_digest=execution.plan_digest,
            plan_status=execution.status,
            node_statuses={node.node_run_id: node.status.value for node in nodes},
            node_budgets={node.node_run_id: node.budget for node in nodes},
            node_usage={node.node_run_id: node.usage for node in nodes},
            artifact_refs=artifact_refs,
            evidence_refs=evidence_refs,
            created_at=now,
        )
        self.store.put_checkpoint(checkpoint)
        if execution.checkpoint_ref != f"checkpoint://{checkpoint_id}":
            updated = replace(
                execution,
                checkpoint_ref=f"checkpoint://{checkpoint_id}",
                artifact_refs=_merge_refs(execution.artifact_refs, artifact_refs),
                evidence_refs=_merge_refs(execution.evidence_refs, evidence_refs),
                updated_at=now,
            )
            # Checkpoint pointers are derived from current state; keep CAS strict.
            self.store.compare_and_swap_execution(
                replace(updated, status_version=execution.status_version + 1),
                execution.status_version,
            )
        return checkpoint


class StaticPlanScheduler(SchedulerPort):
    def __init__(
        self,
        *,
        service: PlanExecutionService,
        executor_registry: NodeExecutorRegistry,
        executor_release_refs: Mapping[str, str],
        verification_service: VerificationServicePort | None = None,
        max_concurrency: int = 1,
        lease_holder: str = "scheduler:static-planir",
        lease_ttl_seconds: int = 300,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")
        self.service = service
        self.executor_registry = executor_registry
        self.executor_release_refs = dict(executor_release_refs)
        self.verification_service = verification_service
        self.max_concurrency = max_concurrency
        self.lease_holder = lease_holder
        self.lease_ttl_seconds = lease_ttl_seconds

    def submit_plan(self, plan: PlanIR, validation_report: PlanValidationReport) -> str:
        execution = self.service.start_execution(
            plan,
            validation_report,
            max_concurrency=self.max_concurrency,
        )
        return execution.plan_execution_id

    async def run_until_terminal(
        self,
        plan: PlanIR,
        plan_execution_id: str,
        *,
        workspace_ref: str,
        branch: str,
    ) -> PlanExecutionRecord:
        while True:
            execution = self.service.store.get_execution(plan_execution_id)
            if execution.status.terminal:
                return execution
            ran = await self.run_ready_nodes_once(
                plan,
                plan_execution_id,
                workspace_ref=workspace_ref,
                branch=branch,
            )
            execution = self.service.store.get_execution(plan_execution_id)
            if execution.status.terminal:
                return execution
            if not ran:
                return self._finalize_or_fail(plan, execution)

    async def run_ready_nodes_once(
        self,
        plan: PlanIR,
        plan_execution_id: str,
        *,
        workspace_ref: str,
        branch: str,
    ) -> bool:
        execution = self.service.store.get_execution(plan_execution_id)
        if execution.status == PlanExecutionStatus.ADMITTED:
            execution = self.service.transition_execution(
                plan_execution_id,
                PlanExecutionStatus.RUNNING,
                expected_version=execution.status_version,
                message="Static PlanIR DAG scheduling started.",
            )
        if execution.status != PlanExecutionStatus.RUNNING:
            return False
        if execution.deadline_at and utc_now() >= execution.deadline_at:
            self.service.transition_execution(
                plan_execution_id,
                PlanExecutionStatus.FAILED,
                expected_version=execution.status_version,
                failure_class="deadline_exceeded",
                message="PlanExecution deadline elapsed before the DAG completed.",
            )
            return False

        ready = self._ready_node_runs(plan, plan_execution_id)
        if not ready:
            return False
        batch = ready[: execution.max_concurrency]
        await asyncio.gather(
            *(
                self._run_node(plan, node_run, workspace_ref=workspace_ref, branch=branch)
                for node_run in batch
            )
        )
        return True

    async def _run_node(
        self,
        plan: PlanIR,
        node_run: NodeRunRecord,
        *,
        workspace_ref: str,
        branch: str,
    ) -> None:
        node = _node_by_id(plan, node_run.node_id)
        current = self.service.store.get_node_run(node_run.node_run_id)
        if current.status == NodeRunStatus.PENDING:
            current = self.service.transition_node(
                current.node_run_id,
                NodeRunStatus.READY,
                expected_version=current.status_version,
                message="Dependencies are satisfied.",
            )
        current = self.service.transition_node(
            current.node_run_id,
            NodeRunStatus.ADMITTED,
            expected_version=current.status_version,
            message="Node admitted for execution.",
        )
        current = self.service.acquire_node_lease(
            current.node_run_id,
            holder=self.lease_holder,
            ttl_seconds=self.lease_ttl_seconds,
            expected_version=current.status_version,
        )
        current = self.service.transition_node(
            current.node_run_id,
            NodeRunStatus.RUNNING,
            expected_version=current.status_version,
            holder=current.lease.holder if current.lease else None,
            fencing_token=current.lease.fencing_token if current.lease else None,
            message="Node is running.",
        )
        if node.node_type == PlanNodeType.GOAL_VERIFICATION.value:
            self._run_goal_verification_node(current, node)
            return
        if node.node_type == PlanNodeType.GATE_VERIFICATION.value:
            self._run_gate_verification_node(current, node)
            return

        release_ref = self.executor_release_refs.get(node.node_type)
        if not release_ref:
            self._fail_node(current, "missing_executor_release", f"No executor release for {node.node_type}")
            return
        executor = self.executor_registry.get(node.node_type, release_ref)
        request = NodeExecutionRequest(
            plan=plan,
            node=node,
            capability_grants=_runtime_grants_for_node(plan, node),
            workspace_ref=workspace_ref,
            branch=branch,
            run_id=current.node_run_id,
        )
        try:
            timeout_seconds = _node_wall_timeout_seconds(node)
            if timeout_seconds:
                result = await asyncio.wait_for(executor.execute(request), timeout=timeout_seconds)
            else:
                result = await executor.execute(request)
        except TimeoutError:
            self.service.transition_node(
                current.node_run_id,
                NodeRunStatus.TIMED_OUT,
                expected_version=self.service.store.get_node_run(current.node_run_id).status_version,
                holder=self.lease_holder,
                fencing_token=current.lease.fencing_token if current.lease else None,
                failure_class="timeout",
                message="Node executor timed out.",
            )
            self._maybe_retry(plan, self.service.store.get_node_run(current.node_run_id), "timeout")
            return
        except Exception as exc:  # pragma: no cover - defensive boundary
            self._fail_node(current, "executor_exception", str(exc))
            return
        self._record_executor_result(plan, node, current, result)

    def _record_executor_result(
        self,
        plan: PlanIR,
        node: PlanNodeIR,
        current: NodeRunRecord,
        result: NodeExecutionResult,
    ) -> None:
        latest = self.service.store.get_node_run(current.node_run_id)
        if result.status == NodeExecutionStatus.ACCEPTED:
            violation = _budget_violation(node, result.usage)
            if violation:
                failure_class, message = violation
                failed = self.service.transition_node(
                    latest.node_run_id,
                    NodeRunStatus.FAILED,
                    expected_version=latest.status_version,
                    holder=self.lease_holder,
                    fencing_token=current.lease.fencing_token if current.lease else None,
                    executor_release=result.executor_release,
                    artifact_refs=result.artifact_refs,
                    evidence_refs=result.evidence_refs,
                    terminal_failure_refs=(
                        *result.terminal_failure_refs,
                        f"BUDGET-{node.node_id.removeprefix('NODE-')}",
                    ),
                    usage=result.usage.to_dict() if result.usage else {},
                    failure_class=failure_class,
                    message=message,
                )
                self._maybe_retry(plan, failed, failure_class)
                return

            verifying = self.service.transition_node(
                latest.node_run_id,
                NodeRunStatus.VERIFYING,
                expected_version=latest.status_version,
                holder=self.lease_holder,
                fencing_token=current.lease.fencing_token if current.lease else None,
                executor_release=result.executor_release,
                artifact_refs=result.artifact_refs,
                evidence_refs=result.evidence_refs,
                terminal_failure_refs=result.terminal_failure_refs,
                usage=result.usage.to_dict() if result.usage else {},
                message=result.message,
            )
            if node.gate_refs and not self.verification_service:
                self.service.transition_node(
                    verifying.node_run_id,
                    NodeRunStatus.FAILED,
                    expected_version=verifying.status_version,
                    holder=self.lease_holder,
                    fencing_token=current.lease.fencing_token if current.lease else None,
                    failure_class="verification_service_unavailable",
                    terminal_failure_refs=(f"VERIFY-{node.node_id.removeprefix('NODE-')}",),
                    message="Declared gate verification requires VerificationService.",
                )
                return
            if self.verification_service and node.gate_refs:
                self.verification_service.select(
                    VerificationTrigger(
                        changed_refs={ref: "current" for ref in (*result.artifact_refs, *result.evidence_refs)}
                    )
                )
            self.service.transition_node(
                verifying.node_run_id,
                NodeRunStatus.SUCCEEDED,
                expected_version=verifying.status_version,
                holder=self.lease_holder,
                fencing_token=current.lease.fencing_token if current.lease else None,
                executor_release=result.executor_release,
                artifact_refs=result.artifact_refs,
                evidence_refs=result.evidence_refs,
                terminal_failure_refs=result.terminal_failure_refs,
                usage=result.usage.to_dict() if result.usage else {},
                message=result.message or "Node gates passed.",
            )
            return

        failure_class = str(result.details.get("failureClass") or result.status.value)
        failed = self.service.transition_node(
            latest.node_run_id,
            _failure_status(result.status),
            expected_version=latest.status_version,
            holder=self.lease_holder,
            fencing_token=current.lease.fencing_token if current.lease else None,
            executor_release=result.executor_release,
            artifact_refs=result.artifact_refs,
            evidence_refs=result.evidence_refs,
            terminal_failure_refs=result.terminal_failure_refs,
            usage=result.usage.to_dict() if result.usage else {},
            failure_class=failure_class,
            message=result.message or failure_class,
        )
        self._maybe_retry(plan, failed, failure_class)

    def _run_gate_verification_node(self, node_run: NodeRunRecord, node: PlanNodeIR) -> None:
        latest = self.service.store.get_node_run(node_run.node_run_id)
        if not self.verification_service:
            self.service.transition_node(
                latest.node_run_id,
                NodeRunStatus.FAILED,
                expected_version=latest.status_version,
                holder=self.lease_holder,
                fencing_token=node_run.lease.fencing_token if node_run.lease else None,
                failure_class="verification_service_unavailable",
                terminal_failure_refs=(f"VERIFY-{node.node_id.removeprefix('NODE-')}",),
                message="Declared gate verification requires VerificationService.",
            )
            return

        usage = _verification_usage()
        violation = _budget_violation(node, usage)
        if violation:
            failure_class, message = violation
            self.service.transition_node(
                latest.node_run_id,
                NodeRunStatus.FAILED,
                expected_version=latest.status_version,
                holder=self.lease_holder,
                fencing_token=node_run.lease.fencing_token if node_run.lease else None,
                terminal_failure_refs=(f"BUDGET-{node.node_id.removeprefix('NODE-')}",),
                usage=usage.to_dict(),
                failure_class=failure_class,
                message=message,
            )
            return

        self.verification_service.select(VerificationTrigger(failed_gate_refs=frozenset(latest.gate_refs)))
        verifying = self.service.transition_node(
            latest.node_run_id,
            NodeRunStatus.VERIFYING,
            expected_version=latest.status_version,
            holder=self.lease_holder,
            fencing_token=node_run.lease.fencing_token if node_run.lease else None,
            evidence_refs=tuple(f"EVD-{gate_ref.removeprefix('GATE-')}" for gate_ref in latest.gate_refs),
            usage=usage.to_dict(),
            message="Declared gate verification boundary ran.",
        )
        self.service.transition_node(
            verifying.node_run_id,
            NodeRunStatus.SUCCEEDED,
            expected_version=verifying.status_version,
            holder=self.lease_holder,
            fencing_token=node_run.lease.fencing_token if node_run.lease else None,
            usage=usage.to_dict(),
            message="Gate verification boundary passed.",
        )

    def _run_goal_verification_node(self, node_run: NodeRunRecord, node: PlanNodeIR) -> None:
        latest = self.service.store.get_node_run(node_run.node_run_id)
        if not self.verification_service:
            self.service.transition_node(
                latest.node_run_id,
                NodeRunStatus.FAILED,
                expected_version=latest.status_version,
                holder=self.lease_holder,
                fencing_token=node_run.lease.fencing_token if node_run.lease else None,
                failure_class="verification_service_unavailable",
                terminal_failure_refs=(f"VERIFY-{node.node_id.removeprefix('NODE-')}",),
                message="Goal completion gate requires VerificationService.",
            )
            return

        usage = _verification_usage()
        violation = _budget_violation(node, usage)
        if violation:
            failure_class, message = violation
            self.service.transition_node(
                latest.node_run_id,
                NodeRunStatus.FAILED,
                expected_version=latest.status_version,
                holder=self.lease_holder,
                fencing_token=node_run.lease.fencing_token if node_run.lease else None,
                terminal_failure_refs=(f"BUDGET-{node.node_id.removeprefix('NODE-')}",),
                usage=usage.to_dict(),
                failure_class=failure_class,
                message=message,
            )
            return

        completion = self.verification_service.complete(VerificationTrigger())
        verifying = self.service.transition_node(
            latest.node_run_id,
            NodeRunStatus.VERIFYING,
            expected_version=latest.status_version,
            holder=self.lease_holder,
            fencing_token=node_run.lease.fencing_token if node_run.lease else None,
            evidence_refs=tuple(f"EVD-{gate_ref.removeprefix('GATE-')}" for gate_ref in latest.gate_refs),
            usage=usage.to_dict(),
            message="Goal completion gate evaluated.",
        )
        if completion.complete:
            self.service.transition_node(
                verifying.node_run_id,
                NodeRunStatus.SUCCEEDED,
                expected_version=verifying.status_version,
                holder=self.lease_holder,
                fencing_token=node_run.lease.fencing_token if node_run.lease else None,
                usage=usage.to_dict(),
                message="Goal completion gate passed.",
            )
        else:
            self.service.transition_node(
                verifying.node_run_id,
                NodeRunStatus.FAILED,
                expected_version=verifying.status_version,
                holder=self.lease_holder,
                fencing_token=node_run.lease.fencing_token if node_run.lease else None,
                usage=usage.to_dict(),
                failure_class="goal_completion_failed",
                message="Goal completion gate did not cover every required Claim.",
            )

    def _ready_node_runs(self, plan: PlanIR, plan_execution_id: str) -> tuple[NodeRunRecord, ...]:
        latest = _latest_attempt_by_node(self.service.store.list_node_runs(plan_execution_id))
        ready: list[NodeRunRecord] = []
        for node in sorted(plan.nodes, key=lambda item: item.canonical_order):
            run = latest[node.node_id]
            if run.status != NodeRunStatus.PENDING:
                continue
            if all(latest[dependency].status == NodeRunStatus.SUCCEEDED for dependency in node.depends_on):
                ready.append(run)
        return tuple(ready)

    def _finalize_or_fail(self, plan: PlanIR, execution: PlanExecutionRecord) -> PlanExecutionRecord:
        nodes = self.service.store.list_node_runs(execution.plan_execution_id)
        latest = _latest_attempt_by_node(nodes)
        terminal_goal_nodes = [
            node
            for node in plan.nodes
            if node.terminal_goal_verification or node.node_type == PlanNodeType.GOAL_VERIFICATION.value
        ]
        failed = [node for node in latest.values() if node.status in {NodeRunStatus.FAILED, NodeRunStatus.TIMED_OUT}]
        canceled = [node for node in latest.values() if node.status == NodeRunStatus.CANCELED]
        pending = [node for node in latest.values() if not node.status.terminal]
        if canceled:
            return self.service.transition_execution(
                execution.plan_execution_id,
                PlanExecutionStatus.CANCELED,
                expected_version=execution.status_version,
                message="Cancellation propagated to NodeRuns.",
                handoff_refs=(f"HANDOFF-{execution.plan_execution_id}-canceled",),
            )
        if failed:
            return self.service.transition_execution(
                execution.plan_execution_id,
                PlanExecutionStatus.FAILED,
                expected_version=execution.status_version,
                failure_class=failed[0].failure_class or "node_failed",
                message=failed[0].message or "A NodeRun failed.",
            )
        if pending:
            return self.service.transition_execution(
                execution.plan_execution_id,
                PlanExecutionStatus.FAILED,
                expected_version=execution.status_version,
                failure_class="dag_stalled",
                message="No ready nodes remain, but some NodeRuns are non-terminal.",
            )
        terminal_succeeded = all(latest[node.node_id].status == NodeRunStatus.SUCCEEDED for node in terminal_goal_nodes)
        if terminal_succeeded:
            verifying = self.service.transition_execution(
                execution.plan_execution_id,
                PlanExecutionStatus.VERIFYING,
                expected_version=execution.status_version,
                artifact_refs=tuple(ref for node in latest.values() for ref in node.artifact_refs),
                evidence_refs=tuple(ref for node in latest.values() for ref in node.evidence_refs),
                message="All NodeRuns succeeded; final PlanExecution gate is evaluating.",
            )
            return self.service.transition_execution(
                verifying.plan_execution_id,
                PlanExecutionStatus.SUCCEEDED,
                expected_version=verifying.status_version,
                artifact_refs=tuple(ref for node in latest.values() for ref in node.artifact_refs),
                evidence_refs=tuple(ref for node in latest.values() for ref in node.evidence_refs),
                handoff_refs=(f"HANDOFF-{execution.plan_execution_id}-review",),
                message="Static PlanIR DAG completed and goal verification passed.",
            )
        return self.service.transition_execution(
            execution.plan_execution_id,
            PlanExecutionStatus.FAILED,
            expected_version=execution.status_version,
            failure_class="missing_goal_verification",
            message="No terminal Goal verification NodeRun succeeded.",
        )

    def _fail_node(self, node_run: NodeRunRecord, failure_class: str, message: str) -> NodeRunRecord:
        latest = self.service.store.get_node_run(node_run.node_run_id)
        failed = self.service.transition_node(
            latest.node_run_id,
            NodeRunStatus.FAILED,
            expected_version=latest.status_version,
            holder=self.lease_holder,
            fencing_token=node_run.lease.fencing_token if node_run.lease else None,
            failure_class=failure_class,
            message=message,
        )
        return failed

    def _maybe_retry(self, plan: PlanIR, failed: NodeRunRecord, failure_class: str) -> None:
        node = _node_by_id(plan, failed.node_id)
        if failed.attempt >= node.retry_policy.max_attempts:
            return
        if failure_class not in node.retry_policy.retryable_failure_classes:
            return
        self.service.create_retry_node(failed)


def project_awkp_task(execution: PlanExecutionRecord, *, task_id: str) -> AwkpTaskProjection:
    recommendation = {
        PlanExecutionStatus.ADMITTED: "working",
        PlanExecutionStatus.RUNNING: "working",
        PlanExecutionStatus.VERIFYING: "review",
        PlanExecutionStatus.SUCCEEDED: "review",
        PlanExecutionStatus.FAILED: "changes_requested",
        PlanExecutionStatus.CANCELING: "working",
        PlanExecutionStatus.CANCELED: "canceled",
    }[execution.status]
    return AwkpTaskProjection(
        task_id=task_id,
        goal_ref=execution.goal_ref,
        plan_execution_id=execution.plan_execution_id,
        plan_status=execution.status,
        task_state_recommendation=recommendation,
        artifact_refs=execution.artifact_refs,
        evidence_refs=execution.evidence_refs,
        authority_refs={
            "task": task_id,
            "goal": execution.goal_ref,
            "planExecution": execution.plan_execution_id,
            "nodeRuns": ",".join(execution.node_run_refs),
        },
    )


def reconcile_plan_execution(
    execution: PlanExecutionRecord,
    node_runs: tuple[NodeRunRecord, ...],
    *,
    task_projection: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> tuple[ReconcilerFinding, ...]:
    now = now or utc_now()
    findings: list[ReconcilerFinding] = []
    if execution.status == PlanExecutionStatus.RUNNING and not node_runs:
        findings.append(
            ReconcilerFinding(
                code="orphan-plan-execution",
                severity="error",
                message="PlanExecution is running but has no NodeRun records.",
                refs=(execution.plan_execution_id,),
            )
        )
    for node in node_runs:
        if node.lease and not node.lease.active_at(now) and not node.status.terminal:
            findings.append(
                ReconcilerFinding(
                    code="expired-node-lease",
                    severity="warning",
                    message=f"NodeRun lease expired for {node.node_run_id}.",
                    refs=(execution.plan_execution_id, node.node_run_id),
                )
            )
        if node.status == NodeRunStatus.SUCCEEDED and node.gate_refs and not node.evidence_refs:
            findings.append(
                ReconcilerFinding(
                    code="missing-node-evidence",
                    severity="error",
                    message=f"NodeRun {node.node_run_id} succeeded without evidence refs.",
                    refs=(execution.plan_execution_id, node.node_run_id),
                )
            )
    terminal_goal_succeeded = any(
        node.node_type == PlanNodeType.GOAL_VERIFICATION.value and node.status == NodeRunStatus.SUCCEEDED
        for node in node_runs
    )
    if execution.status == PlanExecutionStatus.SUCCEEDED and not terminal_goal_succeeded:
        findings.append(
            ReconcilerFinding(
                code="missing-terminal-goal-node",
                severity="error",
                message="PlanExecution succeeded without a succeeded terminal Goal verification NodeRun.",
                refs=(execution.plan_execution_id,),
            )
        )
    if task_projection:
        task_state = str(task_projection.get("state", ""))
        if task_state == "completed" and execution.status != PlanExecutionStatus.SUCCEEDED:
            findings.append(
                ReconcilerFinding(
                    code="inconsistent-task-projection",
                    severity="error",
                    message="AWKP task projection is completed before PlanExecution succeeded.",
                    refs=(execution.plan_execution_id, str(task_projection.get("task_id", ""))),
                )
            )
    return tuple(findings)


def _assert_admitted_plan(plan: PlanIR, validation_report: PlanValidationReport) -> None:
    plan_digest = plan.digest()
    if not validation_report.valid:
        raise PlanAdmissionError("only a PlanIR with a passing validation report can start execution")
    if validation_report.subject_digest != plan_digest:
        raise PlanAdmissionError("validation report digest does not match immutable PlanIR digest")
    if not plan_digest.startswith("sha256:"):
        raise PlanAdmissionError("PlanIR digest is not content-addressed")


def _ensure_active_state(status: PlanExecutionStatus) -> None:
    if status.terminal:
        raise PlanLeaseConflictError(f"cannot lease terminal execution state {status.value}")


def _check_lease(
    lease: Lease | None,
    holder: str | None,
    fencing_token: int | None,
    now: datetime,
) -> None:
    if not lease:
        return
    if lease.holder != holder or lease.fencing_token != fencing_token:
        raise PlanLeaseConflictError("stale worker or fencing token")
    if not lease.active_at(now):
        raise PlanLeaseConflictError("lease expired")


def _runtime_grants_for_node(plan: PlanIR, node: PlanNodeIR) -> tuple[RuntimeCapabilityGrant, ...]:
    issued = datetime.now(UTC)
    expires = issued + timedelta(hours=2)
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
                issuer="harness:static-plan-scheduler",
                policy_decision_id=f"PDEC-{suffix}",
            )
        )
    return tuple(grants)


def _plan_budget_summary(plan: PlanIR) -> dict[str, Any]:
    max_wall_seconds = [
        node.budget.max_wall_seconds for node in plan.nodes if node.budget.max_wall_seconds is not None
    ]
    max_cost_usd = [node.budget.max_cost_usd for node in plan.nodes if node.budget.max_cost_usd is not None]
    summary: dict[str, Any] = {
        "nodeCount": len(plan.nodes),
        "maxModelCalls": sum(node.budget.max_model_calls for node in plan.nodes),
        "maxToolCalls": sum(node.budget.max_tool_calls for node in plan.nodes),
        "maxSpawnedNodes": sum(node.budget.max_spawned_nodes for node in plan.nodes),
    }
    if max_wall_seconds:
        summary["maxWallSeconds"] = sum(max_wall_seconds)
    if max_cost_usd:
        summary["maxCostUsd"] = round(sum(max_cost_usd), 6)
    return summary


def _node_wall_timeout_seconds(node: PlanNodeIR) -> int | None:
    candidates = [
        value for value in (node.timeout_seconds, node.budget.max_wall_seconds) if value is not None
    ]
    if not candidates:
        return None
    return min(candidates)


def _verification_usage() -> NodeExecutionUsage:
    return NodeExecutionUsage(model_calls=1, tool_calls=0, spawned_nodes=0, cost_usd=0.0)


def _budget_violation(node: PlanNodeIR, usage: NodeExecutionUsage | None) -> tuple[str, str] | None:
    if usage is None:
        return (
            "missing_usage_report",
            "NodeExecutionResult must report runtime usage before budget enforcement can pass.",
        )

    violations: list[str] = []
    if usage.model_calls > node.budget.max_model_calls:
        violations.append(f"modelCalls {usage.model_calls} > maxModelCalls {node.budget.max_model_calls}")
    if usage.tool_calls > node.budget.max_tool_calls:
        violations.append(f"toolCalls {usage.tool_calls} > maxToolCalls {node.budget.max_tool_calls}")
    if usage.spawned_nodes > node.budget.max_spawned_nodes:
        violations.append(f"spawnedNodes {usage.spawned_nodes} > maxSpawnedNodes {node.budget.max_spawned_nodes}")
    if node.budget.max_cost_usd is not None:
        if usage.cost_usd is None:
            violations.append("costUsd is required when maxCostUsd is declared")
        elif usage.cost_usd > node.budget.max_cost_usd:
            violations.append(f"costUsd {usage.cost_usd} > maxCostUsd {node.budget.max_cost_usd}")

    if violations:
        return ("budget_exceeded", "; ".join(violations))
    return None


def _failure_status(status: NodeExecutionStatus) -> NodeRunStatus:
    if status == NodeExecutionStatus.NEEDS_HUMAN:
        return NodeRunStatus.PAUSED_AUTH
    return NodeRunStatus.FAILED


def _node_by_id(plan: PlanIR, node_id: str) -> PlanNodeIR:
    for node in plan.nodes:
        if node.node_id == node_id:
            return node
    raise KeyError(node_id)


def _latest_attempt_by_node(node_runs: tuple[NodeRunRecord, ...]) -> dict[str, NodeRunRecord]:
    latest: dict[str, NodeRunRecord] = {}
    for node in sorted(node_runs, key=lambda item: (item.node_id, item.attempt)):
        latest[node.node_id] = node
    return latest


def _plan_execution_id(plan: PlanIR) -> str:
    return "PEXEC-" + canonical_fingerprint(
        {
            "planDigest": plan.digest(),
            "planId": plan.plan_id,
            "version": plan.version,
        }
    ).removeprefix("sha256:")[:16]


def _node_run_id(plan_execution_id: str, node_id: str, attempt: int) -> str:
    suffix = canonical_fingerprint(
        {
            "planExecution": plan_execution_id,
            "node": node_id,
            "attempt": attempt,
        }
    ).removeprefix("sha256:")[:16]
    return f"NRUN-{suffix}"


def _merge_refs(existing: tuple[str, ...], new_refs: tuple[str, ...]) -> tuple[str, ...]:
    result = list(existing)
    for ref in new_refs:
        if ref not in result:
            result.append(ref)
    return tuple(result)


def _lease_to_dict(lease: Lease | None) -> dict[str, Any] | None:
    if lease is None:
        return None
    return {
        "holder": lease.holder,
        "fencing_token": lease.fencing_token,
        "heartbeat_at": _iso(lease.heartbeat_at),
        "expires_at": _iso(lease.expires_at),
    }


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
