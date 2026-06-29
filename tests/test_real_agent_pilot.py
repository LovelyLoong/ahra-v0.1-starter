from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import yaml

from ahra.goal_operations import REAL_BOUNDED_EXECUTOR_REF, GoalOperationError, GoalOperationService
from ahra.plan_ir import PlanDraft
from ahra.plan_execution import PlanExecutionService, PlanExecutionStatus
from ahra.ports import AgentDriverRegistry, AgentRole, AgentRunRequest, AgentRunResult
from ahra.real_agent_pilot import PilotMode, RealAgentPilotConfig, RealAgentPilotRunner, _normalize_real_executor_plan_draft
from ahra.reference_runner.models import ExecutionPolicy, WorkReport
from ahra.sqlite_control_store import SQLiteControlStore


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "m1" / "goal-run-request.yaml"
PILOT_SCRIPT = ROOT / "scripts" / "run_real_agent_pilot.py"


class PilotPlannerDriver:
    def __init__(self, draft: dict[str, Any]) -> None:
        self.draft = draft
        self.calls = 0

    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        self.calls += 1
        self.last_request = request
        return AgentRunResult(output=self.draft)


class PilotExecutorDriver:
    def __init__(self) -> None:
        self.executor_calls = 0

    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        if request.role != AgentRole.EXECUTOR:
            raise AssertionError(f"unexpected role: {request.role}")
        self.executor_calls += 1
        workspace = Path(str(request.workspace_ref))
        target = workspace / "outputs" / "summary.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("real executor pilot output\n", encoding="utf-8")
        return AgentRunResult(
            output=WorkReport(
                summary="Pilot executor wrote the bounded output.",
                changed_files=("outputs/summary.txt",),
            )
        )


class RaisingService:
    def validate(self, request_path: Path) -> dict[str, Any]:
        return {"valid": True}

    def start(self, request_path: Path) -> dict[str, Any]:
        raise RuntimeError("adapter exploded")


class RealAgentPilotTests(unittest.TestCase):
    def test_mode_a_real_planner_output_is_admitted_before_goal_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            registry = AgentDriverRegistry()
            planner = PilotPlannerDriver(_template_draft())
            registry.register("pilot-planner", planner)

            scorecard = RealAgentPilotRunner(planner_registry=registry).run(
                RealAgentPilotConfig(
                    experiment_id="PILOT-A",
                    mode=PilotMode.REAL_PLANNER,
                    request_template=EXAMPLE,
                    output_dir=Path(temp),
                    repetitions=1,
                    planner_driver_ref="pilot-planner",
                )
            )

            self.assertEqual(planner.calls, 1)
            self.assertEqual(scorecard["success_count"], 1)
            run = scorecard["runs"][0]
            self.assertEqual(run["planner"]["status"], "accepted")
            self.assertEqual(run["execution"]["status"], "succeeded")
            planner_payload = planner.last_request.payload["plannerInputArtifact"]["payload"]
            self.assertEqual(planner_payload["allowedCapabilities"], ["filesystem.write"])
            self.assertTrue((Path(temp) / "run-01" / ".ahra" / "artifacts" / "planner-admission-report.json").exists())

    def test_mode_a_rejects_bad_planner_output_without_starting_goal_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            bad_draft = _template_draft()
            for node in bad_draft["spec"]["nodes"]:
                node["claimRefs"] = [claim for claim in node["claimRefs"] if claim != "CLM-GOAL-COMPLETE"]
            registry = AgentDriverRegistry()
            registry.register("pilot-planner", PilotPlannerDriver(bad_draft))

            scorecard = RealAgentPilotRunner(planner_registry=registry).run(
                RealAgentPilotConfig(
                    experiment_id="PILOT-A-BAD",
                    mode=PilotMode.REAL_PLANNER,
                    request_template=EXAMPLE,
                    output_dir=Path(temp),
                    repetitions=1,
                    planner_driver_ref="pilot-planner",
                )
            )

            run = scorecard["runs"][0]
            self.assertEqual(scorecard["success_count"], 0)
            self.assertEqual(run["status"], "rejected")
            self.assertEqual(run["planner"]["failureClass"], "planner_output_rejected")
            self.assertEqual(run["workflow_failure_dimension"], "model_behavior")
            self.assertEqual(scorecard["workflow_failure_dimensions"]["counts"]["model_behavior"], 1)
            self.assertFalse((Path(temp) / "run-01" / ".ahra" / "goal-control.sqlite3").exists())

    def test_mode_b_records_adapter_blocker_when_real_executor_driver_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            scorecard = RealAgentPilotRunner().run(
                RealAgentPilotConfig(
                    experiment_id="PILOT-B-BLOCKED",
                    mode=PilotMode.REAL_EXECUTOR,
                    request_template=EXAMPLE,
                    output_dir=Path(temp),
                    repetitions=1,
                )
            )

            self.assertEqual(scorecard["success_count"], 0)
            self.assertEqual(scorecard["failure_classes"], {"real_executor_driver_unavailable": 1})
            self.assertEqual(scorecard["workflow_failure_dimensions"]["counts"]["provider_runtime"], 1)
            self.assertEqual(scorecard["runs"][0]["workflow_failure_dimension"], "provider_runtime")
            self.assertEqual(scorecard["runs"][0]["status"], "blocked")

    def test_mode_b_real_executor_uses_goal_scheduler_capability_admission(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            driver = PilotExecutorDriver()
            scorecard = RealAgentPilotRunner(executor_driver=driver).run(
                RealAgentPilotConfig(
                    experiment_id="PILOT-B",
                    mode=PilotMode.REAL_EXECUTOR,
                    request_template=EXAMPLE,
                    output_dir=Path(temp),
                    repetitions=1,
                )
            )

            self.assertEqual(driver.executor_calls, 1)
            self.assertEqual(scorecard["success_count"], 1)
            run = scorecard["runs"][0]
            self.assertEqual(run["execution"]["status"], "succeeded")
            self.assertGreaterEqual(run["execution"]["metrics"]["capabilityGrantRefCount"], 1)
            self.assertIsNone(scorecard["cost"]["cost_usd"])
            self.assertFalse(scorecard["cost"]["usage_available"])
            self.assertTrue(scorecard["real_executor_budget_invariant"]["required"])
            self.assertEqual(
                scorecard["real_executor_budget_invariant"]["minimums"]["budgetRequest"]["maxWallSeconds"],
                180,
            )
            self.assertEqual(len(scorecard["cost"]["runs"]), 1)
            self.assertIsNone(scorecard["cost"]["runs"][0]["cost_usd"])
            self.assertIsNone(run["provider_usage"]["total_tokens"])
            self.assertIsNone(run["provider_usage"]["cost_usd"])
            request_path = Path(run["request_path"])
            inspect = GoalOperationService().inspect(
                run["execution"]["goalExecutionId"],
                db_path=request_path.parent / ".ahra" / "goal-control.sqlite3",
                artifact_dir=request_path.parent / ".ahra" / "artifacts",
            )
            self.assertEqual(inspect["metrics"]["missingArtifactCount"], 0)
            self.assertEqual(inspect["artifactFindings"], [])

    def test_goal_operation_real_executor_profile_fails_before_sqlite_without_driver(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            request = Path(temp) / "goal-run-request.yaml"
            data = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
            data["metadata"]["idempotencyKey"] = "real-executor-no-driver"
            data["spec"]["profileRef"] = "profile/m1-real-executor@sha256:" + "9" * 64
            data["spec"]["executor"]["adapterRef"] = REAL_BOUNDED_EXECUTOR_REF
            request.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

            with self.assertRaises(GoalOperationError) as raised:
                GoalOperationService().start(request)

            self.assertEqual(raised.exception.code, "real_executor_driver_unavailable")
            self.assertFalse((Path(temp) / ".ahra" / "goal-control.sqlite3").exists())

    def test_mode_c_normalizes_real_planner_executor_budget_to_policy_window(self) -> None:
        draft = PlanDraft.from_mapping(_template_draft())
        policy = ExecutionPolicy(
            max_attempts=1,
            startup_timeout_seconds=60,
            idle_timeout_seconds=45,
            heartbeat_interval_seconds=10,
            attempt_wall_timeout_seconds=60,
            run_deadline_seconds=90,
        )

        normalized, normalization = _normalize_real_executor_plan_draft(
            draft,
            mode=PilotMode.COMBINED,
            policy=policy,
        )

        self.assertIsNotNone(normalization)
        normalized_write_node = normalized.to_dict()["spec"]["nodes"][0]
        self.assertEqual(normalized_write_node["budgetRequest"]["maxModelCalls"], 2)
        self.assertEqual(normalized_write_node["budgetRequest"]["maxWallSeconds"], 60)
        self.assertEqual(normalized_write_node["timeoutSeconds"], 60)
        assert normalization is not None
        self.assertTrue(normalization["budget_invariant"]["required"])
        self.assertEqual(
            normalization["budget_invariant"]["enforcement_points"],
            ["request_template_expansion", "real_planner_admission_writeback"],
        )

    def test_mode_c_runs_without_legacy_combined_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            planner_registry = AgentDriverRegistry()
            planner_registry.register("pilot-planner", PilotPlannerDriver(_template_draft()))
            scorecard = RealAgentPilotRunner(
                planner_registry=planner_registry,
                executor_driver=PilotExecutorDriver(),
            ).run(
                RealAgentPilotConfig(
                    experiment_id="PILOT-C-DEFAULT",
                    mode=PilotMode.COMBINED,
                    request_template=EXAMPLE,
                    output_dir=Path(temp),
                    repetitions=1,
                    planner_driver_ref="pilot-planner",
                    allow_combined=False,
                )
            )

            self.assertEqual(scorecard["success_count"], 1)
            self.assertEqual(scorecard["runs"][0]["workflow_failure_dimension"], "none")

    def test_pilot_runner_records_unexpected_service_exception_as_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            scorecard = RealAgentPilotRunner(
                executor_driver=PilotExecutorDriver(),
                service_factory=lambda config, run_dir: RaisingService(),
            ).run(
                RealAgentPilotConfig(
                    experiment_id="PILOT-B-EXCEPTION",
                    mode=PilotMode.REAL_EXECUTOR,
                    request_template=EXAMPLE,
                    output_dir=Path(temp),
                    repetitions=1,
                )
            )

            run = scorecard["runs"][0]
            self.assertEqual(scorecard["success_count"], 0)
            self.assertEqual(run["status"], "blocked")
            self.assertEqual(run["failure_class"], "pilot_runner_exception")
            self.assertIn("RuntimeError", run["message"])
            self.assertTrue((Path(temp) / "run-01" / "run-result.json").exists())

    def test_timeout_recovery_uses_partial_child_state_and_finalizes_goal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output_dir = Path(temp)
            config = RealAgentPilotConfig(
                experiment_id="PILOT-C-TIMEOUT",
                mode=PilotMode.COMBINED,
                request_template=EXAMPLE,
                output_dir=output_dir,
                repetitions=1,
                allow_combined=True,
            )
            request_path, goal_execution_id = _prepare_terminal_partial_child_run(output_dir, "PILOT-C-TIMEOUT-R01")

            run = RealAgentPilotRunner().recover_timeout_run(
                config,
                1,
                elapsed_seconds=360.0,
                message="single repetition exceeded process timeout (360s)",
                details={"stdoutTail": "", "stderrTail": ""},
            )

            self.assertEqual(run["status"], "failed")
            self.assertEqual(run["failure_class"], "timeout")
            self.assertEqual(run["workflow_failure_dimension"], "scheduler")
            self.assertEqual(run["planner"]["status"], "accepted")
            self.assertEqual(run["execution"]["goalExecutionId"], goal_execution_id)
            self.assertEqual(run["execution"]["status"], "failed")
            self.assertEqual(run["execution"]["planStatus"], "failed")
            self.assertEqual(run["execution"]["metrics"]["goalStatus"], "failed")
            self.assertTrue(run["details"]["recoveredPartialRun"])
            self.assertTrue((output_dir / "run-01" / "run-result.json").exists())

            inspect = GoalOperationService().inspect(
                goal_execution_id,
                db_path=request_path.parent / ".ahra" / "goal-control.sqlite3",
                artifact_dir=request_path.parent / ".ahra" / "artifacts",
            )
            self.assertEqual(inspect["metrics"]["goalStatus"], "failed")

    def test_timeout_recovery_preserves_synthetic_timeout_when_no_state_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            config = RealAgentPilotConfig(
                experiment_id="PILOT-C-NO-STATE",
                mode=PilotMode.COMBINED,
                request_template=EXAMPLE,
                output_dir=Path(temp),
                repetitions=1,
                allow_combined=True,
            )

            run = RealAgentPilotRunner().recover_timeout_run(
                config,
                1,
                elapsed_seconds=360.0,
                message="single repetition exceeded process timeout (360s)",
            )

            self.assertEqual(run["status"], "blocked")
            self.assertEqual(run["failure_class"], "runner_timeout")
            self.assertEqual(run["planner"]["status"], "skipped")
            self.assertEqual(run["execution"]["status"], "skipped")


class RealAgentPilotScriptTests(unittest.TestCase):
    def test_script_mode_defaults_to_mode_c(self) -> None:
        script = _load_pilot_script()

        args = script._build_parser().parse_args(["--output-dir", "out"])

        self.assertEqual(args.mode, PilotMode.COMBINED.value)

    def test_isolated_watchdog_does_not_preempt_real_executor_deadline(self) -> None:
        script = _load_pilot_script()
        args = SimpleNamespace(repetition_timeout_seconds=120, executor_run_deadline_seconds=240)

        timeout = script._effective_repetition_timeout(args, PilotMode.REAL_EXECUTOR)

        self.assertEqual(timeout, 255)

    def test_isolated_watchdog_preserves_planner_only_timeout(self) -> None:
        script = _load_pilot_script()
        args = SimpleNamespace(repetition_timeout_seconds=120, executor_run_deadline_seconds=240)

        timeout = script._effective_repetition_timeout(args, PilotMode.REAL_PLANNER)

        self.assertEqual(timeout, 120)

    def test_isolated_watchdog_keeps_larger_operator_timeout(self) -> None:
        script = _load_pilot_script()
        args = SimpleNamespace(repetition_timeout_seconds=300, executor_run_deadline_seconds=240)

        timeout = script._effective_repetition_timeout(args, PilotMode.REAL_EXECUTOR)

        self.assertEqual(timeout, 300)

    def test_isolated_timeout_uses_recovery_hook(self) -> None:
        script = _load_pilot_script()
        with tempfile.TemporaryDirectory() as temp:
            args = SimpleNamespace(
                mode=PilotMode.COMBINED.value,
                request=str(EXAMPLE),
                output_dir=temp,
                experiment_id="SCRIPT-TIMEOUT",
                repetitions=1,
                driver_ref="codex-python-sdk",
                model_provider="codex-sdk",
                model=None,
                allow_model_cost=True,
                allow_combined=True,
                repetition_timeout_seconds=1,
                executor_max_attempts=1,
                executor_startup_timeout_seconds=60,
                executor_idle_timeout_seconds=120,
                executor_heartbeat_interval_seconds=15,
                executor_attempt_wall_timeout_seconds=180,
                executor_run_deadline_seconds=1,
            )
            config = RealAgentPilotConfig(
                experiment_id=args.experiment_id,
                mode=PilotMode.COMBINED,
                request_template=EXAMPLE,
                output_dir=Path(temp),
                repetitions=1,
                allow_combined=True,
            )
            calls: list[dict[str, Any]] = []

            class FakeRunner:
                def recover_timeout_run(self, config, index, *, elapsed_seconds, message, details):
                    calls.append({"index": index, "message": message, "details": details})
                    return {"run_id": "SCRIPT-TIMEOUT-R01", "status": "failed", "failure_class": "timeout"}

                def write_scorecard(self, config, runs):
                    return {"runs": runs}

            old_runner = script.RealAgentPilotRunner
            old_run = script.subprocess.run
            try:
                script.RealAgentPilotRunner = lambda: FakeRunner()

                def raise_timeout(*args, **kwargs):
                    raise subprocess.TimeoutExpired(cmd="pilot", timeout=1, output="partial stdout", stderr="partial stderr")

                script.subprocess.run = raise_timeout
                scorecard = script._run_isolated_repetitions(args, config)
            finally:
                script.RealAgentPilotRunner = old_runner
                script.subprocess.run = old_run

            self.assertEqual(scorecard["runs"][0]["failure_class"], "timeout")
            self.assertEqual(calls[0]["index"], 1)
            self.assertIn("single repetition exceeded process timeout", calls[0]["message"])
            self.assertEqual(calls[0]["details"]["stdoutTail"], "partial stdout")
            self.assertEqual(calls[0]["details"]["stderrTail"], "partial stderr")


def _template_draft() -> dict[str, Any]:
    data = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    return copy.deepcopy(data["spec"]["planDraft"])


def _prepare_terminal_partial_child_run(output_dir: Path, run_id: str) -> tuple[Path, str]:
    run_dir = output_dir / "run-01"
    run_dir.mkdir(parents=True)
    request_path = run_dir / "goal-run-request.yaml"
    data = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    data["metadata"]["name"] = run_id
    data["metadata"]["requestId"] = run_id
    data["metadata"]["idempotencyKey"] = run_id
    request_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    operation_service = GoalOperationService()
    operation_service.plan(request_path)
    bundle = operation_service.plan_bundle(request_path)
    assert bundle.plan is not None
    request = bundle.request
    _write_json(
        request.artifact_dir / "planner-admission-report.json",
        {"apiVersion": "ahra.dev/v1alpha1", "kind": "PlanValidationReport", "spec": {"result": "passed", "errors": []}},
    )
    _write_json(
        request.artifact_dir / "planner-output-artifact.json",
        {"artifactId": "PLART-test", "kind": "planner-plan-draft", "payload": request.plan_draft.to_dict()},
    )

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
    return request_path, request.goal_execution_id


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_pilot_script():
    spec = importlib.util.spec_from_file_location("run_real_agent_pilot_script", PILOT_SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load run_real_agent_pilot.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    unittest.main()
