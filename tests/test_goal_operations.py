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
from ahra.goal_operations import DeterministicGoalVerificationService, GoalOperationService
from ahra.plan_execution import PlanExecutionService, PlanExecutionStatus
from ahra.sqlite_control_store import SQLiteControlStore


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "m1" / "goal-run-request.yaml"
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


def _mutate_request(path: Path, mutator) -> None:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    mutator(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


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
