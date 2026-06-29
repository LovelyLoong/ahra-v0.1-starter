from __future__ import annotations

import ast
import hashlib
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from ahra.awkp_state_writer import (
    AwkpTaskStateCasError,
    AwkpTaskStateFenceError,
    AwkpTaskStateIdempotencyError,
    AwkpTaskStateWriter,
)
from ahra.evidence_gate import EvidenceGateError, evaluate_task_gate, inspect_task
from ahra.ports import AwkpTaskStateWriterPort


D1 = "sha256:" + "1" * 64
D2 = "sha256:" + "2" * 64
D3 = "sha256:" + "3" * 64
D4 = "sha256:" + "4" * 64
D5 = "sha256:" + "5" * 64
D6 = "sha256:" + "6" * 64
D7 = "sha256:" + "7" * 64


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _append_event(path: Path, event: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")


def _canonical(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _fingerprint(payload: dict) -> str:
    return "sha256:" + hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _environment() -> dict[str, str | None]:
    return {
        "runtimeProfileDigest": D1,
        "policyDigest": D2,
        "verifierReleaseDigest": D3,
        "testDefinitionDigest": D4,
        "relevantEnvironmentDigest": None,
    }


def _kernel_evidence_docs(task_id: str) -> tuple[str, str, dict, dict]:
    evidence_id = f"EVD-{task_id}-KERNEL"
    gate_run_id = f"GATERUN-{task_id}-KERNEL"
    gate_ref = "GATE-command-check"
    gate_definition_digest = D5
    claim_refs = ["CLAIM-command-backed"]
    subjects = [{"ref": "ART-command-output", "digest": D6}]
    dependencies: list[dict[str, str]] = []
    environment = _environment()
    command = ["uv", "run", "python", "-B", "scripts/check.py", "--lint"]
    gate_run = {
        "apiVersion": "ahra.dev/v1alpha1",
        "kind": "GateRun",
        "metadata": {"gateRunId": gate_run_id},
        "spec": {
            "gateRef": gate_ref,
            "gateDefinitionDigest": gate_definition_digest,
            "claimRefs": claim_refs,
            "result": "passed",
            "subjects": subjects,
            "dependencies": dependencies,
            "environment": environment,
            "validity": {"state": "current", "validUntil": None},
            "command": command,
            "evidenceRef": evidence_id,
        },
    }
    gate_run["spec"]["fingerprint"] = _fingerprint(
        {
            "claimRefs": sorted(claim_refs),
            "command": command,
            "dependencies": dependencies,
            "environment": {
                "policyDigest": environment["policyDigest"],
                "relevantEnvironmentDigest": environment["relevantEnvironmentDigest"],
                "runtimeProfileDigest": environment["runtimeProfileDigest"],
                "testDefinitionDigest": environment["testDefinitionDigest"],
                "verifierReleaseDigest": environment["verifierReleaseDigest"],
            },
            "gateDefinitionDigest": gate_definition_digest,
            "gateRef": gate_ref,
            "subjects": subjects,
        }
    )
    evidence = {
        "apiVersion": "ahra.dev/v1alpha1",
        "kind": "Evidence",
        "metadata": {"evidenceId": evidence_id},
        "spec": {
            "claimRefs": claim_refs,
            "gateRef": gate_ref,
            "gateDefinitionDigest": gate_definition_digest,
            "gateRunId": gate_run_id,
            "result": "passed",
            "confidence": "verified",
            "subjects": subjects,
            "dependencies": dependencies,
            "environment": environment,
            "validity": {"state": "current", "validUntil": None},
            "dependencyScope": "complete",
            "refs": [gate_run_id],
            "supersedes": [],
        },
    }
    evidence["spec"]["fingerprint"] = _fingerprint(
        {
            "claimRefs": sorted(claim_refs),
            "dependencies": dependencies,
            "environment": {
                "policyDigest": environment["policyDigest"],
                "relevantEnvironmentDigest": environment["relevantEnvironmentDigest"],
                "runtimeProfileDigest": environment["runtimeProfileDigest"],
                "testDefinitionDigest": environment["testDefinitionDigest"],
                "verifierReleaseDigest": environment["verifierReleaseDigest"],
            },
            "gateDefinitionDigest": gate_definition_digest,
            "gateRef": gate_ref,
            "subjects": subjects,
        }
    )
    return evidence_id, gate_run_id, evidence, gate_run


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
    kernel_evidence_id, gate_run_id, kernel_evidence, gate_run = _kernel_evidence_docs(task_id)
    _write_json(evidence_dir / "kernel-evidence-v2.json", kernel_evidence)
    _write_json(evidence_dir / "kernel-gate-run-v2.json", gate_run)
    kernel_evidence_sha = hashlib.sha256((evidence_dir / "kernel-evidence-v2.json").read_bytes()).hexdigest()
    gate_run_sha = hashlib.sha256((evidence_dir / "kernel-gate-run-v2.json").read_bytes()).hexdigest()
    artifact_id = f"ART-{task_id}-0001"
    gate_run_artifact_id = f"ART-{task_id}-GATERUN"
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
                },
                {
                    "artifact_id": gate_run_artifact_id,
                    "task_id": task_id,
                    "kind": "kernel_gate_run_v2",
                    "name": "kernel-gate-run-v2.json",
                    "uri": "local://evidence/kernel-gate-run-v2.json",
                    "sha256": gate_run_sha,
                    "media_type": "application/json",
                    "created_by": "agent:codex",
                    "created_at": "2026-06-22T00:03:00Z",
                    "input_refs": ["task.md"],
                    "evidence_refs": [kernel_evidence_id],
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
                },
                {
                    "evidence_id": kernel_evidence_id,
                    "task_id": task_id,
                    "kind": "kernel_evidence_v2",
                    "name": "kernel-evidence-v2.json",
                    "uri": "local://evidence/kernel-evidence-v2.json",
                    "sha256": kernel_evidence_sha,
                    "media_type": "application/json",
                    "created_by": "agent:codex",
                    "created_at": "2026-06-22T00:03:00Z",
                    "refs": [gate_run_artifact_id, gate_run_id],
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


def _make_state_writer_task(root: Path, *, task_id: str = "TASK-9100") -> Path:
    task_dir = root / "work" / "tasks" / task_id
    task_dir.mkdir(parents=True)
    _write_json(
        task_dir / "state.json",
        {
            "schema_version": "awkp/0.1",
            "task_id": task_id,
            "context_id": "CTX-state-writer-test",
            "state": "ready",
            "state_version": 0,
            "owner": None,
            "attempt": 0,
            "lease": None,
            "next_action": "Ready for governed writer test.",
            "pause_reason": None,
            "blockers": [],
            "artifact_refs": [],
            "evidence_refs": [],
            "updated_at": "2026-06-22T00:00:00Z",
        },
    )
    _append_event(
        task_dir / "events.jsonl",
        {
            "schema_version": "awkp/0.1",
            "event_id": f"EVT-{task_id}-0001",
            "idempotency_key": f"{task_id}:created",
            "task_id": task_id,
            "context_id": "CTX-state-writer-test",
            "event_type": "task_created",
            "actor": "human:maintainer",
            "occurred_at": "2026-06-22T00:00:00Z",
            "causation_id": None,
            "correlation_id": "CTX-state-writer-test",
            "from_state": None,
            "to_state": "ready",
            "reason": "Created for governed writer test.",
            "refs": ["task.md"],
        },
    )
    return task_dir


def _write_gate_input(root: Path, *, task_id: str = "TASK-9001", decision: str = "approve") -> Path:
    status = "passed" if decision == "approve" else "failed"
    evidence_refs = [f"EVD-{task_id}-KERNEL"] if decision == "approve" else []
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
                "command_refs": ["CMD-lint"] if decision == "approve" else [],
                "notes": "Checked.",
            },
            {
                "criterion_index": 2,
                "status": "passed" if decision == "approve" else "missing",
                "evidence_refs": evidence_refs if decision == "approve" else [],
                "command_refs": ["CMD-lint"] if decision == "approve" else [],
                "notes": "Checked.",
            },
        ],
        "commands": [
            {
                "command_id": "CMD-lint",
                "command": "uv run python -B scripts\\check.py --lint",
                "status": "passed" if decision == "approve" else "failed",
                "criterion_indices": [1, 2],
                "evidence_refs": evidence_refs,
            }
        ],
    }
    path = root / "gate-input.json"
    _write_json(path, report)
    return path


class EvidenceGateTests(unittest.TestCase):
    def test_awkp_state_writer_governs_cas_fencing_idempotency_and_reclaim(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            task_dir = _make_state_writer_task(root)
            tokens = iter(["FENCE-1", "FENCE-2"])
            writer = AwkpTaskStateWriter(
                work_root=root / "work",
                clock=lambda: "2026-06-22T00:00:00Z",
                token_factory=lambda: next(tokens),
            )
            self.assertIsInstance(writer, AwkpTaskStateWriterPort)

            acquired = writer.acquire_working(
                "TASK-9100",
                expected_version=0,
                actor="agent:producer",
                idempotency_key="TASK-9100:acquire:1",
                reason="Begin governed implementation.",
            )

            self.assertEqual(acquired.state_version, 1)
            self.assertEqual(acquired.fencing_token, "FENCE-1")
            state = json.loads((task_dir / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["state"], "working")
            self.assertEqual(state["state_version"], 1)
            self.assertEqual(state["lease"]["fencing_token"], "FENCE-1")

            with self.assertRaisesRegex(AwkpTaskStateCasError, "expected state_version 0, current 1"):
                writer.acquire_working(
                    "TASK-9100",
                    expected_version=0,
                    actor="agent:producer",
                    idempotency_key="TASK-9100:acquire:stale",
                    reason="Stale writer must fail.",
                )
            state_after_stale = json.loads((task_dir / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state_after_stale["state_version"], 1)
            self.assertEqual(state_after_stale["lease"]["fencing_token"], "FENCE-1")

            with self.assertRaisesRegex(AwkpTaskStateIdempotencyError, "duplicate idempotency_key"):
                writer.request_review(
                    "TASK-9100",
                    expected_version=1,
                    actor="agent:producer",
                    idempotency_key="TASK-9100:acquire:1",
                    fencing_token="FENCE-1",
                    reason="Duplicate idempotency must fail.",
                )
            with self.assertRaisesRegex(AwkpTaskStateFenceError, "fencing token mismatch"):
                writer.request_review(
                    "TASK-9100",
                    expected_version=1,
                    actor="agent:producer",
                    idempotency_key="TASK-9100:review:stale-fence",
                    fencing_token="FENCE-stale",
                    reason="Stale fence must fail.",
                )

            reviewed = writer.request_review(
                "TASK-9100",
                expected_version=1,
                actor="agent:producer",
                idempotency_key="TASK-9100:review:1",
                fencing_token="FENCE-1",
                reason="Implementation evidence is ready for independent review.",
                refs=["state.json", "evidence/governed-state-writer-report.md"],
                artifact_refs=["ART-TASK-9100-0001"],
                evidence_refs=["EVD-TASK-9100-0001"],
            )

            self.assertEqual(reviewed.state_version, 2)
            state = json.loads((task_dir / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["state"], "review")
            self.assertIsNone(state["lease"])
            self.assertIn("ART-TASK-9100-0001", state["artifact_refs"])
            self.assertIn("EVD-TASK-9100-0001", state["evidence_refs"])

            state.update(
                {
                    "state": "changes_requested",
                    "state_version": 3,
                    "next_action": "Reclaim after verifier changes request.",
                    "updated_at": "2026-06-22T00:02:00Z",
                }
            )
            _write_json(task_dir / "state.json", state)
            _append_event(
                task_dir / "events.jsonl",
                {
                    "schema_version": "awkp/0.1",
                    "event_id": "EVT-TASK-9100-0004",
                    "idempotency_key": "TASK-9100:changes-requested:1",
                    "task_id": "TASK-9100",
                    "context_id": "CTX-state-writer-test",
                    "event_type": "evidence_gate_changes_requested",
                    "actor": "agent:verifier",
                    "occurred_at": "2026-06-22T00:02:00Z",
                    "causation_id": "EVT-TASK-9100-0003",
                    "correlation_id": "CTX-state-writer-test",
                    "from_state": "review",
                    "to_state": "changes_requested",
                    "reason": "Verifier requested changes.",
                    "refs": ["state.json"],
                },
            )

            with self.assertRaisesRegex(AwkpTaskStateFenceError, "stale previous fencing token"):
                writer.reclaim_working(
                    "TASK-9100",
                    expected_version=3,
                    actor="agent:producer",
                    idempotency_key="TASK-9100:reclaim:stale-fence",
                    previous_fencing_token="FENCE-stale",
                    reason="Stale previous fence must fail.",
                )

            reclaimed = writer.reclaim_working(
                "TASK-9100",
                expected_version=3,
                actor="agent:producer",
                idempotency_key="TASK-9100:reclaim:1",
                previous_fencing_token="FENCE-1",
                reason="Reclaim after verifier request_changes.",
            )

            self.assertEqual(reclaimed.state_version, 4)
            self.assertEqual(reclaimed.fencing_token, "FENCE-2")
            state = json.loads((task_dir / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["state"], "working")
            self.assertEqual(state["state_version"], 4)
            self.assertEqual(state["lease"]["fencing_token"], "FENCE-2")
            self.assertEqual(state["attempt"], 2)

            events = [
                json.loads(line)
                for line in (task_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            idempotency_keys = [event["idempotency_key"] for event in events]
            self.assertEqual(len(idempotency_keys), len(set(idempotency_keys)))
            occurred_at = [
                datetime.fromisoformat(event["occurred_at"].replace("Z", "+00:00"))
                for event in events
            ]
            self.assertEqual(occurred_at, sorted(occurred_at))
            self.assertEqual(events[-1]["previous_lease_fencing_token"], "FENCE-1")
            self.assertEqual(events[-1]["lease_fencing_token"], "FENCE-2")

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

    def test_rejects_command_backed_pass_without_kernel_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _make_task(root)
            report = _write_gate_input(root)
            data = json.loads(report.read_text(encoding="utf-8"))
            legacy_ref = "EVD-TASK-9001-0001"
            for criterion in data["criteria"]:
                criterion["evidence_refs"] = [legacy_ref]
            data["commands"][0]["evidence_refs"] = [legacy_ref]
            _write_json(report, data)

            with self.assertRaisesRegex(EvidenceGateError, "without kernel EvidenceV2"):
                evaluate_task_gate(
                    "TASK-9001",
                    work_root=root / "work",
                    expected_version=4,
                    report_path=report,
                    actor="agent:verifier",
                )

    def test_rejects_command_backed_pass_with_mismatched_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            task_dir = _make_task(root)
            report = _write_gate_input(root)
            evidence_path = task_dir / "evidence" / "kernel-evidence-v2.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["spec"]["subjects"][0]["digest"] = D7
            _write_json(evidence_path, evidence)
            evidence_sha = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
            manifest_path = task_dir / "evidence-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for record in manifest["evidence"]:
                if record["evidence_id"] == "EVD-TASK-9001-KERNEL":
                    record["sha256"] = evidence_sha
            _write_json(manifest_path, manifest)

            with self.assertRaisesRegex(EvidenceGateError, "fingerprint mismatch"):
                evaluate_task_gate(
                    "TASK-9001",
                    work_root=root / "work",
                    expected_version=4,
                    report_path=report,
                    actor="agent:verifier",
                )

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

    def test_evidence_gate_stays_stdlib_offline(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "src" / "ahra" / "evidence_gate.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".", 1)[0])

        self.assertNotIn("subprocess", imports)
        self.assertNotIn("ahra", imports)

    def test_awkp_state_writer_stays_stdlib_offline(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "src" / "ahra" / "awkp_state_writer.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".", 1)[0])

        self.assertNotIn("subprocess", imports)
        self.assertNotIn("requests", imports)
        self.assertNotIn("yaml", imports)
        self.assertNotIn("ahra", imports)

if __name__ == "__main__":
    unittest.main()
