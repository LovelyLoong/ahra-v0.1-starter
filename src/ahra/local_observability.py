from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


RECORD_SCHEMA_VERSION = "ahra/local-observability-record/0.1"
RECORD_TYPES = {"audit_event", "trace_summary", "usage_summary", "eval_result"}
FORBIDDEN_PRIVATE_KEYS = {
    "chainofthought",
    "thoughtchain",
    "privatechainofthought",
    "privatethoughts",
    "hiddenreasoning",
    "rawreasoning",
    "reasoningtrace",
    "cot",
}


class LocalObservabilityError(ValueError):
    """Raised when a local observability/eval record must fail closed."""


@dataclass(frozen=True, slots=True)
class PublishedLocalRecord:
    task_id: str
    record_type: str
    sha256: str
    path: Path
    artifact_record: dict[str, Any]
    evidence_record: dict[str, Any] | None


def deterministic_json_bytes(data: dict[str, Any]) -> bytes:
    """Serialize JSON deterministically for local content addressing."""

    return (
        json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def validate_local_record(record: dict[str, Any]) -> None:
    if not isinstance(record, dict):
        raise LocalObservabilityError("local record must be a JSON object")
    _reject_private_thought_chain(record)
    if record.get("schema_version") != RECORD_SCHEMA_VERSION:
        raise LocalObservabilityError(
            f"schema_version must be {RECORD_SCHEMA_VERSION}"
        )
    record_type = record.get("record_type")
    if record_type not in RECORD_TYPES:
        raise LocalObservabilityError(f"unsupported record_type: {record_type!r}")
    for key in ["record_id", "task_id", "created_at", "created_by", "payload"]:
        if key not in record:
            raise LocalObservabilityError(f"local record missing {key}")
    if not isinstance(record["payload"], dict):
        raise LocalObservabilityError("local record payload must be an object")


def publish_local_record(
    task_dir: str | Path,
    record: dict[str, Any],
    *,
    evidence: bool = False,
    input_refs: list[str] | None = None,
    evidence_refs: list[str] | None = None,
) -> PublishedLocalRecord:
    """Write a local record and attach it to AWKP artifact/evidence manifests.

    This helper writes artifacts and optional evidence records only. It does not
    update task state and therefore cannot replace AWKP state or event authority.
    """

    validate_local_record(record)
    task_root = Path(task_dir).resolve()
    task_id = str(record["task_id"])
    if task_root.name != task_id:
        raise LocalObservabilityError(
            f"record task_id {task_id!r} must match task directory {task_root.name!r}"
        )

    payload = deterministic_json_bytes(record)
    digest = hashlib.sha256(payload).hexdigest()
    record_type = str(record["record_type"])
    slug = record_type.replace("_", "-")
    name = f"{slug}-{digest[:16]}.json"
    relative_path = Path("local-records") / name
    path = task_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != payload:
        raise LocalObservabilityError(f"content-addressed path collision: {path}")
    path.write_bytes(payload)

    artifact_manifest_path = task_root / "artifact-manifest.json"
    evidence_manifest_path = task_root / "evidence-manifest.json"
    artifact_manifest = _load_manifest(
        artifact_manifest_path,
        task_id=task_id,
        key="artifacts",
    )
    evidence_manifest = _load_manifest(
        evidence_manifest_path,
        task_id=task_id,
        key="evidence",
    )

    id_slug = record_type.upper().replace("_", "-")
    artifact_id = f"ART-{task_id}-{id_slug}-{digest[:12]}"
    evidence_id = f"EVD-{task_id}-{id_slug}-{digest[:12]}"
    created_by = str(record["created_by"])
    created_at = str(record["created_at"])
    artifact_record = {
        "artifact_id": artifact_id,
        "task_id": task_id,
        "kind": f"local_{record_type}",
        "name": name,
        "uri": f"local://{relative_path.as_posix()}",
        "sha256": digest,
        "media_type": "application/json",
        "created_by": created_by,
        "created_at": created_at,
        "input_refs": input_refs or [],
        "evidence_refs": [evidence_id] if evidence else [],
        "supersedes": None,
    }
    evidence_record = None
    if evidence:
        evidence_record = {
            "evidence_id": evidence_id,
            "task_id": task_id,
            "kind": f"local_{record_type}",
            "name": name,
            "uri": f"local://{relative_path.as_posix()}",
            "sha256": digest,
            "media_type": "application/json",
            "created_by": created_by,
            "created_at": created_at,
            "refs": [artifact_id, *(evidence_refs or [])],
        }

    _append_unique_record(artifact_manifest["artifacts"], "artifact_id", artifact_record)
    if evidence_record is not None:
        _append_unique_record(evidence_manifest["evidence"], "evidence_id", evidence_record)
    _write_manifest(artifact_manifest_path, artifact_manifest)
    _write_manifest(evidence_manifest_path, evidence_manifest)

    return PublishedLocalRecord(
        task_id=task_id,
        record_type=record_type,
        sha256=digest,
        path=path,
        artifact_record=artifact_record,
        evidence_record=evidence_record,
    )


def _reject_private_thought_chain(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
            if normalized in FORBIDDEN_PRIVATE_KEYS:
                raise LocalObservabilityError(
                    f"private thought-chain field is not allowed: {path}.{key}"
                )
            _reject_private_thought_chain(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_private_thought_chain(item, f"{path}[{index}]")


def _load_manifest(path: Path, *, task_id: str, key: str) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": "awkp/0.1", "task_id": task_id, key: []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise LocalObservabilityError(f"manifest must be an object: {path}")
    if data.get("schema_version") != "awkp/0.1":
        raise LocalObservabilityError(f"{path.name} schema_version must be awkp/0.1")
    if data.get("task_id") != task_id:
        raise LocalObservabilityError(f"{path.name} task_id must be {task_id}")
    if not isinstance(data.get(key), list):
        raise LocalObservabilityError(f"{path.name} {key} must be an array")
    return data


def _write_manifest(path: Path, data: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _append_unique_record(
    records: list[dict[str, Any]],
    id_key: str,
    record: dict[str, Any],
) -> None:
    record_id = record[id_key]
    for existing in records:
        if existing.get(id_key) == record_id:
            if existing != record:
                raise LocalObservabilityError(f"conflicting manifest record: {record_id}")
            return
    records.append(record)
