from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Iterable


TASK_ID_PATTERN = re.compile(r"^TASK-[A-Za-z0-9._-]+$")


class AwkpTaskCreateError(ValueError):
    """Raised when an AWKP task skeleton request is malformed."""


@dataclass(frozen=True, slots=True)
class AwkpTaskCreateRequest:
    task_id: str
    title: str
    description: str
    context_id: str
    acceptance_criteria: tuple[str, ...]
    work_root: Path | str = "work"
    priority: str = "P1"
    risk_level: str = "R1"
    requester: str = "human:maintainer"
    reviewer: str = "agent:independent-verifier"
    actor: str = "human:maintainer"
    depends_on: tuple[str, ...] = ()
    input_refs: tuple[str, ...] = ()
    output_contract_kinds: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AwkpTaskCreateResult:
    task_id: str
    task_dir: str
    state: str
    state_version: int
    event_id: str
    idempotency_key: str
    created_at: str
    files: tuple[str, ...]


class AwkpTaskCreator:
    """Create lint-clean AWKP task skeletons without authoring task state by hand."""

    def __init__(self, *, clock: Callable[[], datetime | str] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))

    def create(self, request: AwkpTaskCreateRequest) -> AwkpTaskCreateResult:
        _validate_request(request)
        work_root = Path(request.work_root)
        task_dir = work_root / "tasks" / request.task_id
        if task_dir.exists():
            raise AwkpTaskCreateError(f"task directory already exists: {task_dir}")

        created_at = _format_utc(_coerce_datetime(self._clock()))
        evidence_dir = task_dir / "evidence"
        handoff_dir = task_dir / "handoffs"
        evidence_dir.mkdir(parents=True)
        handoff_dir.mkdir(parents=True)

        task_md = _task_markdown(request, created_at)
        (task_dir / "task.md").write_text(task_md, encoding="utf-8")
        _write_json(task_dir / "state.json", _state_document(request, created_at))
        _append_event(task_dir / "events.jsonl", _created_event(request, created_at))
        _write_json(
            task_dir / "artifact-manifest.json",
            {"schema_version": "awkp/0.1", "task_id": request.task_id, "artifacts": []},
        )
        _write_json(
            task_dir / "evidence-manifest.json",
            {"schema_version": "awkp/0.1", "task_id": request.task_id, "evidence": []},
        )

        return AwkpTaskCreateResult(
            task_id=request.task_id,
            task_dir=str(task_dir),
            state="ready",
            state_version=0,
            event_id=f"EVT-{request.task_id}-0001",
            idempotency_key=f"{request.task_id}:task-created:task-create-cli:1",
            created_at=created_at,
            files=(
                "task.md",
                "state.json",
                "events.jsonl",
                "artifact-manifest.json",
                "evidence-manifest.json",
                "evidence/",
                "handoffs/",
            ),
        )


def _validate_request(request: AwkpTaskCreateRequest) -> None:
    if not TASK_ID_PATTERN.fullmatch(request.task_id):
        raise AwkpTaskCreateError(f"invalid task id: {request.task_id!r}")
    for field_name, value in [
        ("title", request.title),
        ("description", request.description),
        ("context_id", request.context_id),
        ("priority", request.priority),
        ("risk_level", request.risk_level),
        ("requester", request.requester),
        ("reviewer", request.reviewer),
        ("actor", request.actor),
    ]:
        if not str(value or "").strip():
            raise AwkpTaskCreateError(f"{field_name} is required")
    criteria = _clean_items(request.acceptance_criteria)
    if not criteria:
        raise AwkpTaskCreateError("at least one --acceptance value is required")
    for depends_on in request.depends_on:
        if not TASK_ID_PATTERN.fullmatch(depends_on):
            raise AwkpTaskCreateError(f"invalid depends_on task id: {depends_on!r}")
    for kind in request.output_contract_kinds:
        if not str(kind).strip():
            raise AwkpTaskCreateError("output contract kind cannot be empty")


def _task_markdown(request: AwkpTaskCreateRequest, created_at: str) -> str:
    output_contract = _output_contract_frontmatter(request.output_contract_kinds)
    return "\n".join(
        [
            "---",
            "type: WorkItem",
            f"id: {request.task_id}",
            "schema_version: awkp/0.1",
            f"title: {_yaml_scalar(request.title)}",
            f"description: {_yaml_scalar(request.description)}",
            f"context_id: {_yaml_scalar(request.context_id)}",
            f"priority: {_yaml_scalar(request.priority)}",
            f"risk_level: {_yaml_scalar(request.risk_level)}",
            f"requester: {_yaml_scalar(request.requester)}",
            f"reviewer: {_yaml_scalar(request.reviewer)}",
            f"created_at: {created_at}",
            f"depends_on: {_yaml_flow_list(request.depends_on)}",
            f"input_refs: {_yaml_flow_list(request.input_refs)}",
            *output_contract,
            "---",
            "",
            "# Goal",
            "",
            request.description.strip(),
            "",
            "# Acceptance criteria",
            "",
            *[f"- [ ] {criterion}" for criterion in _clean_items(request.acceptance_criteria)],
            "",
        ]
    )


def _state_document(request: AwkpTaskCreateRequest, created_at: str) -> dict[str, object]:
    return {
        "schema_version": "awkp/0.1",
        "task_id": request.task_id,
        "context_id": request.context_id,
        "state": "ready",
        "state_version": 0,
        "attempt": 0,
        "owner": None,
        "lease": None,
        "next_action": "Task skeleton created; claim the task before producing evidence.",
        "pause_reason": None,
        "blockers": [],
        "artifact_refs": [],
        "evidence_refs": [],
        "updated_at": created_at,
    }


def _created_event(request: AwkpTaskCreateRequest, created_at: str) -> dict[str, object]:
    return {
        "schema_version": "awkp/0.1",
        "event_id": f"EVT-{request.task_id}-0001",
        "idempotency_key": f"{request.task_id}:task-created:task-create-cli:1",
        "task_id": request.task_id,
        "context_id": request.context_id,
        "event_type": "task_created",
        "actor": request.actor,
        "occurred_at": created_at,
        "causation_id": None,
        "correlation_id": request.context_id,
        "from_state": None,
        "to_state": "ready",
        "reason": "Created lint-clean AWKP task skeleton through ahra task create.",
        "refs": ["task.md", "state.json"],
    }


def _output_contract_frontmatter(kinds: Iterable[str]) -> list[str]:
    clean = _clean_items(kinds)
    if not clean:
        return ["output_contract: []"]
    lines = ["output_contract:"]
    for kind in clean:
        lines.append(f"  - kind: {_yaml_scalar(kind)}")
    return lines


def _clean_items(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(str(value).strip() for value in values if str(value).strip())


def _yaml_scalar(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def _yaml_flow_list(values: Iterable[str]) -> str:
    clean = _clean_items(values)
    if not clean:
        return "[]"
    return "[" + ", ".join(_yaml_scalar(value) for value in clean) + "]"


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _append_event(path: Path, event: dict[str, object]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")


def _coerce_datetime(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise AwkpTaskCreateError("clock must return datetime or ISO string")
    if result.tzinfo is None:
        result = result.replace(tzinfo=UTC)
    return result.astimezone(UTC)


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
