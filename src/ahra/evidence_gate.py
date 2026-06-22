from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable


ALLOWED_DECISIONS = {"approve", "request_changes"}
PASSED_STATUSES = {"passed", "pass"}
FAILED_STATUSES = {"failed", "fail", "missing", "blocked"}


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
    assessments = _map_criteria(criteria, report, evidence_by_id)
    _validate_command_results(report, report_decision)

    if report_decision == "approve":
        if state.get("blockers"):
            raise EvidenceGateError("cannot approve a task that still records blockers")
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
        if not uri.startswith("local://"):
            continue
        path = _local_uri_path(task_dir, uri)
        if not path.exists() or not path.is_file():
            raise EvidenceGateError(f"{key}[{index}] local uri is missing: {uri}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != sha:
            raise EvidenceGateError(f"{key}[{index}] hash mismatch for {uri}")


def _local_uri_path(task_dir: Path, uri: str) -> Path:
    relative = uri.removeprefix("local://")
    path = (task_dir / relative).resolve()
    try:
        path.relative_to(task_dir.resolve())
    except ValueError as exc:
        raise EvidenceGateError(f"local uri escapes task directory: {uri}") from exc
    return path


def _producer_identities(
    artifact_manifest: dict[str, Any],
    evidence_manifest: dict[str, Any],
    event_path: Path,
) -> set[str]:
    identities: set[str] = set()
    for record in artifact_manifest.get("artifacts", []):
        created_by = record.get("created_by")
        if created_by:
            identities.add(str(created_by))
    for record in evidence_manifest.get("evidence", []):
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


def _validate_command_results(report: dict[str, Any], decision: str) -> None:
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
        if command.get("changed_files_sha256") and command.get("verified_changed_files_sha256"):
            if command["changed_files_sha256"] != command["verified_changed_files_sha256"]:
                raise EvidenceGateError(f"command[{index}] is stale for changed files")


def _status(item: dict[str, Any]) -> str:
    return str(item.get("status") or "").strip().lower()


def _refs(item: dict[str, Any]) -> list[str]:
    refs = item.get("evidence_refs", [])
    if refs is None:
        return []
    if not isinstance(refs, list) or not all(isinstance(ref, str) for ref in refs):
        raise EvidenceGateError("evidence_refs must be an array of strings")
    return refs


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
