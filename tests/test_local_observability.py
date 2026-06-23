from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ahra.local_observability import (
    LocalObservabilityError,
    deterministic_json_bytes,
    publish_local_record,
)
from ahra.validation import validate_document


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "contracts" / "schemas" / "local-observability-record.schema.json"


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _make_task(root: Path, task_id: str = "TASK-9008") -> Path:
    task_dir = root / "work" / "tasks" / task_id
    task_dir.mkdir(parents=True)
    _write_json(
        task_dir / "artifact-manifest.json",
        {"schema_version": "awkp/0.1", "task_id": task_id, "artifacts": []},
    )
    _write_json(
        task_dir / "evidence-manifest.json",
        {"schema_version": "awkp/0.1", "task_id": task_id, "evidence": []},
    )
    _write_json(
        task_dir / "state.json",
        {
            "schema_version": "awkp/0.1",
            "task_id": task_id,
            "context_id": "CTX-local-observability-test",
            "state": "working",
            "state_version": 2,
            "owner": "agent:codex",
            "attempt": 1,
            "lease": {
                "holder": "agent:codex",
                "acquired_at": "2026-06-23T00:00:00Z",
                "heartbeat_at": "2026-06-23T00:00:00Z",
                "expires_at": "2026-06-23T00:10:00Z",
            },
            "next_action": "Publish local records.",
            "pause_reason": None,
            "blockers": [],
            "artifact_refs": [],
            "evidence_refs": [],
            "updated_at": "2026-06-23T00:00:00Z",
        },
    )
    return task_dir


def _audit_record(task_id: str = "TASK-9008") -> dict:
    return {
        "schema_version": "ahra/local-observability-record/0.1",
        "record_type": "audit_event",
        "record_id": "LREC-audit-TASK-9008-0001",
        "task_id": task_id,
        "run_id": "RUN-local-observability-test",
        "context_id": "CTX-local-observability-test",
        "created_at": "2026-06-23T00:00:00Z",
        "created_by": "agent:codex",
        "refs": {"tasks": [task_id]},
        "payload": {
            "event_type": "local_record_published",
            "actor": "agent:codex",
            "action": "publish_local_record",
            "resource": "local://local-records/",
            "status": "observed",
            "reason": "Record attached to local manifests.",
        },
    }


def _eval_record(task_id: str = "TASK-9008") -> dict:
    return {
        "schema_version": "ahra/local-observability-record/0.1",
        "record_type": "eval_result",
        "record_id": "LREC-eval-TASK-9008-0001",
        "task_id": task_id,
        "run_id": "RUN-local-observability-test",
        "context_id": "CTX-local-observability-test",
        "created_at": "2026-06-23T00:00:01Z",
        "created_by": "agent:codex",
        "refs": {"tasks": [task_id]},
        "payload": {
            "suite_ref": "local://tests/test_local_observability.py",
            "target_ref": "ahra/local-observability-record/0.1",
            "status": "passed",
            "passed": 1,
            "failed": 0,
            "cases": [
                {
                    "name": "schema-valid",
                    "status": "passed",
                    "evidence_refs": [],
                    "notes": "Generated record validates against schema.",
                }
            ],
        },
    }


class LocalObservabilityTests(unittest.TestCase):
    def test_examples_validate_against_schema(self) -> None:
        for name in [
            "local-audit-event.json",
            "local-trace-summary.json",
            "local-usage-summary.json",
            "local-eval-result.json",
        ]:
            with self.subTest(name=name):
                errors = validate_document(ROOT / "examples" / "records" / name, SCHEMA)
                self.assertEqual(errors, [])

    def test_publish_record_is_content_addressed_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            task_dir = _make_task(Path(temp))
            record = _audit_record()

            first = publish_local_record(task_dir, record, input_refs=["task.md"])
            second = publish_local_record(task_dir, record, input_refs=["task.md"])

            self.assertEqual(first.sha256, second.sha256)
            self.assertEqual(first.artifact_record["artifact_id"], second.artifact_record["artifact_id"])
            self.assertEqual(first.path.name, f"audit-event-{first.sha256[:16]}.json")
            self.assertEqual(first.path.read_bytes(), deterministic_json_bytes(record))
            self.assertEqual(validate_document(first.path, SCHEMA), [])
            manifest = json.loads((task_dir / "artifact-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(manifest["artifacts"]), 1)
            self.assertEqual(manifest["artifacts"][0]["sha256"], first.sha256)

    def test_eval_result_can_be_attached_as_evidence_without_state_change(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            task_dir = _make_task(Path(temp))
            state_before = (task_dir / "state.json").read_bytes()

            published = publish_local_record(task_dir, _eval_record(), evidence=True)

            self.assertEqual((task_dir / "state.json").read_bytes(), state_before)
            self.assertIsNotNone(published.evidence_record)
            artifact_manifest = json.loads(
                (task_dir / "artifact-manifest.json").read_text(encoding="utf-8")
            )
            evidence_manifest = json.loads(
                (task_dir / "evidence-manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(artifact_manifest["artifacts"][0]["evidence_refs"], [
                published.evidence_record["evidence_id"]
            ])
            self.assertEqual(evidence_manifest["evidence"][0]["sha256"], published.sha256)

    def test_private_thought_chain_fields_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            task_dir = _make_task(Path(temp))
            record = _audit_record()
            record["payload"]["private_chain_of_thought"] = "do not persist"

            with self.assertRaisesRegex(LocalObservabilityError, "private thought-chain"):
                publish_local_record(task_dir, record)


if __name__ == "__main__":
    unittest.main()
