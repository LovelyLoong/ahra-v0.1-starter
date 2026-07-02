#!/usr/bin/env python3
"""Minimal AWKP profile linter; standard library only."""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_STATES = {
    "queued", "ready", "working", "waiting_input", "waiting_auth",
    "waiting_dependency", "review", "changes_requested", "completed",
    "failed", "canceled", "rejected",
}
REQUIRED_DOC_KEYS = {
    "type", "id", "schema_version", "title", "description", "status", "owner",
}
REQUIRED_WORK_ITEM_KEYS = {
    "type", "id", "schema_version", "title", "description", "context_id",
    "priority", "risk_level", "requester", "reviewer", "created_at",
    "depends_on", "input_refs", "output_contract",
}
ERRORS: list[str] = []
WARNINGS: list[str] = []


def is_proposed_task_draft(path: Path) -> bool:
    try:
        rel = path.relative_to(ROOT / "work" / "proposed" / "tasks")
    except ValueError:
        return False
    return rel.suffix == ".md"


def is_task_run_artifact(path: Path) -> bool:
    try:
        rel = path.relative_to(ROOT)
    except ValueError:
        return False
    parts = rel.parts
    if len(parts) < 4 or parts[0] != "work" or parts[1] != "tasks":
        return False
    # Run output lives under work/tasks/<TASK>/runs/. A run's worktree can
    # materialize a full repo copy that nests its own work/tasks/<TASK>/runs/
    # tree, so treat "runs" at any depth below the task dir as run byproduct
    # rather than authored content.
    return "runs" in parts[3:]


def err(path: Path, message: str) -> None:
    ERRORS.append(f"{path.relative_to(ROOT)}: {message}")


def warn(path: Path, message: str) -> None:
    WARNINGS.append(f"{path.relative_to(ROOT)}: {message}")


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return None
    if value in {"null", "~"}:
        return None
    if value in {"true", "false"}:
        return value == "true"
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [] if not inner else [x.strip().strip("'\"") for x in inner.split(",")]
    return value.strip("'\"")


def simple_frontmatter(path: Path) -> dict[str, Any] | None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        return None
    data: dict[str, Any] = {}
    current_list: str | None = None
    for raw in text[4:end].splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if re.match(r"^\s+-\s+", raw) and current_list:
            data.setdefault(current_list, []).append(parse_scalar(re.sub(r"^\s+-\s+", "", raw)))
            continue
        if raw.startswith(" "):
            # Nested YAML is not needed for the top-level checks.
            continue
        if ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        key = key.strip()
        parsed = parse_scalar(value)
        data[key] = parsed
        current_list = key if parsed is None else None
        if current_list:
            data[current_list] = []
    return data


def parse_iso(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def lint_root() -> None:
    for required in ["AGENTS.md", "WORKFLOW.md", "SPEC.md", "docs/index.md", "work/index.md"]:
        path = ROOT / required
        if not path.exists():
            err(path, "required file is missing")
    agents = ROOT / "AGENTS.md"
    if agents.exists():
        lines = agents.read_text(encoding="utf-8").splitlines()
        if len(lines) > 120:
            warn(agents, f"{len(lines)} lines; keep the root entry map near or below 120 lines")


def lint_docs() -> None:
    ids: dict[str, Path] = {}
    now = datetime.now(timezone.utc)
    for base in [ROOT / "docs", ROOT / "work"]:
        for path in base.rglob("*.md"):
            if is_task_run_artifact(path):
                continue
            if path.name == "README.md":
                continue
            if is_proposed_task_draft(path):
                continue
            fm = simple_frontmatter(path)
            if fm is None:
                err(path, "missing or malformed YAML frontmatter")
                continue
            if fm.get("type") == "WorkItem":
                missing = REQUIRED_WORK_ITEM_KEYS - set(fm)
            else:
                missing = REQUIRED_DOC_KEYS - set(fm)
            if missing:
                err(path, "missing top-level fields: " + ", ".join(sorted(missing)))
            doc_id = fm.get("id")
            if doc_id:
                if doc_id in ids:
                    err(path, f"duplicate id {doc_id!r}; first seen in {ids[doc_id].relative_to(ROOT)}")
                ids[doc_id] = path
            if fm.get("schema_version") != "awkp/0.1":
                err(path, "schema_version must be awkp/0.1")
            review_after = fm.get("review_after")
            status = fm.get("status")
            if review_after and status == "active":
                parsed = parse_iso(str(review_after))
                if parsed is None:
                    err(path, "review_after is not ISO 8601")
                elif parsed < now:
                    warn(path, f"active document is stale since {review_after}")
            if path.stat().st_size > 120_000:
                warn(path, "large Markdown concept; split for progressive disclosure")


def lint_task(task_dir: Path) -> None:
    task_id = task_dir.name
    for required in ["task.md", "state.json", "events.jsonl", "artifact-manifest.json", "handoffs"]:
        path = task_dir / required
        if not path.exists():
            err(path, "required task component is missing")

    state_path = task_dir / "state.json"
    if not state_path.exists():
        return
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception as exc:
        err(state_path, f"invalid JSON: {exc}")
        return
    for key in ["schema_version","task_id","context_id","state","state_version","attempt","next_action","blockers","artifact_refs","evidence_refs","updated_at"]:
        if key not in state:
            err(state_path, f"missing field {key}")
    if state.get("schema_version") != "awkp/0.1":
        err(state_path, "schema_version must be awkp/0.1")
    if state.get("task_id") != task_id:
        err(state_path, f"task_id must match directory name {task_id}")
    if state.get("state") not in ALLOWED_STATES:
        err(state_path, f"invalid state {state.get('state')!r}")
    if not isinstance(state.get("state_version"), int) or state.get("state_version", -1) < 0:
        err(state_path, "state_version must be a non-negative integer")
    if state.get("state") == "working" and not state.get("lease"):
        err(state_path, "working state requires a lease")

    event_path = task_dir / "events.jsonl"
    event_ids: set[str] = set()
    idem_keys: set[str] = set()
    last_time: datetime | None = None
    if event_path.exists():
        for lineno, line in enumerate(event_path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except Exception as exc:
                err(event_path, f"line {lineno}: invalid JSON: {exc}")
                continue
            for key in ["schema_version","event_id","idempotency_key","task_id","context_id","event_type","actor","occurred_at","correlation_id","reason","refs"]:
                if key not in event:
                    err(event_path, f"line {lineno}: missing {key}")
            if event.get("task_id") != task_id:
                err(event_path, f"line {lineno}: task_id mismatch")
            eid = event.get("event_id")
            idem = event.get("idempotency_key")
            if eid in event_ids:
                err(event_path, f"line {lineno}: duplicate event_id {eid}")
            if idem in idem_keys:
                err(event_path, f"line {lineno}: duplicate idempotency_key {idem}")
            if eid: event_ids.add(eid)
            if idem: idem_keys.add(idem)
            ts = parse_iso(str(event.get("occurred_at", "")))
            if ts is None:
                err(event_path, f"line {lineno}: invalid occurred_at")
            elif last_time and ts < last_time:
                err(event_path, f"line {lineno}: timestamps are not monotonic")
            elif ts:
                last_time = ts

    manifest_path = task_dir / "artifact-manifest.json"
    artifacts = []
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("task_id") != task_id:
                err(manifest_path, "task_id mismatch")
            artifacts = manifest.get("artifacts", [])
            if not isinstance(artifacts, list):
                err(manifest_path, "artifacts must be an array")
                artifacts = []
            for i, art in enumerate(artifacts):
                for key in ["artifact_id","task_id","kind","name","uri","sha256","media_type","created_by","created_at"]:
                    if key not in art:
                        err(manifest_path, f"artifact[{i}] missing {key}")
                if art.get("task_id") != task_id:
                    err(manifest_path, f"artifact[{i}] task_id mismatch")
                if not re.fullmatch(r"[a-f0-9]{64}", str(art.get("sha256", ""))):
                    err(manifest_path, f"artifact[{i}] sha256 must be 64 lowercase hex characters")
        except Exception as exc:
            err(manifest_path, f"invalid JSON: {exc}")

    if state.get("state") == "completed":
        if not state.get("evidence_refs"):
            err(state_path, "completed task requires evidence_refs")
        if not artifacts:
            err(manifest_path, "completed task requires at least one artifact")


def lint_tasks() -> None:
    tasks_root = ROOT / "work" / "tasks"
    if not tasks_root.exists():
        err(tasks_root, "tasks directory is missing")
        return
    for task_dir in sorted(p for p in tasks_root.iterdir() if p.is_dir()):
        lint_task(task_dir)


def lint_relative_links() -> None:
    pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    for path in ROOT.rglob("*.md"):
        if is_task_run_artifact(path):
            continue
        text = path.read_text(encoding="utf-8")
        for target in pattern.findall(text):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target = target.split("#", 1)[0]
            if not target:
                continue
            resolved = (path.parent / target).resolve()
            try:
                resolved.relative_to(ROOT.resolve())
            except ValueError:
                err(path, f"relative link escapes repository: {target}")
                continue
            if not resolved.exists():
                err(path, f"broken relative link: {target}")


def lint_authority_map() -> None:
    path = ROOT / "docs" / "architecture" / "authority-map.md"
    if not path.exists():
        err(path, "required architecture authority map is missing")
        return
    authority_ids: set[str] = set()
    link_pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if not stripped.startswith("| AUTH-"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 3:
            err(path, f"line {lineno}: authority row must include id, concept, and active owner")
            continue
        authority_id = cells[0]
        if authority_id in authority_ids:
            err(path, f"line {lineno}: duplicate authority id {authority_id}")
        authority_ids.add(authority_id)
        owner_cell = cells[2]
        match = link_pattern.search(owner_cell)
        if not match:
            err(path, f"line {lineno}: active owner must be a relative Markdown link")
            continue
        target = match.group(1).split("#", 1)[0]
        if not target:
            err(path, f"line {lineno}: active owner link is empty")
            continue
        resolved = (path.parent / target).resolve()
        try:
            resolved.relative_to(ROOT.resolve())
        except ValueError:
            err(path, f"line {lineno}: active owner escapes repository: {target}")
            continue
        if not resolved.exists():
            err(path, f"line {lineno}: active owner link is broken: {target}")
            continue
        if resolved.suffix == ".md":
            fm = simple_frontmatter(resolved)
            if fm is None:
                err(path, f"line {lineno}: active owner has no parseable frontmatter: {target}")
            elif fm.get("status") != "active":
                err(path, f"line {lineno}: active owner {target} must have status: active")
    if not authority_ids:
        err(path, "authority map must define at least one AUTH-* row")


def main() -> int:
    lint_root()
    lint_docs()
    lint_tasks()
    lint_authority_map()
    lint_relative_links()
    for message in WARNINGS:
        print("WARNING:", message)
    for message in ERRORS:
        print("ERROR:", message)
    print(f"AWKP lint: {len(ERRORS)} error(s), {len(WARNINGS)} warning(s)")
    return 1 if ERRORS else 0


if __name__ == "__main__":
    raise SystemExit(main())
