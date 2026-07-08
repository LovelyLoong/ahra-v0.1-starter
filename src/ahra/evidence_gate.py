from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
import zlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


ALLOWED_DECISIONS = {"approve", "request_changes"}
PASSED_STATUSES = {"passed", "pass"}
FAILED_STATUSES = {"failed", "fail", "missing", "blocked"}
DEVELOPMENT_BOUNDED_PROFILE_REF = "profile/development-bounded"
TASK_LOCAL_URI_PREFIXES = {"evidence", "handoffs", "local-records", "runs"}
PACK_OBJECT_TYPES = {
    1: "commit",
    2: "tree",
    3: "blob",
    4: "tag",
}


class EvidenceGateError(ValueError):
    """Raised when the verifier gate must fail closed."""


@dataclass(frozen=True, slots=True)
class AcceptanceCriterion:
    index: int
    text: str


@dataclass(frozen=True, slots=True)
class EvidenceGateResult:
    task_id: str
    decision: str
    state: str
    state_version: int
    report_artifact_id: str | None
    report_evidence_id: str | None
    event_id: str | None
    report_path: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "decision": self.decision,
            "state": self.state,
            "state_version": self.state_version,
            "report_artifact_id": self.report_artifact_id,
            "report_evidence_id": self.report_evidence_id,
            "event_id": self.event_id,
            "report_path": self.report_path,
        }


@dataclass(frozen=True, slots=True)
class KernelEvidenceIndex:
    evidence: dict[str, dict[str, Any]]
    gate_runs: dict[str, dict[str, Any]]


@dataclass(frozen=True, slots=True)
class EvidenceGateReviewRequirementReport:
    task_id: str
    requires_semantic_reviews: bool
    profile_refs: tuple[str, ...]
    missing_inputs: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "requires_semantic_reviews": self.requires_semantic_reviews,
            "profile_refs": list(self.profile_refs),
            "missing_inputs": list(self.missing_inputs),
        }


def evaluate_task_gate(
    task: str | Path,
    *,
    work_root: str | Path = "work",
    expected_version: int,
    report_path: str | Path,
    actor: str,
    decision: str | None = None,
    dry_run: bool = False,
) -> EvidenceGateResult:
    """Validate evidence and optionally transition an AWKP task state."""

    task_dir = _resolve_task_dir(task, work_root)
    task_id = task_dir.name
    state_path = task_dir / "state.json"
    task_path = task_dir / "task.md"
    artifact_manifest_path = task_dir / "artifact-manifest.json"
    evidence_manifest_path = task_dir / "evidence-manifest.json"
    event_path = task_dir / "events.jsonl"

    state = _load_json(state_path)
    if state.get("task_id") != task_id:
        raise EvidenceGateError(f"state task_id does not match task directory: {task_id}")
    if state.get("state") != "review":
        raise EvidenceGateError(f"task must be in review; current state is {state.get('state')!r}")
    if state.get("state_version") != expected_version:
        raise EvidenceGateError(
            f"expected state_version {expected_version}, current {state.get('state_version')}"
        )

    criteria = parse_acceptance_criteria(task_path)
    if not criteria:
        raise EvidenceGateError("task has no parseable acceptance criteria")

    artifact_manifest = _load_manifest(artifact_manifest_path, "artifacts", task_id)
    evidence_manifest = _load_manifest(evidence_manifest_path, "evidence", task_id)
    _validate_manifest_hashes(task_dir, artifact_manifest, "artifacts")
    _validate_manifest_hashes(task_dir, evidence_manifest, "evidence")

    report = _load_json(Path(report_path))
    report_decision = str(decision or report.get("decision") or "").strip()
    if report_decision not in ALLOWED_DECISIONS:
        raise EvidenceGateError(f"unsupported gate decision: {report_decision!r}")
    if report.get("task_id") != task_id:
        raise EvidenceGateError(f"report task_id must be {task_id}")
    report_actor = str(report.get("verifier") or report.get("actor") or actor)
    if report_actor != actor:
        raise EvidenceGateError("report verifier must match caller actor")

    producer_identities = _producer_identities(artifact_manifest, evidence_manifest, event_path)
    if actor in producer_identities:
        raise EvidenceGateError(f"verifier actor {actor!r} is also a producer identity")

    evidence_by_id = {str(item.get("evidence_id")): item for item in evidence_manifest.get("evidence", [])}
    artifact_by_id = {str(item.get("artifact_id")): item for item in artifact_manifest.get("artifacts", [])}
    kernel_evidence = _kernel_evidence_index(task_dir, artifact_manifest, evidence_manifest)
    assessments = _map_criteria(criteria, report, evidence_by_id)
    command_backed_criteria = _command_backed_criteria(report)
    _validate_command_results(report, report_decision, kernel_evidence)
    requires_semantic_review = _requires_semantic_code_review(
        task_dir=task_dir,
        task_path=task_path,
        artifact_manifest=artifact_manifest,
    )

    if report_decision == "approve":
        if state.get("blockers"):
            raise EvidenceGateError("cannot approve a task that still records blockers")
        if requires_semantic_review:
            _validate_semantic_code_reviews(
                report=report,
                criteria=criteria,
                assessments=assessments,
                evidence_by_id=evidence_by_id,
                kernel_evidence=kernel_evidence,
                producer_identities=producer_identities,
            )
        for criterion in criteria:
            item = assessments.get(criterion.index)
            if item is None:
                raise EvidenceGateError(f"missing assessment for criterion {criterion.index}")
            if _status(item) not in PASSED_STATUSES:
                raise EvidenceGateError(f"criterion {criterion.index} is not passed")
            refs = _refs(item)
            if not refs:
                raise EvidenceGateError(f"criterion {criterion.index} has no evidence_refs")
            for ref in refs:
                if ref not in evidence_by_id:
                    raise EvidenceGateError(f"criterion {criterion.index} references unknown evidence {ref}")
            if criterion.index in command_backed_criteria:
                _validate_command_backed_criterion(criterion.index, refs, kernel_evidence)
        target_state = "completed"
    else:
        missing_or_failed = [
            criterion.index
            for criterion in criteria
            if criterion.index not in assessments
            or _status(assessments[criterion.index]) in FAILED_STATUSES
        ]
        if not missing_or_failed:
            raise EvidenceGateError("request_changes requires at least one failed or missing criterion")
        target_state = "changes_requested"

    if dry_run:
        return EvidenceGateResult(
            task_id=task_id,
            decision=report_decision,
            state=state["state"],
            state_version=state["state_version"],
            report_artifact_id=None,
            report_evidence_id=None,
            event_id=None,
            report_path=None,
        )

    now = _now()
    report_name = f"evidence-gate-report-{expected_version + 1}.json"
    gate_report = _build_gate_report(
        task_id=task_id,
        actor=actor,
        decision=report_decision,
        target_state=target_state,
        criteria=criteria,
        input_report=report,
        now=now,
    )
    report_bytes = _json_bytes(gate_report)
    report_sha = hashlib.sha256(report_bytes).hexdigest()
    report_file = task_dir / "evidence" / report_name
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_bytes(report_bytes)

    artifact_record = _artifact_record(
        task_id=task_id,
        artifact_id=_next_record_id("ART", task_id, artifact_manifest.get("artifacts", [])),
        name=report_name,
        sha256=report_sha,
        created_by=actor,
        created_at=now,
        input_refs=["task.md", "state.json", "artifact-manifest.json", "evidence-manifest.json"],
    )
    evidence_record = _evidence_record(
        task_id=task_id,
        evidence_id=_next_record_id("EVD", task_id, evidence_manifest.get("evidence", [])),
        name=report_name,
        sha256=report_sha,
        created_by=actor,
        created_at=now,
        refs=[artifact_record["artifact_id"], *sorted(_report_evidence_refs(gate_report))],
    )
    artifact_record["evidence_refs"] = [evidence_record["evidence_id"]]
    artifact_manifest["artifacts"].append(artifact_record)
    evidence_manifest["evidence"].append(evidence_record)
    _write_json(artifact_manifest_path, artifact_manifest)
    _write_json(evidence_manifest_path, evidence_manifest)

    previous_event_id = _last_event_id(event_path)
    event_id = _next_event_id(task_id, event_path)
    event_type = "evidence_gate_approved" if target_state == "completed" else "evidence_gate_changes_requested"
    event = {
        "schema_version": "awkp/0.1",
        "event_id": event_id,
        "idempotency_key": f"{task_id}:evidence-gate:{expected_version + 1}",
        "task_id": task_id,
        "context_id": state.get("context_id"),
        "event_type": event_type,
        "actor": actor,
        "occurred_at": now,
        "causation_id": previous_event_id,
        "correlation_id": state.get("context_id"),
        "from_state": state["state"],
        "to_state": target_state,
        "reason": gate_report["summary"],
        "refs": [
            "state.json",
            "artifact-manifest.json",
            "evidence-manifest.json",
            f"evidence/{report_name}",
        ],
    }
    _append_event(event_path, event)

    updated_state = dict(state)
    updated_state["state"] = target_state
    updated_state["state_version"] = expected_version + 1
    updated_state["owner"] = None
    updated_state["lease"] = None
    updated_state["updated_at"] = now
    updated_state["artifact_refs"] = _append_unique(state.get("artifact_refs", []), artifact_record["artifact_id"])
    updated_state["evidence_refs"] = _append_unique(state.get("evidence_refs", []), evidence_record["evidence_id"])
    if target_state == "completed":
        updated_state["next_action"] = "Completed by EvidenceGate verifier approval."
        updated_state["pause_reason"] = None
        updated_state["blockers"] = []
    else:
        updated_state["next_action"] = "Address EvidenceGate verifier findings and return to review."
        updated_state["blockers"] = _request_change_blockers(criteria, assessments)
    _write_json(state_path, updated_state)

    return EvidenceGateResult(
        task_id=task_id,
        decision=report_decision,
        state=target_state,
        state_version=expected_version + 1,
        report_artifact_id=artifact_record["artifact_id"],
        report_evidence_id=evidence_record["evidence_id"],
        event_id=event_id,
        report_path=str(report_file),
    )


def inspect_task(task: str | Path, *, work_root: str | Path = "work") -> dict[str, Any]:
    task_dir = _resolve_task_dir(task, work_root)
    result: dict[str, Any] = {"task_id": task_dir.name, "task_dir": str(task_dir.resolve())}
    for name in ["state.json", "artifact-manifest.json", "evidence-manifest.json"]:
        path = task_dir / name
        if path.exists():
            result[name] = _load_json(path)
    task_path = task_dir / "task.md"
    if task_path.exists():
        result["acceptance_criteria"] = [
            {"index": criterion.index, "text": criterion.text}
            for criterion in parse_acceptance_criteria(task_path)
        ]
    event_path = task_dir / "events.jsonl"
    if event_path.exists():
        result["events"] = _load_events(event_path)
    return result


def resolve_review_requirements(
    task: str | Path,
    *,
    work_root: str | Path = "work",
    profile_refs: Iterable[str] = (),
    report_paths: Iterable[str | Path] = (),
) -> EvidenceGateReviewRequirementReport:
    task_dir = _resolve_task_dir(task, work_root)
    task_id = task_dir.name
    task_path = task_dir / "task.md"
    effective_profile_refs = {str(ref) for ref in profile_refs}
    if not effective_profile_refs:
        artifact_manifest_path = task_dir / "artifact-manifest.json"
        if artifact_manifest_path.exists():
            artifact_manifest = _load_manifest(artifact_manifest_path, "artifacts", task_id)
            effective_profile_refs = _associated_goal_profile_refs(task_dir, artifact_manifest)

    declares_code_change = _task_declares_code_change(task_path)
    missing_inputs: list[str] = []
    if declares_code_change and "" in effective_profile_refs:
        missing_inputs.append("goal_awkp_association.profileRef")

    requires_semantic_reviews = (
        declares_code_change
        and DEVELOPMENT_BOUNDED_PROFILE_REF in effective_profile_refs
    )
    if requires_semantic_reviews:
        for report_path in report_paths:
            path = Path(report_path)
            report = _load_json(path)
            decision = str(report.get("decision") or "").strip()
            if decision != "approve":
                continue
            semantic_reviews = report.get("semantic_reviews")
            if not isinstance(semantic_reviews, list) or not semantic_reviews:
                missing_inputs.append(f"{path}#semantic_reviews")

    return EvidenceGateReviewRequirementReport(
        task_id=task_id,
        requires_semantic_reviews=requires_semantic_reviews,
        profile_refs=tuple(sorted(effective_profile_refs)),
        missing_inputs=tuple(missing_inputs),
    )


def parse_acceptance_criteria(path: Path) -> list[AcceptanceCriterion]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    in_section = False
    raw_items: list[str] = []
    current: list[str] = []
    checkbox = re.compile(r"^\s*-\s+\[[ xX]\]\s+(.*)$")
    for line in lines:
        if re.match(r"^#\s+Acceptance criteria\s*$", line, re.IGNORECASE):
            in_section = True
            continue
        if in_section and line.startswith("# "):
            break
        if not in_section:
            continue
        match = checkbox.match(line)
        if match:
            if current:
                raw_items.append(_normalize(" ".join(current)))
            current = [match.group(1).strip()]
            continue
        if current and line.strip():
            current.append(line.strip())
    if current:
        raw_items.append(_normalize(" ".join(current)))
    return [AcceptanceCriterion(index=i, text=text) for i, text in enumerate(raw_items, 1)]


def _resolve_task_dir(task: str | Path, work_root: str | Path) -> Path:
    task_path = Path(task)
    if task_path.exists():
        return task_path.resolve()
    root = Path(work_root)
    candidate = root / "tasks" / str(task)
    if candidate.exists():
        return candidate.resolve()
    raise EvidenceGateError(f"task directory not found: {task}")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise EvidenceGateError(f"required JSON file is missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise EvidenceGateError(f"JSON document must be an object: {path}")
    return data


def _write_json(path: Path, data: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _json_bytes(data: dict[str, Any]) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _load_manifest(path: Path, key: str, task_id: str) -> dict[str, Any]:
    manifest = _load_json(path)
    if manifest.get("schema_version") != "awkp/0.1":
        raise EvidenceGateError(f"{path.name} schema_version must be awkp/0.1")
    if manifest.get("task_id") != task_id:
        raise EvidenceGateError(f"{path.name} task_id must be {task_id}")
    if not isinstance(manifest.get(key), list):
        raise EvidenceGateError(f"{path.name} {key} must be an array")
    return manifest


def _validate_manifest_hashes(task_dir: Path, manifest: dict[str, Any], key: str) -> None:
    for index, record in enumerate(manifest.get(key, [])):
        uri = str(record.get("uri") or "")
        sha = str(record.get("sha256") or "")
        if not re.fullmatch(r"[a-f0-9]{64}", sha):
            raise EvidenceGateError(f"{key}[{index}] has invalid sha256")
        if uri.startswith("local://"):
            path = _local_uri_path(task_dir, uri)
            if not path.exists() or not path.is_file():
                raise EvidenceGateError(f"{key}[{index}] local uri is missing: {uri}")
            payload = path.read_bytes()
        elif uri.startswith("git:"):
            payload = _git_uri_bytes(task_dir, uri)
        else:
            continue
        actual = hashlib.sha256(payload).hexdigest()
        if actual != sha:
            raise EvidenceGateError(f"{key}[{index}] hash mismatch for {uri}")


def _local_uri_path(task_dir: Path, uri: str) -> Path:
    relative = _local_uri_relative(uri)
    task_root = task_dir.resolve()
    repo_root = _repository_root_for_task(task_root)
    if relative.parts and relative.parts[0] not in TASK_LOCAL_URI_PREFIXES and repo_root is not None:
        repo_path = (repo_root / relative).resolve()
        _ensure_inside(repo_path, repo_root, uri, "repository root")
        if repo_path.exists():
            return repo_path
    task_path = (task_root / relative).resolve()
    _ensure_inside(task_path, task_root, uri, "task directory")
    return task_path


def _local_uri_relative(uri: str) -> Path:
    raw = uri.removeprefix("local://").replace("\\", "/").strip()
    parsed = PurePosixPath(raw)
    parts = [part for part in parsed.parts if part]
    if (
        not raw
        or raw.startswith("/")
        or re.match(r"^[A-Za-z]:", raw)
        or "." in parts
        or ".." in parts
    ):
        raise EvidenceGateError(f"local uri must be a clean relative path: {uri}")
    return Path(*parts)


def _git_uri_bytes(task_dir: Path, uri: str) -> bytes:
    repo_root = _repository_root_for_task(task_dir.resolve())
    if repo_root is None:
        raise EvidenceGateError(f"git uri cannot be resolved without repository root: {uri}")
    commit, relative = _git_uri_parts(uri)
    store = _GitObjectStore(_git_dir_for_repo(repo_root))
    object_type, commit_payload = store.read(commit)
    if object_type != "commit":
        raise EvidenceGateError(f"git uri commit object is not a commit: {uri}")
    tree_id = _commit_tree_id(commit_payload, uri)
    return _tree_blob_bytes(store, tree_id, relative, uri)


def _git_uri_parts(uri: str) -> tuple[str, PurePosixPath]:
    raw = uri.removeprefix("git:")
    commit, separator, path = raw.partition(":")
    if not separator or not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise EvidenceGateError(f"git uri must be git:<40hex-commit>:<relative-path>: {uri}")
    normalized = path.replace("\\", "/").strip()
    parsed = PurePosixPath(normalized)
    parts = [part for part in parsed.parts if part]
    if (
        not normalized
        or normalized.startswith("/")
        or re.match(r"^[A-Za-z]:", normalized)
        or "." in parts
        or ".." in parts
    ):
        raise EvidenceGateError(f"git uri must use a clean relative path: {uri}")
    return commit, PurePosixPath(*parts)


def _git_dir_for_repo(repo_root: Path) -> Path:
    marker = repo_root / ".git"
    if marker.is_dir():
        return marker
    if marker.is_file():
        text = marker.read_text(encoding="utf-8").strip()
        prefix = "gitdir:"
        if text.startswith(prefix):
            raw = text.removeprefix(prefix).strip()
            path = Path(raw)
            return path if path.is_absolute() else (repo_root / path).resolve()
    raise EvidenceGateError(f"repository root has no usable .git directory: {repo_root}")


class _GitObjectStore:
    def __init__(self, git_dir: Path) -> None:
        self.git_dir = git_dir
        self._cache: dict[str, tuple[str, bytes]] = {}
        self._pack_cache: dict[Path, bytes] = {}

    def read(self, object_id: str) -> tuple[str, bytes]:
        if not re.fullmatch(r"[a-f0-9]{40}", object_id):
            raise EvidenceGateError(f"invalid git object id: {object_id}")
        if object_id in self._cache:
            return self._cache[object_id]
        obj = self._read_loose(object_id)
        if obj is None:
            obj = self._read_packed(object_id)
        if obj is None:
            raise EvidenceGateError(f"git object is missing: {object_id}")
        self._cache[object_id] = obj
        return obj

    def _read_loose(self, object_id: str) -> tuple[str, bytes] | None:
        path = self.git_dir / "objects" / object_id[:2] / object_id[2:]
        if not path.exists():
            return None
        try:
            raw = zlib.decompress(path.read_bytes())
        except zlib.error as exc:
            raise EvidenceGateError(f"git loose object is corrupt: {object_id}") from exc
        return _split_git_object(raw, object_id)

    def _read_packed(self, object_id: str) -> tuple[str, bytes] | None:
        pack_dir = self.git_dir / "objects" / "pack"
        for index_path in sorted(pack_dir.glob("*.idx")):
            offset = _pack_index_offset(index_path, object_id)
            if offset is None:
                continue
            pack_path = index_path.with_suffix(".pack")
            return self._read_pack_object(pack_path, offset)
        return None

    def _read_pack_object(self, pack_path: Path, offset: int) -> tuple[str, bytes]:
        pack = self._pack_bytes(pack_path)
        if offset < 12 or offset >= len(pack):
            raise EvidenceGateError(f"git pack object offset is invalid: {pack_path}")
        object_type_code, _size, position = _pack_object_header(pack, offset)
        if object_type_code in PACK_OBJECT_TYPES:
            return PACK_OBJECT_TYPES[object_type_code], _pack_decompress(pack, position)
        if object_type_code == 6:
            base_offset, position = _pack_ofs_delta_base(pack, position, offset)
            base_type, base_payload = self._read_pack_object(pack_path, base_offset)
            delta = _pack_decompress(pack, position)
            return base_type, _apply_git_delta(base_payload, delta)
        if object_type_code == 7:
            if position + 20 > len(pack):
                raise EvidenceGateError(f"git pack ref-delta is truncated: {pack_path}")
            base_id = pack[position : position + 20].hex()
            base_type, base_payload = self.read(base_id)
            delta = _pack_decompress(pack, position + 20)
            return base_type, _apply_git_delta(base_payload, delta)
        raise EvidenceGateError(f"unsupported git pack object type: {object_type_code}")

    def _pack_bytes(self, pack_path: Path) -> bytes:
        if pack_path not in self._pack_cache:
            data = pack_path.read_bytes()
            if not data.startswith(b"PACK"):
                raise EvidenceGateError(f"git pack file is invalid: {pack_path}")
            self._pack_cache[pack_path] = data
        return self._pack_cache[pack_path]


def _split_git_object(raw: bytes, object_id: str) -> tuple[str, bytes]:
    header, separator, payload = raw.partition(b"\0")
    if not separator:
        raise EvidenceGateError(f"git object has invalid header: {object_id}")
    parts = header.split(b" ", 1)
    if len(parts) != 2:
        raise EvidenceGateError(f"git object has invalid header: {object_id}")
    object_type = parts[0].decode("ascii", errors="strict")
    try:
        declared_size = int(parts[1])
    except ValueError as exc:
        raise EvidenceGateError(f"git object has invalid size: {object_id}") from exc
    if declared_size != len(payload):
        raise EvidenceGateError(f"git object size mismatch: {object_id}")
    return object_type, payload


def _pack_index_offset(index_path: Path, object_id: str) -> int | None:
    data = index_path.read_bytes()
    if not data.startswith(b"\xfftOc"):
        raise EvidenceGateError(f"unsupported git pack index format: {index_path}")
    version = struct.unpack(">I", data[4:8])[0]
    if version != 2:
        raise EvidenceGateError(f"unsupported git pack index version: {version}")
    fanout_offset = 8
    count = struct.unpack(">I", data[fanout_offset + 255 * 4 : fanout_offset + 256 * 4])[0]
    names_offset = fanout_offset + 256 * 4
    object_bytes = bytes.fromhex(object_id)
    low, high = 0, count
    while low < high:
        middle = (low + high) // 2
        candidate = data[names_offset + middle * 20 : names_offset + (middle + 1) * 20]
        if candidate < object_bytes:
            low = middle + 1
        else:
            high = middle
    if low >= count:
        return None
    candidate = data[names_offset + low * 20 : names_offset + (low + 1) * 20]
    if candidate != object_bytes:
        return None
    crc_offset = names_offset + count * 20
    offsets_offset = crc_offset + count * 4
    offset_value = struct.unpack(">I", data[offsets_offset + low * 4 : offsets_offset + (low + 1) * 4])[0]
    if offset_value & 0x80000000:
        large_index = offset_value & 0x7FFFFFFF
        large_offset = offsets_offset + count * 4 + large_index * 8
        return struct.unpack(">Q", data[large_offset : large_offset + 8])[0]
    return offset_value


def _pack_object_header(pack: bytes, offset: int) -> tuple[int, int, int]:
    position = offset
    first = pack[position]
    position += 1
    object_type = (first >> 4) & 0x07
    size = first & 0x0F
    shift = 4
    byte = first
    while byte & 0x80:
        byte = pack[position]
        position += 1
        size |= (byte & 0x7F) << shift
        shift += 7
    return object_type, size, position


def _pack_decompress(pack: bytes, position: int) -> bytes:
    try:
        decompressor = zlib.decompressobj()
        payload = decompressor.decompress(pack[position:])
    except zlib.error as exc:
        raise EvidenceGateError("git pack object is corrupt") from exc
    if not decompressor.eof:
        raise EvidenceGateError("git pack object is truncated")
    return payload


def _pack_ofs_delta_base(pack: bytes, position: int, object_offset: int) -> tuple[int, int]:
    byte = pack[position]
    position += 1
    distance = byte & 0x7F
    while byte & 0x80:
        byte = pack[position]
        position += 1
        distance = ((distance + 1) << 7) | (byte & 0x7F)
    return object_offset - distance, position


def _apply_git_delta(base: bytes, delta: bytes) -> bytes:
    position, source_size = _delta_varint(delta, 0)
    position, target_size = _delta_varint(delta, position)
    if source_size != len(base):
        raise EvidenceGateError("git delta source size mismatch")
    output = bytearray()
    while position < len(delta):
        command = delta[position]
        position += 1
        if command & 0x80:
            copy_offset = 0
            copy_size = 0
            for bit_index, shift in enumerate((0, 8, 16, 24)):
                if command & (1 << bit_index):
                    copy_offset |= delta[position] << shift
                    position += 1
            for bit_index, shift in enumerate((0, 8, 16)):
                if command & (1 << (4 + bit_index)):
                    copy_size |= delta[position] << shift
                    position += 1
            if copy_size == 0:
                copy_size = 0x10000
            output.extend(base[copy_offset : copy_offset + copy_size])
        elif command:
            output.extend(delta[position : position + command])
            position += command
        else:
            raise EvidenceGateError("git delta contains invalid copy command")
    if len(output) != target_size:
        raise EvidenceGateError("git delta target size mismatch")
    return bytes(output)


def _delta_varint(delta: bytes, position: int) -> tuple[int, int]:
    shift = 0
    value = 0
    while True:
        if position >= len(delta):
            raise EvidenceGateError("git delta varint is truncated")
        byte = delta[position]
        position += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return position, value
        shift += 7


def _commit_tree_id(payload: bytes, uri: str) -> str:
    first_line = payload.split(b"\n", 1)[0]
    prefix = b"tree "
    if not first_line.startswith(prefix):
        raise EvidenceGateError(f"git uri commit has no tree: {uri}")
    tree_id = first_line.removeprefix(prefix).decode("ascii", errors="strict")
    if not re.fullmatch(r"[a-f0-9]{40}", tree_id):
        raise EvidenceGateError(f"git uri commit tree is invalid: {uri}")
    return tree_id


def _tree_blob_bytes(store: _GitObjectStore, tree_id: str, relative: PurePosixPath, uri: str) -> bytes:
    current_tree = tree_id
    parts = [part.encode("utf-8") for part in relative.parts]
    for index, wanted in enumerate(parts):
        object_type, tree_payload = store.read(current_tree)
        if object_type != "tree":
            raise EvidenceGateError(f"git uri path traverses non-tree object: {uri}")
        found_id = _tree_entry_id(tree_payload, wanted, uri)
        if index == len(parts) - 1:
            target_type, target_payload = store.read(found_id)
            if target_type != "blob":
                raise EvidenceGateError(f"git uri path is not a blob: {uri}")
            return target_payload
        current_tree = found_id
    raise EvidenceGateError(f"git uri path is missing: {uri}")


def _tree_entry_id(tree_payload: bytes, wanted: bytes, uri: str) -> str:
    position = 0
    while position < len(tree_payload):
        try:
            space = tree_payload.index(b" ", position)
            nul = tree_payload.index(b"\0", space + 1)
        except ValueError as exc:
            raise EvidenceGateError(f"git tree object is corrupt: {uri}") from exc
        name = tree_payload[space + 1 : nul]
        object_id = tree_payload[nul + 1 : nul + 21]
        if len(object_id) != 20:
            raise EvidenceGateError(f"git tree entry is truncated: {uri}")
        if name == wanted:
            return object_id.hex()
        position = nul + 21
    raise EvidenceGateError(f"git uri path is missing: {uri}")


def _repository_root_for_task(task_dir: Path) -> Path | None:
    if task_dir.parent.name == "tasks":
        return task_dir.parent.parent.parent.resolve()
    for candidate in (task_dir, *task_dir.parents):
        if (candidate / ".git").exists() and (candidate / "work").exists():
            return candidate.resolve()
    return None


def _ensure_inside(path: Path, root: Path, uri: str, root_name: str) -> None:
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise EvidenceGateError(f"local uri escapes {root_name}: {uri}") from exc


def _producer_identities(
    artifact_manifest: dict[str, Any],
    evidence_manifest: dict[str, Any],
    event_path: Path,
) -> set[str]:
    identities: set[str] = set()
    for record in artifact_manifest.get("artifacts", []):
        if record.get("kind") == "evidence_gate_report":
            continue
        created_by = record.get("created_by")
        if created_by:
            identities.add(str(created_by))
    for record in evidence_manifest.get("evidence", []):
        if record.get("kind") == "evidence_gate_report":
            continue
        created_by = record.get("created_by")
        if created_by:
            identities.add(str(created_by))
    for event in _load_events(event_path):
        if event.get("event_type") in {"lease_acquired", "artifact_published"} and event.get("actor"):
            identities.add(str(event["actor"]))
    return identities


def _load_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            event = json.loads(line)
            if not isinstance(event, dict):
                raise EvidenceGateError(f"event line must be an object in {path}")
            events.append(event)
    return events


def _map_criteria(
    criteria: list[AcceptanceCriterion],
    report: dict[str, Any],
    evidence_by_id: dict[str, dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    items = report.get("criteria")
    if not isinstance(items, list):
        raise EvidenceGateError("report criteria must be an array")
    by_text = {_normalize(criterion.text): criterion.index for criterion in criteria}
    by_index = {criterion.index for criterion in criteria}
    mapped: dict[int, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            raise EvidenceGateError("report criteria entries must be objects")
        index = item.get("criterion_index")
        if index is None and item.get("criterion") is not None:
            index = by_text.get(_normalize(str(item["criterion"])))
        if not isinstance(index, int) or index not in by_index:
            raise EvidenceGateError(f"report criterion does not match task criteria: {item!r}")
        if index in mapped:
            raise EvidenceGateError(f"duplicate assessment for criterion {index}")
        for ref in _refs(item):
            if ref not in evidence_by_id:
                raise EvidenceGateError(f"criterion {index} references unknown evidence {ref}")
        mapped[index] = item
    return mapped


def _validate_command_results(
    report: dict[str, Any],
    decision: str,
    kernel_evidence: KernelEvidenceIndex,
) -> None:
    commands = report.get("commands", [])
    if commands is None:
        return
    if not isinstance(commands, list):
        raise EvidenceGateError("report commands must be an array")
    for index, command in enumerate(commands):
        if not isinstance(command, dict):
            raise EvidenceGateError(f"command[{index}] must be an object")
        status = str(command.get("status") or "").strip().lower()
        if decision == "approve" and status not in PASSED_STATUSES:
            raise EvidenceGateError(f"command[{index}] is not passed")
        if decision == "approve" and status in PASSED_STATUSES:
            refs = _evidence_refs(command)
            if not refs:
                raise EvidenceGateError(
                    f"command[{index}] passed without kernel EvidenceV2 evidence_refs"
                )
            for ref in refs:
                _validate_kernel_command_evidence(ref, kernel_evidence, f"command[{index}]")
        if command.get("changed_files_sha256") and command.get("verified_changed_files_sha256"):
            if command["changed_files_sha256"] != command["verified_changed_files_sha256"]:
                raise EvidenceGateError(f"command[{index}] is stale for changed files")


def _requires_semantic_code_review(
    *,
    task_dir: Path,
    task_path: Path,
    artifact_manifest: dict[str, Any],
) -> bool:
    if not _task_declares_code_change(task_path):
        return False
    profile_refs = _associated_goal_profile_refs(task_dir, artifact_manifest)
    if "" in profile_refs:
        raise EvidenceGateError("code-change Goal/AWKP association missing profileRef")
    return DEVELOPMENT_BOUNDED_PROFILE_REF in profile_refs


def _task_declares_code_change(task_path: Path) -> bool:
    return "ahra/artifact/code-change/0.1" in task_path.read_text(encoding="utf-8")


def _associated_goal_profile_refs(
    task_dir: Path,
    artifact_manifest: dict[str, Any],
) -> set[str]:
    profile_refs: set[str] = set()
    for record in artifact_manifest.get("artifacts", []):
        if not isinstance(record, dict):
            continue
        uri = str(record.get("uri") or "")
        if not uri.startswith("local://"):
            continue
        try:
            path = _local_uri_path(task_dir, uri)
            data = json.loads(path.read_text(encoding="utf-8"))
        except (EvidenceGateError, OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        if data.get("schema_version") != "ahra/goal-awkp-association/0.1":
            continue
        profile_refs.add(str(data.get("profileRef") or ""))
    return profile_refs


def _validate_semantic_code_reviews(
    *,
    report: dict[str, Any],
    criteria: list[AcceptanceCriterion],
    assessments: dict[int, dict[str, Any]],
    evidence_by_id: dict[str, dict[str, Any]],
    kernel_evidence: KernelEvidenceIndex,
    producer_identities: set[str],
) -> None:
    reviews = report.get("semantic_reviews")
    if not isinstance(reviews, list) or not reviews:
        raise EvidenceGateError("development-bounded code-change requires semantic_reviews")
    required_indices = {criterion.index for criterion in criteria}
    covered_indices: set[int] = set()
    for index, review in enumerate(reviews):
        if not isinstance(review, dict):
            raise EvidenceGateError(f"semantic_review[{index}] must be an object")
        status = str(review.get("status") or "").strip().lower()
        if status not in PASSED_STATUSES:
            raise EvidenceGateError(f"semantic_review[{index}] is not passed")
        changed_files = _changed_files(review.get("changed_files"), f"semantic_review[{index}]")
        declared_digest = str(review.get("changed_files_sha256") or "")
        verified_digest = str(review.get("verified_changed_files_sha256") or "")
        expected_digest = _changed_files_digest(changed_files)
        if (
            not declared_digest
            or not verified_digest
            or declared_digest != verified_digest
            or declared_digest != expected_digest
        ):
            raise EvidenceGateError(f"semantic_review[{index}] stale changed files")
        criterion_indices = _semantic_review_criterion_indices(
            review,
            required_indices,
            f"semantic_review[{index}]",
        )
        refs = _evidence_refs(review)
        if not refs:
            raise EvidenceGateError(f"semantic_review[{index}] has no evidence_refs")
        declared_reviewer = _declared_semantic_reviewer(review)
        if declared_reviewer and declared_reviewer in producer_identities:
            raise EvidenceGateError(f"semantic_review[{index}] produced by producer identity")
        for evidence_ref in refs:
            if evidence_ref not in evidence_by_id:
                raise EvidenceGateError(
                    f"semantic_review[{index}] references unknown evidence {evidence_ref}"
                )
            evidence, gate_run = _validate_kernel_command_evidence(
                evidence_ref,
                kernel_evidence,
                f"semantic_review[{index}]",
            )
            _validate_semantic_review_lineage(
                evidence_ref,
                evidence,
                gate_run,
                producer_identities,
                declared_reviewer,
                f"semantic_review[{index}]",
            )
            for criterion_index in criterion_indices:
                assessment = assessments.get(criterion_index)
                if assessment is None or evidence_ref not in _refs(assessment):
                    raise EvidenceGateError(
                        f"semantic_review[{index}] evidence {evidence_ref} not mapped "
                        f"to criterion {criterion_index}"
                    )
        covered_indices.update(criterion_indices)
    missing = sorted(required_indices - covered_indices)
    if missing:
        raise EvidenceGateError(f"semantic_reviews missing criteria {missing}")


def _semantic_review_criterion_indices(
    review: dict[str, Any],
    allowed_indices: set[int],
    ref: str,
) -> set[int]:
    raw = review.get("criterion_indices")
    if not isinstance(raw, list) or not raw:
        raise EvidenceGateError(f"{ref} criterion_indices must be non-empty array")
    result: set[int] = set()
    for item in raw:
        if not isinstance(item, int):
            raise EvidenceGateError(f"{ref} criterion_indices must contain integers")
        if item not in allowed_indices:
            raise EvidenceGateError(f"{ref} references unknown criterion {item}")
        result.add(item)
    return result


def _changed_files(value: Any, ref: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise EvidenceGateError(f"{ref} changed_files must be non-empty array")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise EvidenceGateError(f"{ref} changed_files must contain strings")
        normalized = item.replace("\\", "/").strip()
        parts = [part for part in normalized.split("/") if part]
        if (
            not normalized
            or normalized.startswith("/")
            or re.match(r"^[A-Za-z]:", normalized)
            or "." in parts
            or ".." in parts
        ):
            raise EvidenceGateError(f"{ref} changed_files must be relative clean paths")
        result.append("/".join(parts))
    return result


def _changed_files_digest(changed_files: list[str]) -> str:
    return "sha256:" + hashlib.sha256(
        _canonical_json(sorted(changed_files)).encode("utf-8")
    ).hexdigest()


def _declared_semantic_reviewer(review: dict[str, Any]) -> str | None:
    for key in ("reviewer", "reviewer_identity", "verifier", "verifier_identity"):
        value = review.get(key)
        if value:
            return str(value)
    return None


def _validate_semantic_review_lineage(
    evidence_ref: str,
    evidence: dict[str, Any],
    gate_run: dict[str, Any],
    producer_identities: set[str],
    declared_reviewer: str | None,
    referrer: str,
) -> None:
    gate_run_id = _metadata_ref(gate_run, "gateRunId")
    gate_spec = _object(gate_run.get("spec"), f"{gate_run_id or 'GateRun'}.spec")
    command = _strings(gate_spec.get("command"), f"{gate_run_id}.spec.command")
    if len(command) < 2 or command[0] != "semantic_review":
        raise EvidenceGateError(f"{referrer} GateRun is not semantic_review")
    evidence_spec = _object(evidence.get("spec"), f"{evidence_ref}.spec")
    refs = _strings(evidence_spec.get("refs"), f"{evidence_ref}.spec.refs")
    reviewer_refs = sorted(ref.removeprefix("verifier:") for ref in refs if ref.startswith("verifier:"))
    if not reviewer_refs:
        raise EvidenceGateError(f"{referrer} semantic review missing verifier identity")
    if declared_reviewer and declared_reviewer not in reviewer_refs:
        raise EvidenceGateError(f"{referrer} verifier identity mismatch")
    if any(reviewer in producer_identities for reviewer in reviewer_refs):
        raise EvidenceGateError(f"{referrer} produced by producer identity")


def _command_backed_criteria(report: dict[str, Any]) -> set[int]:
    result: set[int] = set()
    criteria = report.get("criteria", [])
    if isinstance(criteria, list):
        for item in criteria:
            if not isinstance(item, dict):
                continue
            if _has_command_marker(item):
                index = item.get("criterion_index")
                if isinstance(index, int):
                    result.add(index)
    commands = report.get("commands", [])
    if isinstance(commands, list):
        for command in commands:
            if not isinstance(command, dict):
                continue
            index = command.get("criterion_index")
            if isinstance(index, int):
                result.add(index)
            indices = command.get("criterion_indices")
            if isinstance(indices, list):
                result.update(index for index in indices if isinstance(index, int))
    return result


def _has_command_marker(item: dict[str, Any]) -> bool:
    for key in ("command", "commands", "command_ref", "command_refs", "command_evidence_refs"):
        value = item.get(key)
        if value:
            return True
    return False


def _validate_command_backed_criterion(
    criterion_index: int,
    refs: list[str],
    kernel_evidence: KernelEvidenceIndex,
) -> None:
    failures: list[str] = []
    for ref in refs:
        try:
            _validate_kernel_command_evidence(ref, kernel_evidence, f"criterion {criterion_index}")
            return
        except EvidenceGateError as exc:
            failures.append(str(exc))
    reason = "; ".join(failures) if failures else "no evidence_refs"
    raise EvidenceGateError(
        f"criterion {criterion_index} is command-backed but has no valid kernel EvidenceV2 gate-run lineage: {reason}"
    )


def _status(item: dict[str, Any]) -> str:
    return str(item.get("status") or "").strip().lower()


def _refs(item: dict[str, Any]) -> list[str]:
    return _evidence_refs(item)


def _evidence_refs(item: dict[str, Any]) -> list[str]:
    refs = item.get("evidence_refs", [])
    if refs is None:
        return []
    if not isinstance(refs, list) or not all(isinstance(ref, str) for ref in refs):
        raise EvidenceGateError("evidence_refs must be an array of strings")
    return refs


def _kernel_evidence_index(
    task_dir: Path,
    artifact_manifest: dict[str, Any],
    evidence_manifest: dict[str, Any],
) -> KernelEvidenceIndex:
    evidence: dict[str, dict[str, Any]] = {}
    gate_runs: dict[str, dict[str, Any]] = {}
    for record in (*artifact_manifest.get("artifacts", []), *evidence_manifest.get("evidence", [])):
        if not isinstance(record, dict):
            continue
        uri = str(record.get("uri") or "")
        if not uri.startswith("local://"):
            continue
        path = _local_uri_path(task_dir, uri)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or data.get("apiVersion") != "ahra.dev/v1alpha1":
            continue
        if data.get("kind") == "Evidence":
            evidence_id = _metadata_ref(data, "evidenceId")
            if evidence_id:
                evidence[evidence_id] = data
        elif data.get("kind") == "GateRun":
            gate_run_id = _metadata_ref(data, "gateRunId")
            if gate_run_id:
                gate_runs[gate_run_id] = data
    return KernelEvidenceIndex(evidence=evidence, gate_runs=gate_runs)


def _metadata_ref(data: dict[str, Any], key: str) -> str | None:
    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        return None
    value = metadata.get(key)
    return str(value) if value else None


def _validate_kernel_command_evidence(
    evidence_ref: str,
    kernel_evidence: KernelEvidenceIndex,
    referrer: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    evidence = kernel_evidence.evidence.get(evidence_ref)
    if evidence is None:
        raise EvidenceGateError(f"{referrer} references {evidence_ref} without kernel EvidenceV2")
    spec = _object(evidence.get("spec"), f"{evidence_ref}.spec")
    if str(spec.get("result") or "").lower() != "passed":
        raise EvidenceGateError(f"{referrer} references non-passed kernel EvidenceV2 {evidence_ref}")
    validity = _object(spec.get("validity"), f"{evidence_ref}.spec.validity")
    if validity.get("state") != "current":
        raise EvidenceGateError(f"{referrer} references stale kernel EvidenceV2 {evidence_ref}")
    stored_fingerprint = str(spec.get("fingerprint") or "")
    if stored_fingerprint != _evidence_fingerprint(evidence):
        raise EvidenceGateError(f"{referrer} references kernel EvidenceV2 {evidence_ref} with fingerprint mismatch")
    gate_run_id = str(spec.get("gateRunId") or "")
    if not gate_run_id:
        raise EvidenceGateError(f"{referrer} references kernel EvidenceV2 {evidence_ref} without gateRunId")
    gate_run = kernel_evidence.gate_runs.get(gate_run_id)
    if gate_run is None:
        raise EvidenceGateError(f"{referrer} references kernel EvidenceV2 {evidence_ref} without valid gate-run lineage")
    _validate_gate_run_lineage(evidence_ref, evidence, gate_run, referrer)
    return evidence, gate_run


def _validate_gate_run_lineage(
    evidence_ref: str,
    evidence: dict[str, Any],
    gate_run: dict[str, Any],
    referrer: str,
) -> None:
    evidence_spec = _object(evidence.get("spec"), f"{evidence_ref}.spec")
    gate_run_id = _metadata_ref(gate_run, "gateRunId")
    gate_spec = _object(gate_run.get("spec"), f"{gate_run_id or 'GateRun'}.spec")
    if gate_spec.get("evidenceRef") != evidence_ref:
        raise EvidenceGateError(f"{referrer} gate-run lineage does not point back to {evidence_ref}")
    for key in ("gateRef", "gateDefinitionDigest", "result"):
        if gate_spec.get(key) != evidence_spec.get(key):
            raise EvidenceGateError(f"{referrer} gate-run lineage mismatches {key} for {evidence_ref}")
    for key in ("claimRefs", "subjects", "dependencies", "environment"):
        if _canonical_json(gate_spec.get(key)) != _canonical_json(evidence_spec.get(key)):
            raise EvidenceGateError(f"{referrer} gate-run lineage mismatches {key} for {evidence_ref}")
    validity = _object(gate_spec.get("validity"), f"{gate_run_id}.spec.validity")
    if validity.get("state") != "current":
        raise EvidenceGateError(f"{referrer} references stale GateRun {gate_run_id}")
    command = gate_spec.get("command")
    if not isinstance(command, list) or not command or not all(isinstance(item, str) for item in command):
        raise EvidenceGateError(f"{referrer} GateRun {gate_run_id} is not command-backed")
    if gate_spec.get("fingerprint") != _gate_run_fingerprint(gate_run):
        raise EvidenceGateError(f"{referrer} GateRun {gate_run_id} has fingerprint mismatch")


def _evidence_fingerprint(evidence: dict[str, Any]) -> str:
    spec = _object(evidence.get("spec"), "Evidence.spec")
    return _canonical_fingerprint(
        {
            "claimRefs": sorted(_strings(spec.get("claimRefs"), "Evidence.spec.claimRefs")),
            "dependencies": _digest_refs(spec.get("dependencies"), "Evidence.spec.dependencies"),
            "environment": _environment_fingerprint(spec.get("environment")),
            "gateDefinitionDigest": str(spec.get("gateDefinitionDigest") or ""),
            "gateRef": str(spec.get("gateRef") or ""),
            "subjects": _digest_refs(spec.get("subjects"), "Evidence.spec.subjects"),
        }
    )


def _gate_run_fingerprint(gate_run: dict[str, Any]) -> str:
    spec = _object(gate_run.get("spec"), "GateRun.spec")
    return _canonical_fingerprint(
        {
            "claimRefs": sorted(_strings(spec.get("claimRefs"), "GateRun.spec.claimRefs")),
            "command": _strings(spec.get("command"), "GateRun.spec.command"),
            "dependencies": _digest_refs(spec.get("dependencies"), "GateRun.spec.dependencies"),
            "environment": _environment_fingerprint(spec.get("environment")),
            "gateDefinitionDigest": str(spec.get("gateDefinitionDigest") or ""),
            "gateRef": str(spec.get("gateRef") or ""),
            "subjects": _digest_refs(spec.get("subjects"), "GateRun.spec.subjects"),
        }
    )


def _canonical_fingerprint(payload: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _object(value: Any, ref: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvidenceGateError(f"{ref} must be an object")
    return value


def _strings(value: Any, ref: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise EvidenceGateError(f"{ref} must be an array of strings")
    return list(value)


def _digest_refs(value: Any, ref: str) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise EvidenceGateError(f"{ref} must be an array")
    result: list[dict[str, str]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise EvidenceGateError(f"{ref}[{index}] must be an object")
        digest_ref = item.get("ref")
        digest = item.get("digest")
        if not isinstance(digest_ref, str) or not isinstance(digest, str):
            raise EvidenceGateError(f"{ref}[{index}] must include ref and digest strings")
        result.append({"ref": digest_ref, "digest": digest})
    return sorted(result, key=lambda item: item["ref"])


def _environment_fingerprint(value: Any) -> dict[str, str | None]:
    environment = _object(value, "environment")
    return {
        "policyDigest": _optional_string(environment.get("policyDigest")),
        "relevantEnvironmentDigest": _optional_string(environment.get("relevantEnvironmentDigest")),
        "runtimeProfileDigest": _optional_string(environment.get("runtimeProfileDigest")),
        "testDefinitionDigest": _optional_string(environment.get("testDefinitionDigest")),
        "verifierReleaseDigest": _optional_string(environment.get("verifierReleaseDigest")),
    }


def _optional_string(value: Any) -> str | None:
    return str(value) if value is not None else None


def _build_gate_report(
    *,
    task_id: str,
    actor: str,
    decision: str,
    target_state: str,
    criteria: list[AcceptanceCriterion],
    input_report: dict[str, Any],
    now: str,
) -> dict[str, Any]:
    summary = str(input_report.get("summary") or f"EvidenceGate decision: {decision}")
    input_by_index = _input_report_by_index(criteria, input_report)
    return {
        "schema_version": "ahra/evidence-gate-report/0.1",
        "task_id": task_id,
        "generated_by": "ahra.evidence_gate",
        "verifier": actor,
        "generated_at": now,
        "decision": decision,
        "target_state": target_state,
        "summary": summary,
        "criteria": [
            {
                "criterion_index": criterion.index,
                "criterion": criterion.text,
                "status": _status(input_by_index[criterion.index])
                if criterion.index in input_by_index
                else "missing",
                "evidence_refs": _refs(input_by_index[criterion.index])
                if criterion.index in input_by_index
                else [],
                "notes": str(input_by_index[criterion.index].get("notes") or "")
                if criterion.index in input_by_index
                else "No verifier assessment was supplied.",
            }
            for criterion in criteria
        ],
        "commands": input_report.get("commands", []),
        "semantic_reviews": input_report.get("semantic_reviews", []),
    }


def _input_report_by_index(
    criteria: list[AcceptanceCriterion],
    report: dict[str, Any],
) -> dict[int, dict[str, Any]]:
    by_text = {_normalize(criterion.text): criterion.index for criterion in criteria}
    result: dict[int, dict[str, Any]] = {}
    for item in report.get("criteria", []):
        if not isinstance(item, dict):
            continue
        index = item.get("criterion_index")
        if index is None and item.get("criterion") is not None:
            index = by_text.get(_normalize(str(item["criterion"])))
        if isinstance(index, int):
            result[index] = item
    return result


def _report_evidence_refs(gate_report: dict[str, Any]) -> set[str]:
    refs: set[str] = set()
    for criterion in gate_report.get("criteria", []):
        if isinstance(criterion, dict):
            refs.update(str(ref) for ref in criterion.get("evidence_refs", []))
    return refs


def _artifact_record(
    *,
    task_id: str,
    artifact_id: str,
    name: str,
    sha256: str,
    created_by: str,
    created_at: str,
    input_refs: list[str],
) -> dict[str, Any]:
    return {
        "artifact_id": artifact_id,
        "task_id": task_id,
        "kind": "evidence_gate_report",
        "name": name,
        "uri": f"local://evidence/{name}",
        "sha256": sha256,
        "media_type": "application/json",
        "created_by": created_by,
        "created_at": created_at,
        "input_refs": input_refs,
        "evidence_refs": [],
        "supersedes": None,
    }


def _evidence_record(
    *,
    task_id: str,
    evidence_id: str,
    name: str,
    sha256: str,
    created_by: str,
    created_at: str,
    refs: list[str],
) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "task_id": task_id,
        "kind": "evidence_gate_report",
        "name": name,
        "uri": f"local://evidence/{name}",
        "sha256": sha256,
        "media_type": "application/json",
        "created_by": created_by,
        "created_at": created_at,
        "refs": refs,
    }


def _next_record_id(prefix: str, task_id: str, records: Iterable[dict[str, Any]]) -> str:
    pattern = re.compile(rf"^{re.escape(prefix)}-{re.escape(task_id)}-(\d{{4}})$")
    highest = 0
    for record in records:
        for key in ("artifact_id", "evidence_id"):
            value = str(record.get(key) or "")
            match = pattern.match(value)
            if match:
                highest = max(highest, int(match.group(1)))
    return f"{prefix}-{task_id}-{highest + 1:04d}"


def _last_event_id(path: Path) -> str | None:
    events = _load_events(path)
    if not events:
        return None
    event_id = events[-1].get("event_id")
    return str(event_id) if event_id else None


def _next_event_id(task_id: str, path: Path) -> str:
    pattern = re.compile(rf"^EVT-{re.escape(task_id)}-(\d{{4}})$")
    highest = 0
    for event in _load_events(path):
        event_id = str(event.get("event_id") or "")
        match = pattern.match(event_id)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"EVT-{task_id}-{highest + 1:04d}"


def _append_event(path: Path, event: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")


def _append_unique(existing: Any, value: str) -> list[str]:
    result = [str(item) for item in existing] if isinstance(existing, list) else []
    if value not in result:
        result.append(value)
    return result


def _request_change_blockers(
    criteria: list[AcceptanceCriterion],
    assessments: dict[int, dict[str, Any]],
) -> list[str]:
    blockers: list[str] = []
    for criterion in criteria:
        item = assessments.get(criterion.index)
        if item is None:
            blockers.append(f"Criterion {criterion.index} is missing verifier assessment.")
        elif _status(item) in FAILED_STATUSES:
            note = str(item.get("notes") or item.get("reason") or "Verifier requested changes.")
            blockers.append(f"Criterion {criterion.index}: {note}")
    return blockers


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate an AWKP task through EvidenceGate.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    evaluate = subparsers.add_parser("evaluate", help="Validate evidence and transition task state.")
    evaluate.add_argument("task", help="Task ID such as TASK-0007, or path to a task directory.")
    evaluate.add_argument("--work-root", default="work", help="AWKP work root containing tasks/.")
    evaluate.add_argument("--expected-version", required=True, type=int)
    evaluate.add_argument("--report", required=True, help="Verifier report JSON path.")
    evaluate.add_argument("--actor", required=True, help="Verifier actor, for example agent:verifier.")
    evaluate.add_argument("--decision", choices=sorted(ALLOWED_DECISIONS))
    evaluate.add_argument("--dry-run", action="store_true")

    inspect = subparsers.add_parser("inspect", help="Read task gate inputs without changing state.")
    inspect.add_argument("task", help="Task ID such as TASK-0007, or path to a task directory.")
    inspect.add_argument("--work-root", default="work", help="AWKP work root containing tasks/.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            result = inspect_task(args.task, work_root=args.work_root)
        else:
            result = evaluate_task_gate(
                args.task,
                work_root=args.work_root,
                expected_version=args.expected_version,
                report_path=args.report,
                actor=args.actor,
                decision=args.decision,
                dry_run=args.dry_run,
            ).to_dict()
    except EvidenceGateError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
