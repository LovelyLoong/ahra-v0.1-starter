from __future__ import annotations

import json
import os
import re
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator


class AwkpTaskStateWriterError(ValueError):
    """Raised when an AWKP task state transition is not governed."""


class AwkpTaskStateCasError(AwkpTaskStateWriterError):
    """Raised when expected_version does not match state_version."""


class AwkpTaskStateFenceError(AwkpTaskStateWriterError):
    """Raised when a lease holder or fencing token does not match."""


class AwkpTaskStateIdempotencyError(AwkpTaskStateWriterError):
    """Raised when an event idempotency key has already been used."""


class AwkpTaskStateLockError(AwkpTaskStateWriterError):
    """Raised when a task state writer lock cannot be acquired."""


@dataclass(frozen=True, slots=True)
class AwkpTaskStateTransitionResult:
    task_id: str
    from_state: str | None
    to_state: str
    state_version: int
    event_id: str
    idempotency_key: str
    fencing_token: str | None
    occurred_at: str


class AwkpTaskStateWriter:
    """CAS-protected writer for producer-side AWKP task transitions."""

    def __init__(
        self,
        *,
        work_root: str | Path = "work",
        clock: Callable[[], datetime | str] | None = None,
        token_factory: Callable[[], str] | None = None,
        lock_timeout_seconds: float = 5.0,
    ) -> None:
        self.work_root = Path(work_root)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._token_factory = token_factory or (lambda: f"FENCE-{uuid.uuid4().hex}")
        self._lock_timeout_seconds = lock_timeout_seconds

    def acquire_working(
        self,
        task_ref: str | Path,
        *,
        expected_version: int,
        actor: str,
        idempotency_key: str,
        reason: str,
        lease_ttl_seconds: int | None = None,
        refs: Iterable[str] = ("task.md", "state.json"),
    ) -> AwkpTaskStateTransitionResult:
        return self._acquire(
            task_ref,
            expected_version=expected_version,
            actor=actor,
            idempotency_key=idempotency_key,
            reason=reason,
            from_state="ready",
            event_type="lease_acquired",
            previous_fencing_token=None,
            lease_ttl_seconds=lease_ttl_seconds,
            refs=refs,
        )

    def reclaim_working(
        self,
        task_ref: str | Path,
        *,
        expected_version: int,
        actor: str,
        idempotency_key: str,
        previous_fencing_token: str,
        reason: str,
        lease_ttl_seconds: int | None = None,
        refs: Iterable[str] = ("task.md", "state.json"),
    ) -> AwkpTaskStateTransitionResult:
        return self._acquire(
            task_ref,
            expected_version=expected_version,
            actor=actor,
            idempotency_key=idempotency_key,
            reason=reason,
            from_state="changes_requested",
            event_type="lease_reclaimed",
            previous_fencing_token=previous_fencing_token,
            lease_ttl_seconds=lease_ttl_seconds,
            refs=refs,
        )

    def request_review(
        self,
        task_ref: str | Path,
        *,
        expected_version: int,
        actor: str,
        idempotency_key: str,
        fencing_token: str,
        reason: str,
        refs: Iterable[str] = ("state.json",),
        artifact_refs: Iterable[str] = (),
        evidence_refs: Iterable[str] = (),
        next_action: str = "Await independent EvidenceGate review.",
        clear_blockers: bool = False,
    ) -> AwkpTaskStateTransitionResult:
        task_dir = self._task_dir(task_ref)
        with self._locked(task_dir):
            state_path = task_dir / "state.json"
            event_path = task_dir / "events.jsonl"
            state = _load_json(state_path)
            events = _load_events(event_path)
            task_id = _task_id_from_state(task_dir, state)
            _require_non_empty("actor", actor)
            _require_non_empty("idempotency_key", idempotency_key)
            _require_non_empty("fencing_token", fencing_token)
            _assert_expected_version(task_id, state, expected_version)
            _assert_state(task_id, state, "working")
            _assert_unique_idempotency(event_path, events, idempotency_key)
            lease = state.get("lease")
            if not isinstance(lease, dict):
                raise AwkpTaskStateFenceError(f"{task_id} working state has no lease")
            lease_token = str(lease.get("fencing_token") or "")
            if lease_token != fencing_token:
                raise AwkpTaskStateFenceError(f"{task_id} fencing token mismatch")
            holder = str(lease.get("holder") or "")
            if holder != actor:
                raise AwkpTaskStateFenceError(f"{task_id} lease holder mismatch: {holder!r}")

            now = _monotonic_now(self._clock, events)
            new_version = int(state["state_version"]) + 1
            event_id = _next_event_id(task_id, events)
            event = _transition_event(
                state,
                task_id=task_id,
                event_id=event_id,
                idempotency_key=idempotency_key,
                event_type="review_requested",
                actor=actor,
                occurred_at=now,
                causation_id=_last_event_id(events),
                from_state="working",
                to_state="review",
                reason=reason,
                refs=refs,
                expected_version=expected_version,
                new_state_version=new_version,
                lease_fencing_token=fencing_token,
            )
            if clear_blockers:
                event["resolved_blockers"] = [str(item) for item in state.get("blockers", [])]
            _append_event(event_path, event)
            updated = dict(state)
            updated.update(
                {
                    "state": "review",
                    "state_version": new_version,
                    "owner": None,
                    "lease": None,
                    "next_action": next_action,
                    "pause_reason": None,
                    "blockers": [] if clear_blockers else state.get("blockers", []),
                    "artifact_refs": _append_unique_many(state.get("artifact_refs", []), artifact_refs),
                    "evidence_refs": _append_unique_many(state.get("evidence_refs", []), evidence_refs),
                    "updated_at": now,
                }
            )
            _write_json(state_path, updated)
            return AwkpTaskStateTransitionResult(
                task_id=task_id,
                from_state="working",
                to_state="review",
                state_version=new_version,
                event_id=event_id,
                idempotency_key=idempotency_key,
                fencing_token=fencing_token,
                occurred_at=now,
            )

    def record_goal_association(
        self,
        task_ref: str | Path,
        *,
        expected_version: int,
        actor: str,
        idempotency_key: str,
        fencing_token: str,
        goal_execution_id: str,
        goal_status: str,
        reason: str,
        refs: Iterable[str] = ("state.json",),
        next_action: str = "GoalExecution association recorded; prepare task review.",
        artifact_refs: Iterable[str] = (),
        evidence_refs: Iterable[str] = (),
    ) -> AwkpTaskStateTransitionResult:
        task_dir = self._task_dir(task_ref)
        with self._locked(task_dir):
            state_path = task_dir / "state.json"
            event_path = task_dir / "events.jsonl"
            state = _load_json(state_path)
            events = _load_events(event_path)
            task_id = _task_id_from_state(task_dir, state)
            _require_non_empty("actor", actor)
            _require_non_empty("idempotency_key", idempotency_key)
            _require_non_empty("fencing_token", fencing_token)
            _require_non_empty("goal_execution_id", goal_execution_id)
            _require_non_empty("goal_status", goal_status)
            _assert_expected_version(task_id, state, expected_version)
            _assert_state(task_id, state, "working")
            _assert_unique_idempotency(event_path, events, idempotency_key)
            lease = state.get("lease")
            if not isinstance(lease, dict):
                raise AwkpTaskStateFenceError(f"{task_id} working state has no lease")
            lease_token = str(lease.get("fencing_token") or "")
            if lease_token != fencing_token:
                raise AwkpTaskStateFenceError(f"{task_id} fencing token mismatch")
            holder = str(lease.get("holder") or "")
            if holder != actor:
                raise AwkpTaskStateFenceError(f"{task_id} lease holder mismatch: {holder!r}")

            now = _monotonic_now(self._clock, events)
            new_version = int(state["state_version"]) + 1
            event_id = _next_event_id(task_id, events)
            event = _transition_event(
                state,
                task_id=task_id,
                event_id=event_id,
                idempotency_key=idempotency_key,
                event_type="goal_awkp_associated",
                actor=actor,
                occurred_at=now,
                causation_id=_last_event_id(events),
                from_state="working",
                to_state="working",
                reason=reason,
                refs=refs,
                expected_version=expected_version,
                new_state_version=new_version,
                lease_fencing_token=fencing_token,
            )
            event["goal_execution_id"] = goal_execution_id
            event["goal_status"] = goal_status
            _append_event(event_path, event)
            updated = dict(state)
            updated.update(
                {
                    "state_version": new_version,
                    "next_action": next_action,
                    "artifact_refs": _append_unique_many(state.get("artifact_refs", []), artifact_refs),
                    "evidence_refs": _append_unique_many(state.get("evidence_refs", []), evidence_refs),
                    "updated_at": now,
                }
            )
            _write_json(state_path, updated)
            return AwkpTaskStateTransitionResult(
                task_id=task_id,
                from_state="working",
                to_state="working",
                state_version=new_version,
                event_id=event_id,
                idempotency_key=idempotency_key,
                fencing_token=fencing_token,
                occurred_at=now,
            )

    def add_blocker(
        self,
        task_ref: str | Path,
        *,
        expected_version: int,
        actor: str,
        idempotency_key: str,
        blocker: str,
        reason: str,
        refs: Iterable[str] = ("state.json",),
        next_action: str | None = None,
    ) -> AwkpTaskStateTransitionResult:
        task_dir = self._task_dir(task_ref)
        with self._locked(task_dir):
            state_path = task_dir / "state.json"
            event_path = task_dir / "events.jsonl"
            state = _load_json(state_path)
            events = _load_events(event_path)
            task_id = _task_id_from_state(task_dir, state)
            _require_non_empty("actor", actor)
            _require_non_empty("idempotency_key", idempotency_key)
            _require_non_empty("blocker", blocker)
            _assert_expected_version(task_id, state, expected_version)
            _assert_unique_idempotency(event_path, events, idempotency_key)
            current_state = str(state.get("state") or "")
            if current_state in {"completed", "failed", "canceled", "rejected"}:
                raise AwkpTaskStateWriterError(f"{task_id} cannot add blocker in terminal state {current_state!r}")

            now = _monotonic_now(self._clock, events)
            new_version = int(state["state_version"]) + 1
            event_id = _next_event_id(task_id, events)
            event = {
                "schema_version": "awkp/0.1",
                "event_id": event_id,
                "idempotency_key": idempotency_key,
                "task_id": task_id,
                "context_id": state.get("context_id"),
                "event_type": "blocker_added",
                "actor": actor,
                "occurred_at": now,
                "causation_id": _last_event_id(events),
                "correlation_id": state.get("context_id"),
                "from_state": current_state,
                "to_state": current_state,
                "reason": reason,
                "refs": _unique_refs(refs),
                "expected_version": expected_version,
                "new_state_version": new_version,
                "blocker": blocker,
            }
            _append_event(event_path, event)
            blockers = _append_unique_many(state.get("blockers", []), [blocker])
            updated = dict(state)
            updated.update(
                {
                    "state_version": new_version,
                    "next_action": next_action or reason,
                    "blockers": blockers,
                    "updated_at": now,
                }
            )
            _write_json(state_path, updated)
            return AwkpTaskStateTransitionResult(
                task_id=task_id,
                from_state=current_state,
                to_state=current_state,
                state_version=new_version,
                event_id=event_id,
                idempotency_key=idempotency_key,
                fencing_token=None,
                occurred_at=now,
            )

    def clear_blockers(
        self,
        task_ref: str | Path,
        *,
        expected_version: int,
        actor: str,
        idempotency_key: str,
        reason: str,
        refs: Iterable[str] = ("state.json",),
        next_action: str | None = None,
    ) -> AwkpTaskStateTransitionResult:
        task_dir = self._task_dir(task_ref)
        with self._locked(task_dir):
            state_path = task_dir / "state.json"
            event_path = task_dir / "events.jsonl"
            state = _load_json(state_path)
            events = _load_events(event_path)
            task_id = _task_id_from_state(task_dir, state)
            _require_non_empty("actor", actor)
            _require_non_empty("idempotency_key", idempotency_key)
            _require_non_empty("reason", reason)
            _assert_expected_version(task_id, state, expected_version)
            _assert_unique_idempotency(event_path, events, idempotency_key)
            current_state = str(state.get("state") or "")
            if current_state in {"completed", "failed", "canceled", "rejected"}:
                raise AwkpTaskStateWriterError(f"{task_id} cannot clear blockers in terminal state {current_state!r}")

            resolved_blockers = [str(item) for item in state.get("blockers", []) if str(item)]
            if not resolved_blockers:
                raise AwkpTaskStateWriterError(f"{task_id} has no blockers to clear")

            now = _monotonic_now(self._clock, events)
            new_version = int(state["state_version"]) + 1
            event_id = _next_event_id(task_id, events)
            event = {
                "schema_version": "awkp/0.1",
                "event_id": event_id,
                "idempotency_key": idempotency_key,
                "task_id": task_id,
                "context_id": state.get("context_id"),
                "event_type": "blockers_cleared",
                "actor": actor,
                "occurred_at": now,
                "causation_id": _last_event_id(events),
                "correlation_id": state.get("context_id"),
                "from_state": current_state,
                "to_state": current_state,
                "reason": reason,
                "refs": _unique_refs(refs),
                "expected_version": expected_version,
                "new_state_version": new_version,
                "resolved_blockers": resolved_blockers,
            }
            _append_event(event_path, event)
            updated = dict(state)
            updated.update(
                {
                    "state_version": new_version,
                    "next_action": next_action or reason,
                    "blockers": [],
                    "updated_at": now,
                }
            )
            _write_json(state_path, updated)
            return AwkpTaskStateTransitionResult(
                task_id=task_id,
                from_state=current_state,
                to_state=current_state,
                state_version=new_version,
                event_id=event_id,
                idempotency_key=idempotency_key,
                fencing_token=None,
                occurred_at=now,
            )

    def _acquire(
        self,
        task_ref: str | Path,
        *,
        expected_version: int,
        actor: str,
        idempotency_key: str,
        reason: str,
        from_state: str,
        event_type: str,
        previous_fencing_token: str | None,
        lease_ttl_seconds: int | None,
        refs: Iterable[str],
    ) -> AwkpTaskStateTransitionResult:
        task_dir = self._task_dir(task_ref)
        with self._locked(task_dir):
            state_path = task_dir / "state.json"
            event_path = task_dir / "events.jsonl"
            state = _load_json(state_path)
            events = _load_events(event_path)
            task_id = _task_id_from_state(task_dir, state)
            _require_non_empty("actor", actor)
            _require_non_empty("idempotency_key", idempotency_key)
            _assert_expected_version(task_id, state, expected_version)
            _assert_state(task_id, state, from_state)
            _assert_unique_idempotency(event_path, events, idempotency_key)
            if state.get("lease"):
                raise AwkpTaskStateFenceError(f"{task_id} cannot acquire while a lease is present")
            if from_state == "changes_requested":
                _require_non_empty("previous_fencing_token", previous_fencing_token)
                latest_token = _latest_event_fencing_token(events)
                if latest_token is None:
                    raise AwkpTaskStateFenceError(f"{task_id} has no prior fencing token to reclaim")
                if latest_token != previous_fencing_token:
                    raise AwkpTaskStateFenceError(f"{task_id} stale previous fencing token")

            now = _monotonic_now(self._clock, events)
            fencing_token = self._new_fencing_token(task_id, events)
            expires_at = _expires_at(now, lease_ttl_seconds)
            holder = actor
            lease = {
                "holder": holder,
                "fencing_token": fencing_token,
                "acquired_at": now,
                "heartbeat_at": now,
                "expires_at": expires_at,
            }
            new_version = int(state["state_version"]) + 1
            event_id = _next_event_id(task_id, events)
            event = _transition_event(
                state,
                task_id=task_id,
                event_id=event_id,
                idempotency_key=idempotency_key,
                event_type=event_type,
                actor=actor,
                occurred_at=now,
                causation_id=_last_event_id(events),
                from_state=from_state,
                to_state="working",
                reason=reason,
                refs=refs,
                expected_version=expected_version,
                new_state_version=new_version,
                lease_fencing_token=fencing_token,
                previous_lease_fencing_token=previous_fencing_token,
            )
            _append_event(event_path, event)
            updated = dict(state)
            updated.update(
                {
                    "state": "working",
                    "state_version": new_version,
                    "owner": holder,
                    "attempt": int(state.get("attempt") or 0) + 1,
                    "lease": lease,
                    "next_action": f"{actor} holds the task lease and is producing review evidence.",
                    "pause_reason": None,
                    "updated_at": now,
                }
            )
            _write_json(state_path, updated)
            return AwkpTaskStateTransitionResult(
                task_id=task_id,
                from_state=from_state,
                to_state="working",
                state_version=new_version,
                event_id=event_id,
                idempotency_key=idempotency_key,
                fencing_token=fencing_token,
                occurred_at=now,
            )

    def _task_dir(self, task_ref: str | Path) -> Path:
        path = Path(task_ref)
        if (path / "state.json").exists():
            return path
        return self.work_root / "tasks" / str(task_ref)

    def _new_fencing_token(self, task_id: str, events: list[dict[str, Any]]) -> str:
        token = str(self._token_factory())
        if not token:
            raise AwkpTaskStateFenceError("fencing token factory returned an empty token")
        used = {
            str(event.get("lease_fencing_token"))
            for event in events
            if event.get("lease_fencing_token") is not None
        }
        if token in used:
            raise AwkpTaskStateFenceError(f"{task_id} fencing token was already used")
        return token

    @contextmanager
    def _locked(self, task_dir: Path) -> Iterator[None]:
        if not task_dir.exists():
            raise AwkpTaskStateWriterError(f"AWKP task directory not found: {task_dir}")
        if not task_dir.is_dir():
            raise AwkpTaskStateWriterError(f"AWKP task path is not a directory: {task_dir}")
        lock_path = task_dir / ".state-writer.lock"
        deadline = time.monotonic() + self._lock_timeout_seconds
        handle: int | None = None
        while True:
            try:
                handle = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(handle, f"{os.getpid()} {datetime.now(UTC).isoformat()}\n".encode("utf-8"))
                break
            except FileExistsError as exc:
                if time.monotonic() >= deadline:
                    raise AwkpTaskStateLockError(f"could not acquire task state writer lock: {lock_path}") from exc
                time.sleep(0.05)
        try:
            yield
        finally:
            if handle is not None:
                os.close(handle)
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise AwkpTaskStateWriterError(f"required AWKP JSON file is missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AwkpTaskStateWriterError(f"AWKP JSON document must be an object: {path}")
    return data


def _write_json(path: Path, data: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _load_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _append_event(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")


def _task_id_from_state(task_dir: Path, state: dict[str, Any]) -> str:
    task_id = str(state.get("task_id") or "")
    if not task_id:
        raise AwkpTaskStateWriterError(f"state task_id is missing: {task_dir / 'state.json'}")
    if task_id != task_dir.name:
        raise AwkpTaskStateWriterError(f"state task_id does not match task directory: {task_dir}")
    return task_id


def _assert_expected_version(task_id: str, state: dict[str, Any], expected_version: int) -> None:
    current = int(state.get("state_version", -1))
    if current != expected_version:
        raise AwkpTaskStateCasError(f"{task_id} expected state_version {expected_version}, current {current}")


def _assert_state(task_id: str, state: dict[str, Any], expected_state: str) -> None:
    current = str(state.get("state") or "")
    if current != expected_state:
        raise AwkpTaskStateWriterError(f"{task_id} expected state {expected_state!r}, current {current!r}")


def _assert_unique_idempotency(path: Path, events: list[dict[str, Any]], idempotency_key: str) -> None:
    for event in events:
        if event.get("idempotency_key") == idempotency_key:
            raise AwkpTaskStateIdempotencyError(f"duplicate idempotency_key {idempotency_key!r} in {path}")


def _require_non_empty(name: str, value: object) -> None:
    if not isinstance(value, str) or not value:
        raise AwkpTaskStateWriterError(f"{name} is required")


def _next_event_id(task_id: str, events: list[dict[str, Any]]) -> str:
    pattern = re.compile(rf"^EVT-{re.escape(task_id)}-(\d{{4}})$")
    highest = 0
    for event in events:
        match = pattern.match(str(event.get("event_id") or ""))
        if match:
            highest = max(highest, int(match.group(1)))
    return f"EVT-{task_id}-{highest + 1:04d}"


def _last_event_id(events: list[dict[str, Any]]) -> str | None:
    if not events:
        return None
    event_id = events[-1].get("event_id")
    return str(event_id) if event_id else None


def _latest_event_fencing_token(events: list[dict[str, Any]]) -> str | None:
    for event in reversed(events):
        token = event.get("lease_fencing_token")
        if token:
            return str(token)
    return None


def _transition_event(
    state: dict[str, Any],
    *,
    task_id: str,
    event_id: str,
    idempotency_key: str,
    event_type: str,
    actor: str,
    occurred_at: str,
    causation_id: str | None,
    from_state: str,
    to_state: str,
    reason: str,
    refs: Iterable[str],
    expected_version: int,
    new_state_version: int,
    lease_fencing_token: str,
    previous_lease_fencing_token: str | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "schema_version": "awkp/0.1",
        "event_id": event_id,
        "idempotency_key": idempotency_key,
        "task_id": task_id,
        "context_id": state.get("context_id"),
        "event_type": event_type,
        "actor": actor,
        "occurred_at": occurred_at,
        "causation_id": causation_id,
        "correlation_id": state.get("context_id"),
        "from_state": from_state,
        "to_state": to_state,
        "reason": reason,
        "refs": _unique_refs(refs),
        "expected_version": expected_version,
        "new_state_version": new_state_version,
        "lease_fencing_token": lease_fencing_token,
    }
    if previous_lease_fencing_token is not None:
        event["previous_lease_fencing_token"] = previous_lease_fencing_token
    return event


def _unique_refs(refs: Iterable[str]) -> list[str]:
    result: list[str] = []
    for ref in refs:
        text = str(ref)
        if text not in result:
            result.append(text)
    return result


def _append_unique_many(existing: Any, additions: Iterable[str]) -> list[str]:
    result = [str(item) for item in existing] if isinstance(existing, list) else []
    for addition in additions:
        text = str(addition)
        if text not in result:
            result.append(text)
    return result


def _monotonic_now(clock: Callable[[], datetime | str], events: list[dict[str, Any]]) -> str:
    candidate = _coerce_datetime(clock())
    last = _last_occurred_at(events)
    if last is not None and candidate <= last:
        candidate = last + timedelta(microseconds=1)
    return _format_utc(candidate)


def _coerce_datetime(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise AwkpTaskStateWriterError("clock must return datetime or ISO string")
    if result.tzinfo is None:
        result = result.replace(tzinfo=UTC)
    return result.astimezone(UTC)


def _last_occurred_at(events: list[dict[str, Any]]) -> datetime | None:
    for event in reversed(events):
        value = event.get("occurred_at")
        if value:
            return _coerce_datetime(str(value))
    return None


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _expires_at(acquired_at: str, lease_ttl_seconds: int | None) -> str | None:
    if lease_ttl_seconds is None:
        return None
    if lease_ttl_seconds <= 0:
        raise AwkpTaskStateWriterError("lease_ttl_seconds must be positive")
    return _format_utc(_coerce_datetime(acquired_at) + timedelta(seconds=lease_ttl_seconds))
