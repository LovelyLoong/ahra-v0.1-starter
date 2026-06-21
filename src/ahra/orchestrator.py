from __future__ import annotations

import threading
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from .domain import Budget, Lease, RunRecord, RunStatus, utc_now


class NotFoundError(KeyError):
    pass


class VersionConflictError(RuntimeError):
    pass


class InvalidTransitionError(RuntimeError):
    pass


class LeaseConflictError(RuntimeError):
    pass


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
