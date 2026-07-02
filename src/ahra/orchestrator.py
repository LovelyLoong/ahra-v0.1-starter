from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from .awkp_state_writer import AwkpTaskStateTransitionResult, AwkpTaskStateWriter
from .domain import Budget, Lease, RunRecord, RunStatus, utc_now
from .evidence_gate import EvidenceGateResult, evaluate_task_gate


class NotFoundError(KeyError):
    pass


class VersionConflictError(RuntimeError):
    pass


class InvalidTransitionError(RuntimeError):
    pass


class LeaseConflictError(RuntimeError):
    pass


class AwkpTaskOrchestratorError(ValueError):
    """Raised when the task review orchestrator must fail closed."""


@dataclass(frozen=True, slots=True)
class AwkpTaskReviewCycle:
    cycle: int
    review_event_id: str
    review_state_version: int
    gate_event_id: str | None
    decision: str
    state: str
    state_version: int
    report_path: str | None
    reclaim_event_id: str | None = None
    blocker_event_id: str | None = None


@dataclass(frozen=True, slots=True)
class AwkpTaskOrchestrationRequest:
    task: str | Path
    expected_version: int
    producer_actor: str
    verifier_actor: str
    fencing_token: str
    report_paths: tuple[str | Path, ...]
    work_root: str | Path = "work"
    max_cycles: int = 1
    idempotency_key_prefix: str | None = None
    review_refs: tuple[str, ...] = ("state.json", "artifact-manifest.json", "evidence-manifest.json")
    artifact_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    lease_ttl_seconds: int | None = None
    reason: str = "Task evidence is ready for automated independent EvidenceGate review."


@dataclass(frozen=True, slots=True)
class AwkpTaskOrchestrationResult:
    task_id: str
    terminal_state: str
    state_version: int
    cycles: tuple[AwkpTaskReviewCycle, ...]
    blocked: bool = False
    blocker: str | None = None


class AwkpTaskReviewOrchestrator:
    """Chains producer review request, independent EvidenceGate, and bounded repair loops."""

    def __init__(
        self,
        *,
        work_root: str | Path = "work",
        state_writer: AwkpTaskStateWriter | None = None,
        gate_evaluator: Callable[..., EvidenceGateResult] = evaluate_task_gate,
    ) -> None:
        self.work_root = Path(work_root)
        self.state_writer = state_writer or AwkpTaskStateWriter(work_root=self.work_root)
        self._gate_evaluator = gate_evaluator

    def run(self, request: AwkpTaskOrchestrationRequest) -> AwkpTaskOrchestrationResult:
        if not request.producer_actor:
            raise AwkpTaskOrchestratorError("producer_actor is required")
        if not request.verifier_actor:
            raise AwkpTaskOrchestratorError("verifier_actor is required")
        if request.producer_actor == request.verifier_actor:
            raise AwkpTaskOrchestratorError("verifier_actor must differ from producer_actor")
        if not request.fencing_token:
            raise AwkpTaskOrchestratorError("fencing_token is required")
        if request.max_cycles < 1:
            raise AwkpTaskOrchestratorError("max_cycles must be positive")
        if not request.report_paths:
            raise AwkpTaskOrchestratorError("at least one verifier report path is required")

        work_root = Path(request.work_root)
        task_dir = _awkp_task_dir(request.task, work_root)
        task_id = _awkp_task_id(task_dir)
        prefix = request.idempotency_key_prefix or f"{task_id}:task-orchestrator"
        expected_version = request.expected_version
        fencing_token = request.fencing_token
        pending_reclaim: AwkpTaskStateTransitionResult | None = None
        cycles: list[AwkpTaskReviewCycle] = []

        for cycle in range(1, request.max_cycles + 1):
            if cycle > len(request.report_paths):
                state = _awkp_task_state(task_dir)
                blocker = f"Task review orchestrator stopped before cycle {cycle}: no verifier report path was supplied."
                blocker_result = self.state_writer.add_blocker(
                    request.task,
                    expected_version=int(state["state_version"]),
                    actor="ahra:task-orchestrator",
                    idempotency_key=f"{prefix}:cycle-{cycle}:missing-report-blocker",
                    blocker=blocker,
                    reason=blocker,
                    refs=("state.json",),
                    next_action="Publish corrected evidence and rerun the task review orchestrator.",
                )
                return AwkpTaskOrchestrationResult(
                    task_id=task_id,
                    terminal_state=str(state.get("state") or ""),
                    state_version=blocker_result.state_version,
                    cycles=tuple(cycles),
                    blocked=True,
                    blocker=blocker,
                )

            review_state = _awkp_task_state(task_dir)
            review = self.state_writer.request_review(
                request.task,
                expected_version=expected_version,
                actor=request.producer_actor,
                idempotency_key=f"{prefix}:cycle-{cycle}:review",
                fencing_token=fencing_token,
                reason=request.reason,
                refs=request.review_refs,
                artifact_refs=request.artifact_refs,
                evidence_refs=request.evidence_refs,
                clear_blockers=cycle > 1 or bool(review_state.get("blockers")),
                next_action="Automated orchestrator is invoking independent EvidenceGate review.",
            )
            gate = self._gate_evaluator(
                request.task,
                work_root=work_root,
                expected_version=review.state_version,
                report_path=request.report_paths[cycle - 1],
                actor=request.verifier_actor,
            )
            review_cycle = AwkpTaskReviewCycle(
                cycle=cycle,
                review_event_id=review.event_id,
                review_state_version=review.state_version,
                gate_event_id=gate.event_id,
                decision=gate.decision,
                state=gate.state,
                state_version=gate.state_version,
                report_path=gate.report_path,
                reclaim_event_id=pending_reclaim.event_id if pending_reclaim else None,
            )
            cycles.append(review_cycle)

            if gate.state == "completed":
                return AwkpTaskOrchestrationResult(
                    task_id=task_id,
                    terminal_state=gate.state,
                    state_version=gate.state_version,
                    cycles=tuple(cycles),
                )
            if gate.state != "changes_requested":
                return AwkpTaskOrchestrationResult(
                    task_id=task_id,
                    terminal_state=gate.state,
                    state_version=gate.state_version,
                    cycles=tuple(cycles),
                )
            if cycle >= request.max_cycles:
                blocker = f"Task review orchestrator reached max_cycles={request.max_cycles} with EvidenceGate changes_requested."
                blocker_result = self.state_writer.add_blocker(
                    request.task,
                    expected_version=gate.state_version,
                    actor="ahra:task-orchestrator",
                    idempotency_key=f"{prefix}:cycle-{cycle}:max-cycles-blocker",
                    blocker=blocker,
                    reason=blocker,
                    refs=("state.json", "artifact-manifest.json", "evidence-manifest.json"),
                    next_action="Address EvidenceGate findings and rerun the task review orchestrator.",
                )
                cycles[-1] = replace(cycles[-1], blocker_event_id=blocker_result.event_id)
                return AwkpTaskOrchestrationResult(
                    task_id=task_id,
                    terminal_state="changes_requested",
                    state_version=blocker_result.state_version,
                    cycles=tuple(cycles),
                    blocked=True,
                    blocker=blocker,
                )

            pending_reclaim = self.state_writer.reclaim_working(
                request.task,
                expected_version=gate.state_version,
                actor=request.producer_actor,
                idempotency_key=f"{prefix}:cycle-{cycle}:reclaim",
                previous_fencing_token=fencing_token,
                reason="Automated orchestrator reclaimed task after EvidenceGate request_changes.",
                lease_ttl_seconds=request.lease_ttl_seconds,
                refs=("state.json", "artifact-manifest.json", "evidence-manifest.json"),
            )
            expected_version = pending_reclaim.state_version
            fencing_token = str(pending_reclaim.fencing_token or "")

        raise AwkpTaskOrchestratorError("unreachable orchestrator loop exit")


ALLOWED_TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.CREATED: {RunStatus.ADMITTED, RunStatus.CANCELED, RunStatus.FAILED},
    RunStatus.ADMITTED: {RunStatus.QUEUED, RunStatus.CANCELED, RunStatus.FAILED},
    RunStatus.QUEUED: {RunStatus.PROVISIONING, RunStatus.CANCELED, RunStatus.TIMED_OUT},
    RunStatus.PROVISIONING: {RunStatus.RUNNING, RunStatus.BACKOFF, RunStatus.FAILED, RunStatus.CANCELED},
    RunStatus.RUNNING: {
        RunStatus.PAUSED_INPUT,
        RunStatus.PAUSED_AUTH,
        RunStatus.PAUSED_POLICY,
        RunStatus.BACKOFF,
        RunStatus.SUSPENDED,
        RunStatus.VERIFYING,
        RunStatus.FAILED,
        RunStatus.TIMED_OUT,
        RunStatus.CANCELED,
    },
    RunStatus.PAUSED_INPUT: {RunStatus.RUNNING, RunStatus.CANCELED, RunStatus.TIMED_OUT},
    RunStatus.PAUSED_AUTH: {RunStatus.RUNNING, RunStatus.CANCELED, RunStatus.TIMED_OUT},
    RunStatus.PAUSED_POLICY: {RunStatus.RUNNING, RunStatus.CANCELED, RunStatus.FAILED},
    RunStatus.BACKOFF: {RunStatus.QUEUED, RunStatus.FAILED, RunStatus.CANCELED, RunStatus.TIMED_OUT},
    RunStatus.SUSPENDED: {RunStatus.QUEUED, RunStatus.CANCELED, RunStatus.TIMED_OUT},
    RunStatus.VERIFYING: {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.RUNNING, RunStatus.CANCELED},
    RunStatus.SUCCEEDED: set(),
    RunStatus.FAILED: set(),
    RunStatus.TIMED_OUT: set(),
    RunStatus.CANCELED: set(),
}


class InMemoryRunStore:
    """Reference store. Production adapters must provide transactional CAS."""

    def __init__(self) -> None:
        self._runs: dict[str, RunRecord] = {}
        self._lock = threading.RLock()

    def create(self, run: RunRecord) -> None:
        with self._lock:
            if run.run_id in self._runs:
                raise VersionConflictError(f"run already exists: {run.run_id}")
            self._runs[run.run_id] = run

    def get(self, run_id: str) -> RunRecord:
        with self._lock:
            try:
                return self._runs[run_id]
            except KeyError as exc:
                raise NotFoundError(run_id) from exc

    def compare_and_swap(self, run: RunRecord, expected_version: int) -> RunRecord:
        with self._lock:
            current = self.get(run.run_id)
            if current.status_version != expected_version:
                raise VersionConflictError(
                    f"expected version {expected_version}, current {current.status_version}"
                )
            if run.status_version != expected_version + 1:
                raise VersionConflictError("new record must increment status_version exactly once")
            self._runs[run.run_id] = run
            return run


class RunService:
    def __init__(self, store: InMemoryRunStore) -> None:
        self.store = store

    def create_run(
        self,
        *,
        task_id: str,
        context_id: str,
        attempt: int,
        agent_release: str,
        budget: Budget,
    ) -> RunRecord:
        now = utc_now()
        run = RunRecord(
            run_id=f"RUN-{uuid.uuid4()}",
            task_id=task_id,
            context_id=context_id,
            attempt=attempt,
            agent_release=agent_release,
            status=RunStatus.CREATED,
            status_version=0,
            budgets=budget,
            trace_id=uuid.uuid4().hex,
            created_at=now,
            updated_at=now,
        )
        self.store.create(run)
        return run

    def transition(
        self,
        run_id: str,
        to_status: RunStatus,
        *,
        expected_version: int,
        failure: dict | None = None,
    ) -> RunRecord:
        current = self.store.get(run_id)
        if to_status not in ALLOWED_TRANSITIONS[current.status]:
            raise InvalidTransitionError(f"{current.status.value} -> {to_status.value} is not allowed")
        updated = replace(
            current,
            status=to_status,
            status_version=current.status_version + 1,
            updated_at=utc_now(),
            failure=failure,
            lease=None if to_status.terminal else current.lease,
        )
        return self.store.compare_and_swap(updated, expected_version)

    def acquire_lease(
        self,
        run_id: str,
        *,
        holder: str,
        ttl_seconds: int,
        expected_version: int,
        now: datetime | None = None,
    ) -> RunRecord:
        now = now or utc_now()
        current = self.store.get(run_id)
        if current.status not in {RunStatus.QUEUED, RunStatus.PROVISIONING, RunStatus.RUNNING}:
            raise LeaseConflictError(f"cannot lease run in state {current.status.value}")
        if current.lease and current.lease.active_at(now) and current.lease.holder != holder:
            raise LeaseConflictError("active lease is held by another worker")
        next_token = (current.lease.fencing_token + 1) if current.lease else 1
        lease = Lease(
            holder=holder,
            fencing_token=next_token,
            heartbeat_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
        updated = replace(
            current,
            lease=lease,
            status_version=current.status_version + 1,
            updated_at=now,
        )
        return self.store.compare_and_swap(updated, expected_version)

    def heartbeat(
        self,
        run_id: str,
        *,
        holder: str,
        fencing_token: int,
        ttl_seconds: int,
        expected_version: int,
        now: datetime | None = None,
    ) -> RunRecord:
        now = now or datetime.now(timezone.utc)
        current = self.store.get(run_id)
        if not current.lease:
            raise LeaseConflictError("run has no lease")
        if current.lease.holder != holder or current.lease.fencing_token != fencing_token:
            raise LeaseConflictError("stale worker or fencing token")
        lease = replace(
            current.lease,
            heartbeat_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
        updated = replace(
            current,
            lease=lease,
            status_version=current.status_version + 1,
            updated_at=now,
        )
        return self.store.compare_and_swap(updated, expected_version)


def _awkp_task_dir(task: str | Path, work_root: Path) -> Path:
    task_path = Path(task)
    if (task_path / "state.json").exists():
        return task_path
    return work_root / "tasks" / str(task)


def _awkp_task_id(task_dir: Path) -> str:
    state = _awkp_task_state(task_dir)
    task_id = str(state.get("task_id") or "")
    if not task_id:
        raise AwkpTaskOrchestratorError(f"state task_id is missing: {task_dir / 'state.json'}")
    if task_id != task_dir.name:
        raise AwkpTaskOrchestratorError(f"state task_id does not match task directory: {task_dir}")
    return task_id


def _awkp_task_state(task_dir: Path) -> dict[str, Any]:
    state_path = task_dir / "state.json"
    if not state_path.exists():
        raise AwkpTaskOrchestratorError(f"task state is missing: {state_path}")
    data = json.loads(state_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AwkpTaskOrchestratorError(f"task state must be a JSON object: {state_path}")
    return data
