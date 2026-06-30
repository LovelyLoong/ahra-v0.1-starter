from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import yaml

from ahra import cli
from ahra.evidence_v2 import DigestRef, EvidenceEnvironment, EvidenceResult, EvidenceV2
from ahra.goal_operations import (
    DeterministicGoalVerificationService,
    GoalAwkpBridge,
    GoalAwkpBridgeRequest,
    GoalOperationError,
    GoalOperationService,
)
from ahra.plan_execution import PlanExecutionService, PlanExecutionStatus
from ahra.ports import GoalAwkpBridgePort
from ahra.sqlite_control_store import SQLiteControlStore


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "m1" / "goal-run-request.yaml"
COMMAND_GATE_EXAMPLE = ROOT / "examples" / "m1" / "goal-run-request-command-gate.yaml"
D1 = "sha256:" + "1" * 64
D2 = "sha256:" + "2" * 64
D3 = "sha256:" + "3" * 64
D4 = "sha256:" + "4" * 64


def _evidence(
    evidence_id: str,
    claim_ref: str,
    *,
    result: EvidenceResult = EvidenceResult.PASSED,
    stored: bool = True,
) -> EvidenceV2:
    record = EvidenceV2(
        evidence_id=evidence_id,
        claim_refs=(claim_ref,),
        gate_ref=f"GATE-{claim_ref}",
        gate_definition_digest=D1,
        gate_run_id=f"GRUN-{evidence_id}",
        result=result,
        confidence="verified",
        subjects=(DigestRef(ref=f"ART-{claim_ref}", digest=D2),),
        dependencies=(),
        environment=EvidenceEnvironment(
            runtime_profile_digest=D1,
            policy_digest=D2,
            verifier_release_digest=D3,
            test_definition_digest=D4,
        ),
    )
    return replace(record, stored_fingerprint=record.fingerprint() if stored else None)


def _run_cli(argv: list[str]) -> tuple[int, dict]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = cli.main(argv)
    payload = json.loads(stdout.getvalue() or stderr.getvalue())
    return code, payload


def _run_cli_subprocess(argv: list[str]) -> tuple[int, dict]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    completed = subprocess.run(
        [sys.executable, "-m", "ahra.cli", *argv],
        check=False,
        text=True,
        capture_output=True,
        env=env,
    )
    payload = json.loads(completed.stdout or completed.stderr)
    return completed.returncode, payload


def _copy_request(root: Path) -> Path:
    request = root / "goal-run-request.yaml"
    shutil.copyfile(EXAMPLE, request)
    return request


def _copy_command_gate_request(root: Path) -> Path:
    request = root / "goal-run-request-command-gate.yaml"
    shutil.copyfile(COMMAND_GATE_EXAMPLE, request)
    return request


def _mutate_request(path: Path, mutator) -> None:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    mutator(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _write_bridge_task(root: Path, *, task_id: str = "TASK-BRIDGE") -> Path:
    task_dir = root / "work" / "tasks" / task_id
    task_dir.mkdir(parents=True)
    (task_dir / "evidence").mkdir()
    (task_dir / "handoffs").mkdir()
    (task_dir / "task.md").write_text(
        f"""---
type: WorkItem
id: {task_id}
schema_version: awkp/0.1
title: Bridge task
description: Temporary bridge task.
context_id: CTX-bridge-test
priority: P1
risk_level: R2
requester: human:maintainer
reviewer: agent:verifier
created_at: 2026-06-29T00:00:00Z
depends_on: []
input_refs: []
output_contract: []
---

# Goal

Bridge a completed GoalExecution.

# Acceptance criteria

- [ ] The command-backed GoalExecution evidence is accepted by EvidenceGate.
""",
        encoding="utf-8",
    )
    (task_dir / "state.json").write_text(
        json.dumps(
            {
                "schema_version": "awkp/0.1",
                "task_id": task_id,
                "context_id": "CTX-bridge-test",
                "state": "working",
                "state_version": 1,
                "owner": "agent:producer",
                "attempt": 1,
                "lease": {
                    "holder": "agent:producer",
                    "fencing_token": "FENCE-bridge",
                    "acquired_at": "2026-06-29T00:01:00Z",
                    "heartbeat_at": "2026-06-29T00:01:00Z",
                    "expires_at": None,
                },
                "next_action": "Await GoalExecution bridge.",
                "pause_reason": None,
                "blockers": [],
                "artifact_refs": [],
                "evidence_refs": [],
                "updated_at": "2026-06-29T00:01:00Z",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (task_dir / "artifact-manifest.json").write_text(
        json.dumps({"schema_version": "awkp/0.1", "task_id": task_id, "artifacts": []}, indent=2) + "\n",
        encoding="utf-8",
    )
    (task_dir / "evidence-manifest.json").write_text(
        json.dumps({"schema_version": "awkp/0.1", "task_id": task_id, "evidence": []}, indent=2) + "\n",
        encoding="utf-8",
    )
    events = [
        {
            "schema_version": "awkp/0.1",
            "event_id": f"EVT-{task_id}-0001",
            "idempotency_key": f"{task_id}:created",
            "task_id": task_id,
            "context_id": "CTX-bridge-test",
            "event_type": "task_created",
            "actor": "human:maintainer",
            "occurred_at": "2026-06-29T00:00:00Z",
            "causation_id": None,
            "correlation_id": "CTX-bridge-test",
            "from_state": None,
            "to_state": "ready",
            "reason": "Created for bridge test.",
            "refs": ["task.md"],
        },
        {
            "schema_version": "awkp/0.1",
            "event_id": f"EVT-{task_id}-0002",
            "idempotency_key": f"{task_id}:lease",
            "task_id": task_id,
            "context_id": "CTX-bridge-test",
            "event_type": "lease_acquired",
            "actor": "agent:producer",
            "occurred_at": "2026-06-29T00:01:00Z",
            "causation_id": f"EVT-{task_id}-0001",
            "correlation_id": "CTX-bridge-test",
            "from_state": "ready",
            "to_state": "working",
            "reason": "Producer claimed bridge task.",
            "refs": ["state.json"],
            "expected_version": 0,
            "new_state_version": 1,
            "lease_fencing_token": "FENCE-bridge",
        },
    ]
    (task_dir / "events.jsonl").write_text(
        "".join(json.dumps(event, separators=(",", ":")) + "\n" for event in events),
        encoding="utf-8",
    )
    return task_dir


def _command_evidence_ref(artifact_dir: Path) -> str:
    for path in sorted((artifact_dir / "kernel-evidence").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data["spec"]["gateRef"] == "GATE-command-sentinel":
            return data["metadata"]["evidenceId"]
    raise AssertionError("command-backed EvidenceV2 was not materialized")


def _write_bridge_gate_input(root: Path, *, task_id: str, evidence_ref: str) -> Path:
    report = {
        "schema_version": "ahra/evidence-gate-input/0.1",
        "task_id": task_id,
        "verifier": "agent:verifier",
        "decision": "approve",
        "summary": "Verifier mapped the AWKP criterion to kernel GateRun evidence.",
        "criteria": [
            {
                "criterion_index": 1,
                "status": "passed",
                "evidence_refs": [evidence_ref],
                "command_refs": ["CMD-command-gate"],
                "notes": "The command-backed GoalExecution gate passed.",
            }
        ],
        "commands": [
            {
                "command_id": "CMD-command-gate",
                "command": "python -c COMMAND_GATE_OK",
                "status": "passed",
                "criterion_indices": [1],
                "evidence_refs": [evidence_ref],
            }
        ],
    }
    path = root / "awkp-gate-input.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return path


class GoalOperationCliTests(unittest.TestCase):
    def test_validate_plan_start_resume_inspect_and_terminal_cancel(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request = _copy_request(root)

            validate_code, validate_payload = _run_cli(["goal", "validate", str(request)])
            self.assertEqual(validate_code, 0)
            self.assertTrue(validate_payload["result"]["valid"])
            goal_execution_id = validate_payload["result"]["goalExecutionId"]

            plan_code, plan_payload = _run_cli(["goal", "plan", str(request)])
            self.assertEqual(plan_code, 0)
            self.assertEqual(plan_payload["result"]["executedNodeCount"], 0)
            self.assertTrue((root / ".ahra" / "artifacts" / "plan-ir.json").exists())

            start_code, start_payload = _run_cli(["goal", "start", str(request), "--run-once"])
            self.assertEqual(start_code, 0)
            self.assertEqual(start_payload["result"]["goalStatus"], "running")
            self.assertEqual(start_payload["result"]["planStatus"], "running")
            self.assertTrue((root / "workspace" / "outputs" / "summary.txt").exists())

            resume_code, resume_payload = _run_cli_subprocess(
                ["goal", "resume", goal_execution_id, "--request", str(request)]
            )
            self.assertEqual(resume_code, 0)
            self.assertEqual(resume_payload["result"]["goalStatus"], "succeeded")
            self.assertEqual(resume_payload["result"]["planStatus"], "succeeded")
            self.assertEqual(
                resume_payload["result"]["inspect"]["metrics"]["nodeStatusCounts"],
                {"succeeded": 2},
            )
            self.assertGreaterEqual(resume_payload["result"]["inspect"]["metrics"]["evidenceRefCount"], 2)
            self.assertEqual(resume_payload["result"]["inspect"]["metrics"]["capabilityGrantRefCount"], 1)

            db = root / ".ahra" / "goal-control.sqlite3"
            inspect_code, inspect_payload = _run_cli(["goal", "inspect", goal_execution_id, "--db", str(db)])
            self.assertEqual(inspect_code, 0)
            self.assertEqual(inspect_payload["result"]["metrics"]["goalStatus"], "succeeded")

            (root / "workspace" / "outputs" / "summary.txt").unlink()
            missing_code, missing_payload = _run_cli(["goal", "inspect", goal_execution_id, "--db", str(db)])
            self.assertEqual(missing_code, 0)
            self.assertEqual(missing_payload["result"]["metrics"]["missingArtifactCount"], 1)

            cancel_code, cancel_payload = _run_cli(
                ["goal", "cancel", goal_execution_id, "--db", str(db), "--reason", "terminal negative"]
            )
            self.assertEqual(cancel_code, 2)
            self.assertEqual(cancel_payload["code"], "cancel_terminal_goal")

    def test_goal_validate_does_not_import_dynamic_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            request = _copy_request(Path(temp))
            sys.modules.pop("ahra.dynamic_fixture", None)

            code, payload = _run_cli(["goal", "validate", str(request)])

            self.assertEqual(code, 0)
            self.assertTrue(payload["result"]["valid"])
            self.assertNotIn("ahra.dynamic_fixture", sys.modules)

    def test_unknown_and_invalid_goal_request_refs_fail_closed(self) -> None:
        cases = [
            (
                "legacy_profile_not_default",
                lambda data: data["spec"].__setitem__("profileRef", "standard-harness"),
            ),
            (
                "unknown_planner_adapter",
                lambda data: data["spec"]["planner"].__setitem__(
                    "adapterRef",
                    "planner/unknown@sha256:9999999999999999999999999999999999999999999999999999999999999999",
                ),
            ),
            (
                "unknown_executor_adapter",
                lambda data: data["spec"]["executor"].__setitem__(
                    "adapterRef",
                    "executor/unknown@sha256:9999999999999999999999999999999999999999999999999999999999999999",
                ),
            ),
            (
                "unknown_gate_runner",
                lambda data: data["spec"]["gateRunner"].__setitem__(
                    "adapterRef",
                    "gate-runner/unknown@sha256:9999999999999999999999999999999999999999999999999999999999999999",
                ),
            ),
            (
                "unknown_runtime_ref",
                lambda data: data["spec"]["runtime"].__setitem__(
                    "runtimeRef",
                    "runtime/unknown@sha256:9999999999999999999999999999999999999999999999999999999999999999",
                ),
            ),
            (
                "invalid_digest",
                lambda data: data["spec"]["goal"].__setitem__("goalDigest", "sha256:not-a-digest"),
            ),
        ]
        for expected_code, mutator in cases:
            with self.subTest(expected_code=expected_code), tempfile.TemporaryDirectory() as temp:
                request = _copy_request(Path(temp))
                _mutate_request(request, mutator)

                code, payload = _run_cli(["goal", "validate", str(request)])

                self.assertEqual(code, 2)
                self.assertEqual(payload["code"], expected_code)

    def test_resume_requires_existing_sqlite_store(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            request = _copy_request(Path(temp))
            _, payload = _run_cli(["goal", "validate", str(request)])
            goal_execution_id = payload["result"]["goalExecutionId"]

            code, error_payload = _run_cli(["goal", "resume", goal_execution_id, "--request", str(request)])

            self.assertEqual(code, 2)
            self.assertEqual(error_payload["code"], "missing_sqlite_database")

    def test_duplicate_start_idempotency_key_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            request = _copy_request(Path(temp))

            first_code, _ = _run_cli(["goal", "start", str(request)])
            second_code, second_payload = _run_cli(["goal", "start", str(request)])

            self.assertEqual(first_code, 0)
            self.assertEqual(second_code, 2)
            self.assertEqual(second_payload["code"], "duplicate_start_idempotency_key")

    def test_real_command_gate_failure_records_defect_then_fixed_input_completes_goal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            fail_root = Path(temp) / "fail"
            pass_root = Path(temp) / "pass"
            fail_root.mkdir()
            pass_root.mkdir()

            fail_request = _copy_command_gate_request(fail_root)
            fail_input = fail_root / "workspace" / "inputs" / "command-gate.txt"
            fail_input.parent.mkdir(parents=True)
            fail_input.write_text("broken\n", encoding="utf-8")

            fail_code, fail_payload = _run_cli(["goal", "start", str(fail_request)])

            self.assertEqual(fail_code, 0)
            fail_result = fail_payload["result"]
            self.assertEqual(fail_result["planStatus"], "failed")
            self.assertEqual(fail_result["goalStatus"], "repairing")
            self.assertFalse(fail_result["completion"]["complete"])
            self.assertEqual(
                fail_result["completion"]["openDefectRefs"],
                fail_result["inspect"]["goalExecution"]["open_defect_refs"],
            )
            self.assertEqual(len(fail_result["defects"]), 1)
            defect = fail_result["defects"][0]
            self.assertEqual(defect["kind"], "DefectRecord")
            self.assertEqual(defect["spec"]["gateRef"], "GATE-command-sentinel")
            self.assertEqual(defect["spec"]["status"], "open")
            self.assertIn(defect["metadata"]["defectId"], fail_result["inspect"]["goalExecution"]["open_defect_refs"])
            failed_command_node = next(
                node for node in fail_result["inspect"]["nodeRuns"] if node["node_id"] == "NODE-command-gate"
            )
            self.assertEqual(failed_command_node["status"], "failed")
            self.assertEqual(failed_command_node["failure_class"], "gate_execution_failed")
            self.assertEqual(failed_command_node["gate_refs"], ["GATE-command-sentinel"])
            self.assertTrue(failed_command_node["evidence_refs"])
            failed_raw_path = (
                fail_root
                / ".ahra"
                / "artifacts"
                / "verification"
                / "GATE-command-sentinel"
                / "attempt-1-command-output.json"
            )
            failed_raw = json.loads(failed_raw_path.read_text(encoding="utf-8"))
            self.assertEqual(failed_raw["status"], "failed")
            self.assertEqual(failed_raw["failureClass"], "unexpected_exit_code")
            self.assertEqual(failed_raw["exitCode"], 1)
            self.assertIn("COMMAND_GATE_BAD:broken", failed_raw["stdout"])

            pass_request = _copy_command_gate_request(pass_root)
            pass_input = pass_root / "workspace" / "inputs" / "command-gate.txt"
            pass_input.parent.mkdir(parents=True)
            pass_input.write_text("fixed\n", encoding="utf-8")

            pass_code, pass_payload = _run_cli(["goal", "start", str(pass_request)])

            self.assertEqual(pass_code, 0)
            pass_result = pass_payload["result"]
            self.assertEqual(pass_result["planStatus"], "succeeded")
            self.assertEqual(pass_result["goalStatus"], "succeeded")
            self.assertTrue(pass_result["completion"]["complete"])
            self.assertEqual(pass_result["defects"], [])
            self.assertEqual(pass_result["inspect"]["goalExecution"]["open_defect_refs"], [])
            passed_command_node = next(
                node for node in pass_result["inspect"]["nodeRuns"] if node["node_id"] == "NODE-command-gate"
            )
            self.assertEqual(passed_command_node["status"], "succeeded")
            self.assertEqual(passed_command_node["gate_refs"], ["GATE-command-sentinel"])
            self.assertTrue(passed_command_node["evidence_refs"])
            passed_raw_path = (
                pass_root
                / ".ahra"
                / "artifacts"
                / "verification"
                / "GATE-command-sentinel"
                / "attempt-1-command-output.json"
            )
            passed_raw = json.loads(passed_raw_path.read_text(encoding="utf-8"))
            self.assertEqual(passed_raw["status"], "passed")
            self.assertIsNone(passed_raw["failureClass"])
            self.assertEqual(passed_raw["exitCode"], 0)
            self.assertIn("COMMAND_GATE_OK", passed_raw["stdout"])
            self.assertTrue(pass_result["kernelVerification"]["evidenceRecords"])
            self.assertTrue(pass_result["kernelVerification"]["gateRuns"])

    def test_goal_awkp_bridge_associates_goal_and_completes_task_through_evidence_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            goal_root = root / "goal"
            goal_root.mkdir()
            task_dir = _write_bridge_task(root)
            request_path = _copy_command_gate_request(goal_root)
            gate_input = goal_root / "workspace" / "inputs" / "command-gate.txt"
            gate_input.parent.mkdir(parents=True)
            gate_input.write_text("fixed\n", encoding="utf-8")

            start_code, start_payload = _run_cli(["goal", "start", str(request_path)])

            self.assertEqual(start_code, 0)
            start_result = start_payload["result"]
            self.assertEqual(start_result["goalStatus"], "succeeded")
            artifact_dir = goal_root / ".ahra" / "artifacts"
            evidence_ref = _command_evidence_ref(artifact_dir)
            report_path = _write_bridge_gate_input(root, task_id="TASK-BRIDGE", evidence_ref=evidence_ref)

            bridge = GoalAwkpBridge(work_root=root / "work")
            self.assertIsInstance(bridge, GoalAwkpBridgePort)
            result = bridge.run(
                GoalAwkpBridgeRequest(
                    goal_execution_id=start_result["goalExecutionId"],
                    task="TASK-BRIDGE",
                    work_root=root / "work",
                    expected_task_version=1,
                    producer_actor="agent:producer",
                    verifier_actor="agent:verifier",
                    fencing_token="FENCE-bridge",
                    report_paths=(report_path,),
                    db_path=goal_root / ".ahra" / "goal-control.sqlite3",
                    artifact_dir=artifact_dir,
                    idempotency_key_prefix="TASK-BRIDGE:goal-awkp-test",
                )
            )

            self.assertEqual(result.goal_status, "succeeded")
            self.assertEqual(result.orchestration.terminal_state, "completed")
            self.assertIn(evidence_ref, result.materialization.kernel_evidence_refs)
            state = json.loads((task_dir / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["state"], "completed")
            self.assertIn(evidence_ref, state["evidence_refs"])
            events = [
                json.loads(line)
                for line in (task_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(
                [event["event_type"] for event in events[-3:]],
                ["goal_awkp_associated", "review_requested", "evidence_gate_approved"],
            )
            self.assertEqual(events[-3]["goal_execution_id"], start_result["goalExecutionId"])
            evidence_manifest = json.loads((task_dir / "evidence-manifest.json").read_text(encoding="utf-8"))
            artifact_manifest = json.loads((task_dir / "artifact-manifest.json").read_text(encoding="utf-8"))
            self.assertIn(evidence_ref, {record["evidence_id"] for record in evidence_manifest["evidence"]})
            self.assertIn("kernel_gate_run_v2", {record["kind"] for record in artifact_manifest["artifacts"]})

    def test_goal_awkp_bridge_rejects_same_producer_and_verifier_before_state_write(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            task_dir = _write_bridge_task(root)
            before = (task_dir / "state.json").read_text(encoding="utf-8")

            with self.assertRaisesRegex(GoalOperationError, "distinct producer and verifier"):
                GoalAwkpBridge(work_root=root / "work").run(
                    GoalAwkpBridgeRequest(
                        goal_execution_id="GEXEC-missing",
                        task="TASK-BRIDGE",
                        work_root=root / "work",
                        expected_task_version=1,
                        producer_actor="agent:same",
                        verifier_actor="agent:same",
                        fencing_token="FENCE-bridge",
                        report_paths=(root / "missing-report.json",),
                        db_path=root / "missing.sqlite3",
                        artifact_dir=root / "artifacts",
                    )
                )

            self.assertEqual((task_dir / "state.json").read_text(encoding="utf-8"), before)

    def test_finish_active_plan_if_terminal_finalizes_failed_goal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            request_path = _copy_request(Path(temp))
            service = GoalOperationService()
            service.plan(request_path)
            bundle = service.plan_bundle(request_path)
            assert bundle.plan is not None
            request = bundle.request
            store = SQLiteControlStore(request.store_path)
            plan_service = PlanExecutionService(store)  # type: ignore[arg-type]
            goal = plan_service.create_goal_execution(
                goal_ref=request.goal_ref,
                goal_digest=request.goal_digest,
                claim_graph_digest=request.claim_graph_digest,
                claim_graph_ref=request.claim_graph_ref,
                goal_execution_id=request.goal_execution_id,
                max_repair_cycles=request.max_repair_cycles,
                budget_summary={"profileRef": request.profile_ref},
                workspace_ref=str(request.workspace_ref),
            )
            execution = plan_service.start_execution(
                bundle.plan,
                bundle.validation_report,
                goal_execution_ref=goal.goal_execution_id,
                max_concurrency=request.max_concurrency,
            )
            plan_service.attach_plan_execution(
                goal.goal_execution_id,
                execution.plan_execution_id,
                expected_version=goal.status_version,
            )
            running = plan_service.transition_execution(
                execution.plan_execution_id,
                PlanExecutionStatus.RUNNING,
                expected_version=execution.status_version,
                message="Static PlanIR DAG scheduling started.",
            )
            plan_service.transition_execution(
                running.plan_execution_id,
                PlanExecutionStatus.FAILED,
                expected_version=running.status_version,
                failure_class="timeout",
                message="Node executor timed out.",
            )

            finalized = service.finish_active_plan_if_terminal(
                request.goal_execution_id,
                db_path=request.store_path,
            )
            second = service.finish_active_plan_if_terminal(
                request.goal_execution_id,
                db_path=request.store_path,
            )

            self.assertEqual(finalized.status.value, "failed")
            self.assertIsNone(finalized.active_plan_execution_ref)
            self.assertEqual(finalized.failure_class, "timeout")
            self.assertEqual(second.status.value, "failed")

    def test_completion_service_derives_from_current_evidence(self) -> None:
        failing_service = DeterministicGoalVerificationService.from_required_claim_refs(
            goal_ref="GOAL-evidence-derived",
            required_claim_refs=("CLAIM-a", "CLAIM-b"),
            evidence_records=lambda: (
                _evidence("EVD-a-pass", "CLAIM-a"),
                _evidence("EVD-b-fail", "CLAIM-b", result=EvidenceResult.FAILED),
            ),
        )

        failing = failing_service.complete()

        self.assertFalse(failing.complete)
        self.assertEqual(failing.uncovered_claim_refs, ("CLAIM-b",))
        self.assertEqual(failing.current_claim_coverage, 0.5)

        passing_service = DeterministicGoalVerificationService.from_required_claim_refs(
            goal_ref="GOAL-evidence-derived",
            required_claim_refs=("CLAIM-a", "CLAIM-b"),
            evidence_records=lambda: (
                _evidence("EVD-a-pass", "CLAIM-a"),
                _evidence("EVD-b-pass", "CLAIM-b"),
            ),
        )

        passing = passing_service.complete()

        self.assertTrue(passing.complete)
        self.assertEqual(passing.current_claim_coverage, 1.0)

    def test_finish_active_plan_uses_derived_incomplete_result_without_goal_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            request_path = _copy_request(Path(temp))
            service = GoalOperationService()
            bundle = service.plan_bundle(request_path)
            assert bundle.plan is not None
            request = bundle.request
            store = SQLiteControlStore(request.store_path)
            plan_service = PlanExecutionService(store)  # type: ignore[arg-type]
            goal = plan_service.create_goal_execution(
                goal_ref=request.goal_ref,
                goal_digest=request.goal_digest,
                claim_graph_digest=request.claim_graph_digest,
                claim_graph_ref=request.claim_graph_ref,
                goal_execution_id=request.goal_execution_id,
                max_repair_cycles=request.max_repair_cycles,
                budget_summary={"profileRef": request.profile_ref},
                workspace_ref=str(request.workspace_ref),
            )
            execution = plan_service.start_execution(
                bundle.plan,
                bundle.validation_report,
                goal_execution_ref=goal.goal_execution_id,
                max_concurrency=request.max_concurrency,
            )
            plan_service.attach_plan_execution(
                goal.goal_execution_id,
                execution.plan_execution_id,
                expected_version=goal.status_version,
            )
            running = plan_service.transition_execution(
                execution.plan_execution_id,
                PlanExecutionStatus.RUNNING,
                expected_version=execution.status_version,
                message="Static PlanIR DAG scheduling started.",
            )
            verifying = plan_service.transition_execution(
                running.plan_execution_id,
                PlanExecutionStatus.VERIFYING,
                expected_version=running.status_version,
                evidence_refs=("EVD-a-pass", "EVD-b-fail"),
                message="Plan entered final verification.",
            )
            succeeded = plan_service.transition_execution(
                verifying.plan_execution_id,
                PlanExecutionStatus.SUCCEEDED,
                expected_version=verifying.status_version,
                evidence_refs=("EVD-a-pass", "EVD-b-fail"),
                message="Plan finished, but goal completion must still be derived.",
            )
            completion_service = DeterministicGoalVerificationService.from_required_claim_refs(
                goal_ref=request.goal_ref,
                required_claim_refs=request.required_claim_refs,
                evidence_records=lambda: (
                    _evidence("EVD-a-pass", request.required_claim_refs[0]),
                    _evidence("EVD-b-fail", request.required_claim_refs[1], result=EvidenceResult.FAILED),
                ),
            )

            finalized = service._finish_goal_if_ready(
                plan_service,
                request.goal_execution_id,
                succeeded.plan_execution_id,
                completion=completion_service.complete(),
            )

            self.assertEqual(finalized.status.value, "verifying")
            self.assertIsNone(finalized.active_plan_execution_ref)
            self.assertIn("EVD-b-fail", finalized.evidence_refs)
            self.assertIn("incomplete", finalized.message)


if __name__ == "__main__":
    unittest.main()
