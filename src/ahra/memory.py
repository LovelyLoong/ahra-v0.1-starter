from __future__ import annotations

import threading
import uuid
from dataclasses import replace
from datetime import datetime, timezone

from .domain import MemoryKind, MemoryRecord, MemoryScope, MemoryStatus, utc_now


class MemoryErrorBase(RuntimeError):
    pass


class MemoryNotFound(MemoryErrorBase):
    pass


class InvalidMemoryTransition(MemoryErrorBase):
    pass


class InMemoryMemoryStore:
    def __init__(self) -> None:
        self._items: dict[str, MemoryRecord] = {}
        self._lock = threading.RLock()

    def put(self, record: MemoryRecord) -> None:
        with self._lock:
            if record.memory_id in self._items:
                raise InvalidMemoryTransition("memory already exists")
            self._items[record.memory_id] = record

    def get(self, memory_id: str) -> MemoryRecord:
        with self._lock:
            try:
                return self._items[memory_id]
            except KeyError as exc:
                raise MemoryNotFound(memory_id) from exc

    def replace(self, record: MemoryRecord) -> None:
        with self._lock:
            if record.memory_id not in self._items:
                raise MemoryNotFound(record.memory_id)
            self._items[record.memory_id] = record

    def list_for_scope(self, tenant_id: str, project_id: str | None = None) -> list[MemoryRecord]:
        with self._lock:
            return [
                item
                for item in self._items.values()
                if item.scope.tenant_id == tenant_id
                and (project_id is None or item.scope.project_id == project_id)
            ]


class MemoryService:
    """Reference governance: model writes candidates; a separate actor promotes them."""

    def __init__(self, store: InMemoryMemoryStore) -> None:
        self.store = store

    def propose(
        self,
        *,
        kind: MemoryKind,
        scope: MemoryScope,
        statement: str,
        source_refs: tuple[str, ...],
        created_by: str,
        confidence: float,
        sensitivity: str,
        retention_policy: str,
        tags: tuple[str, ...] = (),
    ) -> MemoryRecord:
        if not source_refs:
            raise ValueError("source_refs are required")
        if not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        record = MemoryRecord(
            memory_id=f"MEM-{uuid.uuid4()}",
            kind=kind,
            scope=scope,
            statement=statement,
            status=MemoryStatus.CANDIDATE,
            confidence=confidence,
            source_refs=source_refs,
            created_by=created_by,
            created_at=utc_now(),
            sensitivity=sensitivity,
            retention_policy=retention_policy,
            tags=tags,
        )
        self.store.put(record)
        return record

    def promote(self, memory_id: str, *, verifier: str) -> MemoryRecord:
        current = self.store.get(memory_id)
        if current.status != MemoryStatus.CANDIDATE:
            raise InvalidMemoryTransition("only candidate memory can be promoted")
        # verifier is intentionally required even though the reference record does
        # not yet persist reviewer metadata; a production adapter should audit it.
        if not verifier:
            raise ValueError("verifier is required")
        active = replace(current, status=MemoryStatus.ACTIVE, valid_from=utc_now())
        self.store.replace(active)
        return active

    def reject(self, memory_id: str, *, reviewer: str) -> MemoryRecord:
        current = self.store.get(memory_id)
        if current.status != MemoryStatus.CANDIDATE:
            raise InvalidMemoryTransition("only candidate memory can be rejected")
        if not reviewer:
            raise ValueError("reviewer is required")
        rejected = replace(current, status=MemoryStatus.REJECTED)
        self.store.replace(rejected)
        return rejected

    def retrieve(
        self,
        *,
        tenant_id: str,
        project_id: str | None,
        query: str,
        limit: int = 5,
        now: datetime | None = None,
    ) -> list[MemoryRecord]:
        now = now or datetime.now(timezone.utc)
        terms = {term.casefold() for term in query.split() if term}
        candidates = [
            item
            for item in self.store.list_for_scope(tenant_id, project_id)
            if item.visible_at(now)
        ]

        def score(item: MemoryRecord) -> tuple[int, float, float]:
            haystack = f"{item.statement} {' '.join(item.tags)}".casefold()
            matches = sum(1 for term in terms if term in haystack)
            return (matches, item.confidence, item.created_at.timestamp())

        candidates.sort(key=score, reverse=True)
        return candidates[:limit]
