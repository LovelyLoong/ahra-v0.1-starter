from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .goal_operations import GoalExecutionRequest
from .request_draft import RequestDraft


@dataclass(frozen=True, slots=True)
class ApprovalEvent:
    event_id: str
    approval_id: str
    event_type: str
    actor: str
    occurred_at: datetime
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "eventId": self.event_id,
            "approvalId": self.approval_id,
            "eventType": self.event_type,
            "actor": self.actor,
            "occurredAt": self.occurred_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class ApprovalRecord:
    approval_id: str
    request_id: str
    intent_id: str
    producer_actor: str
    status: str
    requested_by: str
    requested_at: datetime
    decision_by: str | None = None
    decided_at: datetime | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "approvalId": self.approval_id,
            "requestId": self.request_id,
            "intentId": self.intent_id,
            "producerActor": self.producer_actor,
            "status": self.status,
            "requestedBy": self.requested_by,
            "requestedAt": _iso(self.requested_at),
            "decisionBy": self.decision_by,
            "decidedAt": _iso(self.decided_at) if self.decided_at else None,
            "reason": self.reason,
        }


class ApprovalService:
    """Human authorization gate for freezing RequestDraft into GoalExecutionRequest."""

    def __init__(self, *, clock=None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self._records: dict[str, ApprovalRecord] = {}
        self._events: list[ApprovalEvent] = []

    @property
    def events(self) -> tuple[ApprovalEvent, ...]:
        return tuple(self._events)

    def request_authorization(self, draft: RequestDraft, *, actor: str, reason: str = "") -> ApprovalRecord:
        approval_id = "APR-" + draft.request_id.removeprefix("REQ-")
        if approval_id in self._records:
            return self._records[approval_id]
        now = self._now()
        record = ApprovalRecord(
            approval_id=approval_id,
            request_id=draft.request_id,
            intent_id=draft.intent_id,
            producer_actor=draft.producer_actor,
            status="waiting_auth",
            requested_by=actor,
            requested_at=now,
            reason=reason or "RequestDraft is waiting for human authorization.",
        )
        self._records[approval_id] = record
        self._append(approval_id, "approval_requested", actor, record.reason, now)
        return record

    def approve(self, approval_id: str, *, actor: str, reason: str = "") -> ApprovalRecord:
        record = self._require_record(approval_id)
        if record.status != "waiting_auth":
            raise ValueError(f"approval {approval_id} is not waiting_auth")
        if actor == record.producer_actor:
            raise ValueError("producer cannot self-authorize a RequestDraft")
        if not actor.startswith("human:"):
            raise ValueError("RequestDraft freeze requires an explicit human approval actor")
        now = self._now()
        approved = replace(
            record,
            status="approved",
            decision_by=actor,
            decided_at=now,
            reason=reason or "Human approved acceptance criteria and capability boundary.",
        )
        self._records[approval_id] = approved
        self._append(approval_id, "approval_granted", actor, approved.reason, now)
        return approved

    def reject(self, approval_id: str, *, actor: str, reason: str) -> ApprovalRecord:
        record = self._require_record(approval_id)
        now = self._now()
        rejected = replace(record, status="rejected", decision_by=actor, decided_at=now, reason=reason)
        self._records[approval_id] = rejected
        self._append(approval_id, "approval_rejected", actor, reason, now)
        return rejected

    def freeze(self, draft: RequestDraft, *, approval_id: str) -> GoalExecutionRequest:
        record = self._require_record(approval_id)
        if record.request_id != draft.request_id:
            raise ValueError("approval does not belong to this RequestDraft")
        if record.status != "approved":
            raise ValueError("RequestDraft cannot freeze before approval")
        return GoalExecutionRequest(
            name=draft.name,
            request_id=draft.request_id,
            idempotency_key=draft.idempotency_key,
            profile_ref=draft.profile_ref,
            workspace_ref=Path(draft.workspace_ref),
            artifact_dir=Path(draft.artifact_dir),
            store_kind=draft.store_kind,
            store_path=Path(draft.store_path),
            planner_adapter_ref=draft.planner_adapter_ref,
            executor_adapter_ref=draft.executor_adapter_ref,
            gate_runner_adapter_ref=draft.gate_runner_adapter_ref,
            runtime_ref=draft.runtime_ref,
            runtime_digest=draft.runtime_digest,
            goal_ref=draft.goal_ref,
            goal_digest=draft.goal_digest,
            claim_graph_digest=draft.claim_graph_digest,
            claim_graph_ref=None,
            required_claim_refs=draft.required_claim_refs,
            registered_node_types=draft.registered_node_types,
            registered_gate_refs=draft.registered_gate_refs,
            gate_definitions=(),
            registered_runtime_refs=draft.registered_runtime_refs,
            allowed_capabilities=draft.allowed_capabilities,
            plan_draft=draft.plan_draft,
            max_repair_cycles=draft.max_repair_cycles,
            max_concurrency=draft.max_concurrency,
            branch=draft.branch,
        )

    def status(self, approval_id: str) -> str:
        return self._require_record(approval_id).status

    def get(self, approval_id: str) -> ApprovalRecord:
        return self._require_record(approval_id)

    def _require_record(self, approval_id: str) -> ApprovalRecord:
        try:
            return self._records[approval_id]
        except KeyError as exc:
            raise ValueError(f"unknown approval id: {approval_id}") from exc

    def _append(self, approval_id: str, event_type: str, actor: str, reason: str, occurred_at: datetime) -> None:
        self._events.append(
            ApprovalEvent(
                event_id=f"AEVT-{len(self._events) + 1:04d}",
                approval_id=approval_id,
                event_type=event_type,
                actor=actor,
                occurred_at=occurred_at,
                reason=reason,
            )
        )

    def _now(self) -> datetime:
        value = self._clock()
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=UTC)
        raise TypeError("ApprovalService clock must return datetime")


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


__all__ = ["ApprovalEvent", "ApprovalRecord", "ApprovalService"]
