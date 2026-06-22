from __future__ import annotations

import asyncio
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from ahra.evidence_gate import EvidenceGateError, evaluate_task_gate, inspect_task
from ahra.mcp_server import AhraMCPServer


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _append_event(path: Path, event: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")


def _make_task(root: Path, *, task_id: str = "TASK-9001") -> Path:
    task_dir = root / "work" / "tasks" / task_id
    evidence_dir = task_dir / "evidence"
    evidence_dir.mkdir(parents=True)
    task_md = """---
type: WorkItem
id: TASK-9001
schema_version: awkp/0.1
title: Temporary gate task
description: Temporary test task.
context_id: CTX-gate-test
priority: P0
risk_level: R1
requester: human:maintainer
reviewer: agent:verifier
created_at: 2026-06-22T00:00:00Z
depends_on: []
input_refs: []
output_contract: []
---

# Goal

Test EvidenceGate.

# Acceptance criteria

- [ ] Criterion one is satisfied.
- [ ] Criterion two is satisfied with continuation
      text.

# Verification method

- unittest
"""
    task_dir.joinpath("task.md").write_text(task_md.replace("TASK-9001", task_id), encoding="utf-8")
    _write_json(
        task_dir / "state.json",
        {
            "schema_version": "awkp/0.1",
            "task_id": task_id,
            "context_id": "CTX-gate-test",
            "state": "review",
            "state_version": 4,
            "owner": None,
            "attempt": 1,
            "lease": None,
            "next_action": "Await independent verifier.",
            "pause_reason": None,
            "blockers": [],
            "artifact_refs": ["ART-TASK-9001-0001".replace("TASK-9001", task_id)],
            "evidence_refs": ["EVD-TASK-9001-0001".replace("TASK-9001", task_id)],
            "updated_at": "2026-06-22T00:04:00Z",
        },
    )
    report_payload = b'{"ok": true}\n'
    report_sha = hashlib.sha256(report_payload).hexdigest()
    (evidence_dir / "implementation-report.json").write_bytes(report_payload)
    artifact_id = f"ART-{task_id}-0001"
    evidence_id = f"EVD-{task_id}-0001"
    _write_json(
        task_dir / "artifact-manifest.json",
        {
            "schema_version": "awkp/0.1",
            "task_id": task_id,
            "artifacts": [
                {
                    "artifact_id": artifact_id,
                    "task_id": task_id,
                    "kind": "verification_report",
                    "name": "implementation-report.json",
                    "uri": "local://evidence/implementation-report.json",
                    "sha256": report_sha,
                    "media_type": "application/json",
                    "created_by": "agent:codex",
                    "created_at": "2026-06-22T00:03:00Z",
                    "input_refs": ["task.md"],
                    "evidence_refs": [evidence_id],
                    "supersedes": None,
                }
            ],
        },
    )
    _write_json(
        task_dir / "evidence-manifest.json",
        {
            "schema_version": "awkp/0.1",
            "task_id": task_id,
            "evidence": [
                {
                    "evidence_id": evidence_id,
                    "task_id": task_id,
                    "kind": "verification_report",
                    "name": "implementation-report.json",
                    "uri": "local://evidence/implementation-report.json",
                    "sha256": report_sha,
                    "media_type": "application/json",
                    "created_by": "agent:codex",
                    "created_at": "2026-06-22T00:03:00Z",
                    "refs": [artifact_id],
                }
            ],
        },
    )
    _append_event(
        task_dir / "events.jsonl",
        {
            "schema_version": "awkp/0.1",
            "event_id": f"EVT-{task_id}-0001",
            "idempotency_key": f"{task_id}:create",
            "task_id": task_id,
            "context_id": "CTX-gate-test",
            "event_type": "task_created",
            "actor": "human:maintainer",
            "occurred_at": "2026-06-22T00:00:00Z",
            "causation_id": None,
            "correlation_id": "CTX-gate-test",
            "from_state": None,
            "to_state": "ready",
            "reason": "Created for test.",
            "refs": ["task.md"],
        },
    )
    _append_event(
        task_dir / "events.jsonl",
        {
            "schema_version": "awkp/0.1",
            "event_id": f"EVT-{task_id}-0002",
            "idempotency_key": f"{task_id}:artifact",
            "task_id": task_id,
            "context_id": "CTX-gate-test",
            "event_type": "artifact_published",
            "actor": "agent:codex",
            "occurred_at": "2026-06-22T00:03:00Z",
            "causation_id": f"EVT-{task_id}-0001",
            "correlation_id": "CTX-gate-test",
            "from_state": "working",
            "to_state": "review",
            "reason": "Implementation ready for review.",
            "refs": ["artifact-manifest.json", "evidence-manifest.json"],
        },
    )
    return task_dir


def _write_gate_input(root: Path, *, task_id: str = "TASK-9001", decision: str = "approve") -> Path:
    status = "passed" if decision == "approve" else "failed"
    evidence_refs = [f"EVD-{task_id}-0001"] if decision == "approve" else []
    report = {
        "schema_version": "ahra/evidence-gate-input/0.1",
        "task_id": task_id,
        "verifier": "agent:verifier",
        "decision": decision,
        "summary": "Verifier mapped criteria to evidence.",
        "criteria": [
            {
                "criterion_index": 1,
                "status": status,
                "evidence_refs": evidence_refs,
                "notes": "Checked.",
            },
            {
                "criterion_index": 2,
                "status": "passed" if decision == "approve" else "missing",
                "evidence_refs": evidence_refs if decision == "approve" else [],
                "notes": "Checked.",
            },
        ],
        "commands": [{"command": "python scripts\\check.py", "status": "passed"}],
    }
    path = root / "gate-input.json"
    _write_json(path, report)
    return path


class EvidenceGateTests(unittest.TestCase):
    def test_approve_writes_gate_report_and_completes_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            task_dir = _make_task(root)
            report = _write_gate_input(root)

            result = evaluate_task_gate(
                "TASK-9001",
                work_root=root / "work",
                expected_version=4,
                report_path=report,
                actor="agent:verifier",
            )

            self.assertEqual(result.state, "completed")
            state = json.loads((task_dir / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["state"], "completed")
            self.assertEqual(state["state_version"], 5)
            self.assertIn(result.report_artifact_id, state["artifact_refs"])
            self.assertIn(result.report_evidence_id, state["evidence_refs"])
            self.assertTrue(Path(str(result.report_path)).exists())
            events = [
                json.loads(line)
                for line in (task_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(events[-1]["event_type"], "evidence_gate_approved")

    def test_request_changes_records_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            task_dir = _make_task(root)
            report = _write_gate_input(root, decision="request_changes")

            result = evaluate_task_gate(
                task_dir,
                work_root=root / "work",
                expected_version=4,
                report_path=report,
                actor="agent:verifier",
            )

            self.assertEqual(result.state, "changes_requested")
            state = json.loads((task_dir / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["state"], "changes_requested")
            self.assertGreaterEqual(len(state["blockers"]), 1)

    def test_rejects_stale_expected_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _make_task(root)
            report = _write_gate_input(root)

            with self.assertRaisesRegex(EvidenceGateError, "expected state_version"):
                evaluate_task_gate(
                    "TASK-9001",
                    work_root=root / "work",
                    expected_version=3,
                    report_path=report,
                    actor="agent:verifier",
                )

    def test_rejects_producer_self_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _make_task(root)
            report = _write_gate_input(root)
            data = json.loads(report.read_text(encoding="utf-8"))
            data["verifier"] = "agent:codex"
            _write_json(report, data)

            with self.assertRaisesRegex(EvidenceGateError, "producer identity"):
                evaluate_task_gate(
                    "TASK-9001",
                    work_root=root / "work",
                    expected_version=4,
                    report_path=report,
                    actor="agent:codex",
                )

    def test_rejects_approve_without_evidence_for_every_criterion(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _make_task(root)
            report = _write_gate_input(root)
            data = json.loads(report.read_text(encoding="utf-8"))
            data["criteria"][1]["evidence_refs"] = []
            _write_json(report, data)

            with self.assertRaisesRegex(EvidenceGateError, "has no evidence_refs"):
                evaluate_task_gate(
                    "TASK-9001",
                    work_root=root / "work",
                    expected_version=4,
                    report_path=report,
                    actor="agent:verifier",
                )

    def test_inspect_task_returns_criteria_and_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _make_task(root)

            result = inspect_task("TASK-9001", work_root=root / "work")

            self.assertEqual(result["state.json"]["state"], "review")
            self.assertEqual(len(result["acceptance_criteria"]), 2)

    def test_mcp_evidence_gate_tool_uses_same_service(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _make_task(root)
            report = _write_gate_input(root)
            server = AhraMCPServer()

            inspected = asyncio.run(
                server.call_tool(
                    "ahra.task_inspect",
                    {"taskId": "TASK-9001", "workRoot": str(root / "work")},
                )
            )
            self.assertEqual(len(inspected["acceptance_criteria"]), 2)

            result = asyncio.run(
                server.call_tool(
                    "ahra.evidence_gate_evaluate",
                    {
                        "taskId": "TASK-9001",
                        "workRoot": str(root / "work"),
                        "expectedVersion": 4,
                        "reportPath": str(report),
                        "actor": "agent:verifier",
                    },
                )
            )
            self.assertEqual(result["state"], "completed")


if __name__ == "__main__":
    unittest.main()
