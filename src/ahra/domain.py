from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RunStatus(StrEnum):
    CREATED = "created"
    ADMITTED = "admitted"
    QUEUED = "queued"
    PROVISIONING = "provisioning"
    RUNNING = "running"
    PAUSED_INPUT = "paused_input"
    PAUSED_AUTH = "paused_auth"
    PAUSED_POLICY = "paused_policy"
    BACKOFF = "backoff"
    SUSPENDED = "suspended"
    VERIFYING = "verifying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELED = "canceled"

    @property
    def terminal(self) -> bool:
        return self in {
            self.SUCCEEDED,
            self.FAILED,
            self.TIMED_OUT,
            self.CANCELED,
        }


class MemoryKind(StrEnum):
    WORKING = "working"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"


class MemoryStatus(StrEnum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"
    TOMBSTONED = "tombstoned"


class SideEffect(StrEnum):
    READ_ONLY = "read_only"
    REVERSIBLE_WRITE = "reversible_write"
    EXTERNAL_WRITE = "external_write"
    IRREVERSIBLE_OR_HIGH_IMPACT = "irreversible_or_high_impact"


@dataclass(frozen=True, slots=True)
class Lease:
    holder: str
    fencing_token: int
    heartbeat_at: datetime
    expires_at: datetime

    def active_at(self, now: datetime) -> bool:
        return self.expires_at > now


@dataclass(frozen=True, slots=True)
class Budget:
    max_cost_usd: float
    max_model_calls: int
    max_tool_calls: int
    deadline: datetime


@dataclass(frozen=True, slots=True)
class Usage:
    cost_usd: float = 0.0
    model_calls: int = 0
    tool_calls: int = 0


@dataclass(frozen=True, slots=True)
class RunRecord:
    run_id: str
    task_id: str
    context_id: str
    attempt: int
    agent_release: str
    status: RunStatus
    status_version: int
    budgets: Budget
    trace_id: str
    created_at: datetime
    updated_at: datetime
    usage: Usage = field(default_factory=Usage)
    lease: Lease | None = None
    workflow_definition: str | None = None
    workflow_execution_id: str | None = None
    session_id: str | None = None
    runtime_profile: str | None = None
    workspace_ref: str | None = None
    context_manifest_ref: str | None = None
    checkpoint_ref: str | None = None
    failure: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["schema_version"] = "ahra/run/0.1"
        result["status"] = self.status.value
        for key in ("created_at", "updated_at"):
            result[key] = getattr(self, key).isoformat().replace("+00:00", "Z")
        result["budgets"]["deadline"] = self.budgets.deadline.isoformat().replace("+00:00", "Z")
        if self.lease:
            result["lease"]["heartbeat_at"] = self.lease.heartbeat_at.isoformat().replace("+00:00", "Z")
            result["lease"]["expires_at"] = self.lease.expires_at.isoformat().replace("+00:00", "Z")
        return result


@dataclass(frozen=True, slots=True)
class MemoryScope:
    tenant_id: str
    project_id: str | None = None
    task_id: str | None = None
    subject_id: str | None = None
    agent_id: str | None = None


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    memory_id: str
    kind: MemoryKind
    scope: MemoryScope
    statement: str
    status: MemoryStatus
    confidence: float
    source_refs: tuple[str, ...]
    created_by: str
    created_at: datetime
    sensitivity: str
    retention_policy: str
    entities: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    review_after: datetime | None = None
    supersedes: tuple[str, ...] = ()

    def visible_at(self, now: datetime) -> bool:
        if self.status != MemoryStatus.ACTIVE:
            return False
        if self.valid_from and self.valid_from > now:
            return False
        if self.valid_to and self.valid_to <= now:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        def iso(value: datetime | None) -> str | None:
            return value.isoformat().replace("+00:00", "Z") if value else None

        return {
            "schema_version": "ahra/memory-record/0.1",
            "memory_id": self.memory_id,
            "kind": self.kind.value,
            "scope": asdict(self.scope),
            "content": {
                "statement": self.statement,
                "entities": list(self.entities),
                "tags": list(self.tags),
            },
            "status": self.status.value,
            "confidence": self.confidence,
            "source_refs": list(self.source_refs),
            "created_by": self.created_by,
            "created_at": iso(self.created_at),
            "valid_from": iso(self.valid_from),
            "valid_to": iso(self.valid_to),
            "review_after": iso(self.review_after),
            "sensitivity": self.sensitivity,
            "retention_policy": self.retention_policy,
            "supersedes": list(self.supersedes),
        }


@dataclass(frozen=True, slots=True)
class ToolDescriptor:
    name: str
    version: str
    side_effect: SideEffect
    risk_level: str
    required_scopes: tuple[str, ...]
    data_classes_allowed: tuple[str, ...]
    idempotency: str
    timeout_seconds: int
    compensation_tool: str | None = None


@dataclass(frozen=True, slots=True)
class PolicyInput:
    human_identity: str
    agent_release: str
    workload_identity: str
    task_id: str
    task_risk: str
    action: str
    resource: str
    granted_scopes: tuple[str, ...]
    data_classes: tuple[str, ...]
    approval_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    decision_id: str
    allow: bool
    reason_code: str
    policy_version: str
    approval_required: bool
    credential_scopes: tuple[str, ...]
    decided_at: datetime
    required_runtime_tier: str | None = None


@dataclass(frozen=True, slots=True)
class ContextItem:
    kind: str
    ref: str
    sha256: str
    trust: str
    priority: int
    estimated_tokens: int


@dataclass(frozen=True, slots=True)
class ContextManifest:
    context_manifest_id: str
    run_id: str
    agent_release_digest: str
    items: tuple[ContextItem, ...]
    token_budget: int
    compiler_version: str
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "ahra/context-manifest/0.1",
            "context_manifest_id": self.context_manifest_id,
            "run_id": self.run_id,
            "agent_release_digest": self.agent_release_digest,
            "items": [asdict(item) for item in self.items],
            "token_budget": self.token_budget,
            "compiler_version": self.compiler_version,
            "sha256": self.sha256,
        }
