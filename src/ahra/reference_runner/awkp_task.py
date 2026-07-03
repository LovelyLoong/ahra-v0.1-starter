from __future__ import annotations

import hashlib
import json
import re
import shlex
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from ahra.evidence_gate import parse_acceptance_criteria

from .models import CheckSpec, TaskAttemptRecord, TaskRunResult, TaskSpec, WorkflowOutcome, to_jsonable


class AwkpTaskError(ValueError):
    """Raised when a workflow request cannot satisfy AWKP task authority rules."""


@dataclass(frozen=True, slots=True)
class AwkpTaskBinding:
    task_id: str
    source_task_dir: Path


def task_from_awkp_markdown(path: Path) -> TaskSpec:
    frontmatter, body = _frontmatter(path)
    task_id = str(frontmatter["id"])
    title = str(frontmatter["title"])
    objective = _section(body, "Goal") or str(frontmatter.get("description") or title)
    criteria = tuple(criterion.text for criterion in parse_acceptance_criteria(path))
    if not criteria:
        raise AwkpTaskError(f"AWKP task has no parseable acceptance criteria: {path}")
    return TaskSpec(
        id=task_id,
        title=title,
        objective=objective,
        acceptance_criteria=criteria,
        scope=tuple(_section_items(body, "Scope")),
        requirements=tuple(_section_items(body, "Constraints")),
        non_goals=tuple(_section_items(body, "Non-goals")),
        checks=tuple(_verification_checks(body)),
    )


def find_awkp_task_binding(source_workspace_ref: str, task: TaskSpec | None) -> AwkpTaskBinding | None:
    if task is None:
        return None
    source = Path(source_workspace_ref).resolve()
    task_dir = source / "work" / "tasks" / task.id
    if not task_dir.exists():
        return None
    if not task_dir.is_dir():
        raise AwkpTaskError(f"AWKP task path is not a directory: {task_dir}")
    return AwkpTaskBinding(task_id=task.id, source_task_dir=task_dir)


def assert_awkp_task_ready(binding: AwkpTaskBinding) -> None:
    state = _load_json(binding.source_task_dir / "state.json")
    if state.get("task_id") != binding.task_id:
        raise AwkpTaskError(f"state task_id does not match task directory: {binding.task_id}")
    if state.get("state") != "ready":
        raise AwkpTaskError(
            f"formal workflow requires AWKP task state 'ready'; "
            f"{binding.task_id} is {state.get('state')!r}"
        )
    if state.get("lease"):
        raise AwkpTaskError(f"formal workflow cannot start with an active lease: {binding.task_id}")
    for dependency in _depends_on(binding.source_task_dir / "task.md"):
        dependency_dir = binding.source_task_dir.parent / dependency
        dependency_state = _load_json(dependency_dir / "state.json")
        if dependency_state.get("state") != "completed":
            raise AwkpTaskError(
                f"formal workflow dependency is not completed: "
                f"{dependency} is {dependency_state.get('state')!r}"
            )


def claim_awkp_task_in_workspace(workspace_ref: str, task_id: str, run_id: str) -> None:
    task_dir = _workspace_task_dir(workspace_ref, task_id)
    state_path = task_dir / "state.json"
    state = _load_json(state_path)
    if state.get("state") != "ready":
        raise AwkpTaskError(f"cannot claim {task_id}; state is {state.get('state')!r}")
    now = _now()
    version = int(state["state_version"])
    holder = f"workflow-runner:reference:{run_id}"
    event_path = task_dir / "events.jsonl"
    event_id = _next_event_id(task_id, event_path)
    _append_event(
        event_path,
        {
            "schema_version": "awkp/0.1",
            "event_id": event_id,
            "idempotency_key": f"{task_id}:workflow-claim:{run_id}",
            "task_id": task_id,
            "context_id": state.get("context_id"),
            "event_type": "lease_acquired",
            "actor": "workflow-runner:reference",
            "occurred_at": now,
            "causation_id": _last_event_id(event_path),
            "correlation_id": state.get("context_id"),
            "from_state": "ready",
            "to_state": "working",
            "reason": f"Workflow run {run_id} claimed the task for formal execution.",
            "refs": ["task.md", "state.json"],
        },
    )
    updated = dict(state)
    updated.update(
        {
            "state": "working",
            "state_version": version + 1,
            "owner": holder,
            "attempt": int(state.get("attempt") or 0) + 1,
            "lease": {
                "holder": holder,
                "acquired_at": now,
                "heartbeat_at": now,
                "expires_at": None,
            },
            "next_action": f"Workflow run {run_id} is executing in an isolated worktree.",
            "pause_reason": None,
            "updated_at": now,
        }
    )
    _write_json(state_path, updated)


def publish_awkp_review_in_workspace(
    workspace_ref: str,
    *,
    result: TaskRunResult,
) -> None:
    if result.status != WorkflowOutcome.ACCEPTED:
        raise AwkpTaskError(f"only accepted task runs can be published to AWKP review: {result.status}")
    task_dir = _workspace_task_dir(workspace_ref, result.task_id)
    state_path = task_dir / "state.json"
    event_path = task_dir / "events.jsonl"
    state = _load_json(state_path)
    from_state = _publishable_state(result.task_id, state, "review")

    now = _now()
    report_name = f"workflow-run-{result.run_id}.json"
    artifact_id, evidence_id = _write_report_records(
        task_dir=task_dir,
        result=result,
        report_name=report_name,
        record_kind="workflow_run_report",
        now=now,
    )

    handoff_ref = _write_handoff(task_dir, result, evidence_id, now, report_name=report_name)
    artifact_event_id = _next_event_id(result.task_id, event_path)
    _append_event(
        event_path,
        {
            "schema_version": "awkp/0.1",
            "event_id": artifact_event_id,
            "idempotency_key": f"{result.task_id}:workflow-artifact:{result.run_id}",
            "task_id": result.task_id,
            "context_id": state.get("context_id"),
            "event_type": "artifact_published",
            "actor": "workflow-runner:reference",
            "occurred_at": now,
            "causation_id": _last_event_id(event_path),
            "correlation_id": state.get("context_id"),
            "from_state": from_state,
            "to_state": from_state,
            "reason": f"Published workflow run report for {result.run_id}.",
            "refs": ["artifact-manifest.json", "evidence-manifest.json", f"evidence/{report_name}"],
        },
    )
    review_event_id = _next_event_id(result.task_id, event_path)
    _append_event(
        event_path,
        {
            "schema_version": "awkp/0.1",
            "event_id": review_event_id,
            "idempotency_key": f"{result.task_id}:workflow-review:{result.run_id}",
            "task_id": result.task_id,
            "context_id": state.get("context_id"),
            "event_type": "review_requested",
            "actor": "workflow-runner:reference",
            "occurred_at": now,
            "causation_id": artifact_event_id,
            "correlation_id": state.get("context_id"),
            "from_state": from_state,
            "to_state": "review",
            "reason": "Workflow run passed deterministic and semantic gates; EvidenceGate review remains required.",
            "refs": ["state.json", handoff_ref, f"evidence/{report_name}"],
        },
    )

    updated = dict(state)
    updated.update(
        {
            "state": "review",
            "state_version": int(state["state_version"]) + 1,
            "owner": None,
            "lease": None,
            "next_action": "Run independent EvidenceGate review for the workflow run evidence.",
            "pause_reason": None,
            "artifact_refs": _append_unique(state.get("artifact_refs", []), artifact_id),
            "evidence_refs": _append_unique(state.get("evidence_refs", []), evidence_id),
            "updated_at": now,
        }
    )
    _write_json(state_path, updated)


def publish_awkp_failure_in_workspace(
    workspace_ref: str,
    *,
    result: TaskRunResult,
) -> None:
    if result.status not in {WorkflowOutcome.REJECTED, WorkflowOutcome.ERROR, WorkflowOutcome.BLOCKED}:
        raise AwkpTaskError(f"only failed task runs can publish AWKP failure evidence: {result.status}")
    task_dir = _workspace_task_dir(workspace_ref, result.task_id)
    state_path = task_dir / "state.json"
    event_path = task_dir / "events.jsonl"
    state = _load_json(state_path)
    from_state = _publishable_state(result.task_id, state, "failure")

    now = _now()
    report_name = f"workflow-run-{result.run_id}-failure.json"
    artifact_id, evidence_id = _write_report_records(
        task_dir=task_dir,
        result=result,
        report_name=report_name,
        record_kind="workflow_failure_report",
        now=now,
    )

    handoff_ref = _write_handoff(
        task_dir,
        result,
        evidence_id,
        now,
        report_name=report_name,
        failed=True,
    )
    artifact_event_id = _next_event_id(result.task_id, event_path)
    _append_event(
        event_path,
        {
            "schema_version": "awkp/0.1",
            "event_id": artifact_event_id,
            "idempotency_key": f"{result.task_id}:workflow-failure-artifact:{result.run_id}",
            "task_id": result.task_id,
            "context_id": state.get("context_id"),
            "event_type": "artifact_published",
            "actor": "workflow-runner:reference",
            "occurred_at": now,
            "causation_id": _last_event_id(event_path),
            "correlation_id": state.get("context_id"),
            "from_state": from_state,
            "to_state": from_state,
            "reason": f"Published terminal workflow failure evidence for {result.run_id}.",
            "refs": ["artifact-manifest.json", "evidence-manifest.json", f"evidence/{report_name}"],
        },
    )
    review_event_id = _next_event_id(result.task_id, event_path)
    _append_event(
        event_path,
        {
            "schema_version": "awkp/0.1",
            "event_id": review_event_id,
            "idempotency_key": f"{result.task_id}:workflow-failure-review:{result.run_id}",
            "task_id": result.task_id,
            "context_id": state.get("context_id"),
            "event_type": "review_requested",
            "actor": "workflow-runner:reference",
            "occurred_at": now,
            "causation_id": artifact_event_id,
            "correlation_id": state.get("context_id"),
            "from_state": from_state,
            "to_state": "review",
            "reason": "Workflow run ended in terminal failure; user or verifier judgment is required.",
            "refs": ["state.json", handoff_ref, f"evidence/{report_name}"],
        },
    )

    updated = dict(state)
    updated.update(
        {
            "state": "review",
            "state_version": int(state["state_version"]) + 1,
            "owner": None,
            "lease": None,
            "next_action": "Review terminal workflow failure evidence before retrying, changing, or failing the task.",
            "pause_reason": None,
            "blockers": _append_unique(state.get("blockers", []), result.message),
            "artifact_refs": _append_unique(state.get("artifact_refs", []), artifact_id),
            "evidence_refs": _append_unique(state.get("evidence_refs", []), evidence_id),
            "updated_at": now,
        }
    )
    _write_json(state_path, updated)


def _publishable_state(task_id: str, state: dict[str, Any], action: str) -> str:
    state_name = str(state.get("state"))
    if state_name == "working":
        return state_name
    if state_name == "review" and not state.get("lease"):
        return state_name
    raise AwkpTaskError(f"cannot publish {action} for {task_id}; state is {state.get('state')!r}")


def _write_report_records(
    *,
    task_dir: Path,
    result: TaskRunResult,
    report_name: str,
    record_kind: str,
    now: str,
) -> tuple[str, str]:
    report_path = task_dir / "evidence" / report_name
    report = _workflow_report(result, now)
    report_bytes = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_bytes(report_bytes)
    digest = hashlib.sha256(report_bytes).hexdigest()

    artifact_manifest_path = task_dir / "artifact-manifest.json"
    evidence_manifest_path = task_dir / "evidence-manifest.json"
    artifact_manifest = _load_manifest(artifact_manifest_path, "artifacts", result.task_id)
    evidence_manifest = _load_manifest(evidence_manifest_path, "evidence", result.task_id)
    artifact_id = _next_record_id("ART", result.task_id, artifact_manifest["artifacts"])
    evidence_id = _next_record_id("EVD", result.task_id, evidence_manifest["evidence"])
    artifact = {
        "artifact_id": artifact_id,
        "task_id": result.task_id,
        "kind": record_kind,
        "name": report_name,
        "uri": f"local://evidence/{report_name}",
        "sha256": digest,
        "media_type": "application/json",
        "created_by": "workflow-runner:reference",
        "created_at": now,
        "input_refs": [result.run_id, result.artifact_dir],
        "evidence_refs": [evidence_id],
        "supersedes": None,
    }
    evidence = {
        "evidence_id": evidence_id,
        "task_id": result.task_id,
        "kind": record_kind,
        "name": report_name,
        "uri": f"local://evidence/{report_name}",
        "sha256": digest,
        "media_type": "application/json",
        "created_by": "workflow-runner:reference",
        "created_at": now,
        "refs": [artifact_id, result.run_id],
    }
    artifact_manifest["artifacts"].append(artifact)
    evidence_manifest["evidence"].append(evidence)
    _write_json(artifact_manifest_path, artifact_manifest)
    _write_json(evidence_manifest_path, evidence_manifest)
    return artifact_id, evidence_id


def _workflow_report(result: TaskRunResult, now: str) -> dict[str, Any]:
    return {
        "schema_version": "ahra/workflow-run-report/0.1",
        "task_id": result.task_id,
        "run_id": result.run_id,
        "generated_by": "workflow-runner:reference",
        "generated_at": now,
        "status": str(result.status),
        "commit": result.commit,
        "branch": result.branch,
        "workspace": result.workspace,
        "artifact_dir": result.artifact_dir,
        "summary": result.message,
        "attempt_count": len(result.attempts),
        "last_error": _last_attempt_error(result.attempts),
        "terminal_failure_record": _terminal_failure_record(result),
        "attempts": [to_jsonable(attempt) for attempt in result.attempts],
    }


def _last_attempt_error(attempts: tuple[TaskAttemptRecord, ...]) -> str | None:
    for attempt in reversed(attempts):
        if attempt.error:
            return attempt.error
        if attempt.review and attempt.review.blocking_issues:
            return "; ".join(attempt.review.blocking_issues)
        if attempt.deterministic:
            if attempt.deterministic.policy.violations:
                return "; ".join(attempt.deterministic.policy.violations)
            failed_checks = [
                check.name
                for check in attempt.deterministic.checks
                if check.required and not check.passed
            ]
            if failed_checks:
                return f"Required checks failed: {', '.join(failed_checks)}"
    return None


def _terminal_failure_record(result: TaskRunResult) -> str | None:
    if result.status not in {WorkflowOutcome.REJECTED, WorkflowOutcome.ERROR, WorkflowOutcome.BLOCKED}:
        return None
    return f"{result.artifact_dir}/tasks/{result.task_id}/terminal-failure.json"


def _write_handoff(
    task_dir: Path,
    result: TaskRunResult,
    evidence_id: str,
    now: str,
    *,
    report_name: str,
    failed: bool = False,
) -> str:
    handoff_dir = task_dir / "handoffs"
    handoff_dir.mkdir(parents=True, exist_ok=True)
    index = _next_handoff_index(handoff_dir)
    name = f"HANDOFF-{index:04d}.md"
    path = handoff_dir / name
    title = (
        f"Workflow run {result.run_id} failed and needs judgment"
        if failed
        else f"Workflow run {result.run_id} ready for EvidenceGate review"
    )
    status = (
        f"`{result.run_id}` ended as `{result.status}` and published failure evidence `{evidence_id}`."
        if failed
        else f"`{result.run_id}` passed the reference workflow gates and published `{evidence_id}`."
    )
    next_action = (
        "Review the failure evidence. A user or independent verifier must decide whether to retry, request changes, or fail the task."
        if failed
        else "Run an independent EvidenceGate review. Do not mark the task completed from this handoff alone."
    )
    path.write_text(
        "\n".join(
            [
                "---",
                "type: Handoff",
                f"id: HANDOFF-{result.task_id}-{index:04d}",
                "schema_version: awkp/0.1",
                f"title: {title}",
                f"created_at: {now}",
                f"source_refs: [../task.md, ../state.json, ../evidence/{report_name}]",
                "---",
                "",
                "# Status",
                "",
                status,
                "",
                "# Verification",
                "",
                "See the workflow run report and run artifact directory for deterministic and semantic evidence.",
                "",
                "# Next Action",
                "",
                next_action,
                "",
            ]
        ),
        encoding="utf-8",
    )
    return f"handoffs/{name}"


def _frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise AwkpTaskError(f"AWKP task markdown is missing frontmatter: {path}")
    end = text.find("\n---", 4)
    if end == -1:
        raise AwkpTaskError(f"AWKP task markdown frontmatter is not closed: {path}")
    metadata = yaml.safe_load(text[4:end])
    if not isinstance(metadata, dict):
        raise AwkpTaskError(f"AWKP task frontmatter must be an object: {path}")
    return metadata, text[end + 4 :]


def _depends_on(path: Path) -> tuple[str, ...]:
    metadata, _ = _frontmatter(path)
    value = metadata.get("depends_on", ())
    if value is None:
        return ()
    if not isinstance(value, list):
        raise AwkpTaskError(f"depends_on must be a list in {path}")
    return tuple(str(item) for item in value)


def _section(body: str, heading: str) -> str:
    lines = _section_lines(body, heading)
    return "\n".join(line.strip() for line in lines if line.strip()).strip()


def _section_items(body: str, heading: str) -> list[str]:
    items: list[str] = []
    for line in _section_lines(body, heading):
        text = line.strip()
        if text.startswith("- "):
            items.append(text[2:].strip())
        elif text:
            items.append(text)
    return items


def _verification_checks(body: str) -> list[CheckSpec]:
    checks: list[CheckSpec] = []
    index = 1
    for item in _section_items(body, "Verification method"):
        command = _verification_command(item)
        if not command:
            continue
        checks.append(
            CheckSpec(
                name=f"verification {index}",
                argv=tuple(shlex.split(command, posix=False)),
            )
        )
        index += 1
    return checks


def _verification_command(item: str) -> str | None:
    text = item.strip()
    if not text:
        return None
    if text.startswith("`") and text.endswith("`"):
        return text.strip("` ").strip()
    if text.startswith("$ "):
        return text[2:].strip()
    return None


def _section_lines(body: str, heading: str) -> list[str]:
    lines = body.splitlines()
    in_section = False
    result: list[str] = []
    target = heading.casefold()
    for line in lines:
        match = re.match(r"^#\s+(.+?)\s*$", line)
        if match:
            if in_section:
                break
            in_section = match.group(1).casefold() == target
            continue
        if in_section:
            result.append(line)
    return result


def _workspace_task_dir(workspace_ref: str, task_id: str) -> Path:
    task_dir = Path(workspace_ref).resolve() / "work" / "tasks" / task_id
    if not task_dir.exists():
        raise AwkpTaskError(f"AWKP task directory not found in workspace: {task_dir}")
    return task_dir


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise AwkpTaskError(f"required AWKP JSON file is missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AwkpTaskError(f"AWKP JSON document must be an object: {path}")
    return data


def _load_manifest(path: Path, key: str, task_id: str) -> dict[str, Any]:
    data = _load_json(path)
    if data.get("schema_version") != "awkp/0.1":
        raise AwkpTaskError(f"{path.name} schema_version must be awkp/0.1")
    if data.get("task_id") != task_id:
        raise AwkpTaskError(f"{path.name} task_id must be {task_id}")
    if not isinstance(data.get(key), list):
        raise AwkpTaskError(f"{path.name} {key} must be an array")
    return data


def _write_json(path: Path, data: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    # On Windows a host file scanner (e.g. an endpoint encryption client) can
    # transiently lock the target during the write/rename, surfacing as
    # PermissionError (WinError 5). The lock is momentary, so retry with a short
    # backoff before giving up and re-raising the real error.
    last_error: PermissionError | None = None
    for attempt in range(5):
        try:
            temporary.write_text(payload, encoding="utf-8")
            temporary.replace(path)
            return
        except PermissionError as error:
            last_error = error
            time.sleep(0.2 * (attempt + 1))
    assert last_error is not None
    raise last_error


def _append_event(path: Path, event: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")


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


def _load_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _next_record_id(prefix: str, task_id: str, records: list[dict[str, Any]]) -> str:
    pattern = re.compile(rf"^{re.escape(prefix)}-{re.escape(task_id)}-(\d{{4}})$")
    highest = 0
    for record in records:
        for key in ("artifact_id", "evidence_id"):
            match = pattern.match(str(record.get(key) or ""))
            if match:
                highest = max(highest, int(match.group(1)))
    return f"{prefix}-{task_id}-{highest + 1:04d}"


def _next_handoff_index(handoff_dir: Path) -> int:
    highest = 0
    for path in handoff_dir.glob("HANDOFF-*.md"):
        match = re.fullmatch(r"HANDOFF-(\d{4})\.md", path.name)
        if match:
            highest = max(highest, int(match.group(1)))
    return highest + 1


def _append_unique(existing: Any, value: str) -> list[str]:
    result = [str(item) for item in existing] if isinstance(existing, list) else []
    if value not in result:
        result.append(value)
    return result


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
