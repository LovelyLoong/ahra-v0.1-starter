from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from typing import Any

import yaml

from ahra.goal_operations import REAL_BOUNDED_EXECUTOR_REF, GoalOperationError, GoalOperationService
from ahra.ports import AgentDriverRegistry, AgentRole, AgentRunRequest, AgentRunResult
from ahra.real_agent_pilot import PilotMode, RealAgentPilotConfig, RealAgentPilotRunner
from ahra.reference_runner.models import WorkReport


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "m1" / "goal-run-request.yaml"


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


def _template_draft() -> dict[str, Any]:
    data = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    return copy.deepcopy(data["spec"]["planDraft"])


if __name__ == "__main__":
    unittest.main()
