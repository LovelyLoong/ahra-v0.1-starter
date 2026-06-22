from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from ahra.ports import ArtifactStore, EventPublisher, EvidenceStore

from .models import to_jsonable


@runtime_checkable
class ReferenceRunStore(ArtifactStore, EvidenceStore, EventPublisher, Protocol):
    @property
    def run_dir(self) -> Path: ...

    def write_json(self, name: str, data: Any) -> Path: ...

    def write_artifact(
        self,
        name: str,
        content: bytes | str | Any,
        *,
        task_id: str,
        kind: str,
        media_type: str,
        created_by: str,
        input_refs: list[str] | None = None,
        evidence_refs: list[str] | None = None,
    ) -> dict[str, Any]: ...

    def write_evidence(
        self,
        name: str,
        content: bytes | str | Any,
        *,
        task_id: str,
        kind: str,
        media_type: str = "application/json",
        created_by: str = "workflow-module:reference-runner",
        refs: list[str] | None = None,
    ) -> dict[str, Any]: ...

    def event(self, event: str, **payload: Any) -> None: ...


class FileRunStore:
    """File-backed artifact/event sink for reference workflow modules.

    This is not the authoritative AHRA RunStore. It stores module artifacts,
    evidence, reports, and an append-only local event stream for inspection.
    """

    def __init__(self, run_dir: Path) -> None:
        self._run_dir = run_dir.resolve()
        self._run_dir.mkdir(parents=True, exist_ok=True)
        self._artifacts = self._load_manifest_records("artifact-manifest.json", "artifacts")
        self._evidence = self._load_manifest_records("evidence-manifest.json", "evidence")

    @property
    def run_dir(self) -> Path:
        return self._run_dir

    def subdir(self, name: str) -> Path:
        path = self.run_dir / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_json(self, name: str, data: Any) -> Path:
        path = self.run_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(to_jsonable(data), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(path)
        return path

    def write_text(self, name: str, text: str) -> Path:
        path = self.run_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def put(self, content: bytes, media_type: str, metadata: dict[str, Any]) -> str:
        name = str(metadata.get("name") or f"objects/{uuid4().hex}")
        path = self.run_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return self._local_uri(path)

    def get(self, artifact_ref: str) -> bytes:
        return self._path_from_local_uri(artifact_ref).read_bytes()

    def write_artifact(
        self,
        name: str,
        content: bytes | str | Any,
        *,
        task_id: str,
        kind: str,
        media_type: str,
        created_by: str,
        input_refs: list[str] | None = None,
        evidence_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        if isinstance(content, bytes):
            payload = content
        elif isinstance(content, str):
            payload = content.encode("utf-8")
        else:
            payload = json.dumps(to_jsonable(content), ensure_ascii=False, indent=2).encode("utf-8")
        path = self.run_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        record = {
            "artifact_id": f"ART-{uuid4().hex}",
            "task_id": task_id,
            "kind": kind,
            "name": Path(name).name,
            "uri": self._local_uri(path),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "media_type": media_type,
            "created_by": created_by,
            "created_at": self._now(),
            "input_refs": input_refs or [],
            "evidence_refs": evidence_refs or [],
            "supersedes": None,
        }
        self._artifacts.append(record)
        self._write_artifact_manifest(task_id)
        return record

    def write_evidence(
        self,
        name: str,
        content: bytes | str | Any,
        *,
        task_id: str,
        kind: str,
        media_type: str = "application/json",
        created_by: str = "workflow-module:reference-runner",
        refs: list[str] | None = None,
    ) -> dict[str, Any]:
        if isinstance(content, bytes):
            payload = content
        elif isinstance(content, str):
            payload = content.encode("utf-8")
        else:
            payload = json.dumps(to_jsonable(content), ensure_ascii=False, indent=2).encode("utf-8")
        path = self.run_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        record = {
            "evidence_id": f"EVD-{uuid4().hex}",
            "task_id": task_id,
            "kind": kind,
            "name": Path(name).name,
            "uri": self._local_uri(path),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "media_type": media_type,
            "created_by": created_by,
            "created_at": self._now(),
            "refs": refs or [],
        }
        self._evidence.append(record)
        self._write_evidence_manifest(task_id)
        return record

    def event(self, event: str, **payload: Any) -> None:
        data = to_jsonable(payload)
        record = {
            "specversion": "1.0",
            "id": f"EVT-{uuid4().hex}",
            "source": "ahra://reference-runner",
            "type": f"dev.ahra.workflow.{event}.v1",
            "subject": str(data.get("task_id") or data.get("goal_id") or data.get("run_id") or "run"),
            "time": self._now(),
            "datacontenttype": "application/json",
            "data": data,
        }
        path = self.run_dir / "events.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def publish(self, event_type: str, subject: str, data: dict[str, Any]) -> None:
        self.event(event_type, subject=subject, **data)

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat().replace("+00:00", "Z")

    def _local_uri(self, path: Path) -> str:
        return f"local://{path.relative_to(self.run_dir).as_posix()}"

    def _path_from_local_uri(self, uri: str) -> Path:
        if not uri.startswith("local://"):
            raise ValueError(f"unsupported local uri: {uri}")
        return self.run_dir / uri.removeprefix("local://")

    def _write_artifact_manifest(self, task_id: str) -> None:
        self.write_json(
            "artifact-manifest.json",
            {
                "schema_version": "awkp/0.1",
                "task_id": task_id,
                "artifacts": self._artifacts,
            },
        )

    def _write_evidence_manifest(self, task_id: str) -> None:
        self.write_json(
            "evidence-manifest.json",
            {
                "schema_version": "awkp/0.1",
                "task_id": task_id,
                "evidence": self._evidence,
            },
        )

    def _load_manifest_records(self, name: str, key: str) -> list[dict[str, Any]]:
        path = self.run_dir / name
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        records = data.get(key, [])
        if not isinstance(records, list):
            raise ValueError(f"invalid {name}: {key} must be a list")
        return [dict(record) for record in records]
