from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from ahra.ports import AgentRole, AgentRunRequest, AgentRunResult
from ahra.reference_runner.driver import propose_next_steps, review_goal, review_task
from ahra.reference_runner.models import (
    DeterministicEvidence,
    GoalReviewResult,
    GoalSpec,
    NextStepDecision,
    PlanAction,
    PolicyEvidence,
    ReviewResult,
    ReviewVerdict,
    TaskSpec,
    WorkReport,
)


class CapturingDriver:
    def __init__(self) -> None:
        self.requests: list[AgentRunRequest] = []

    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        self.requests.append(request)
        if request.role == AgentRole.TASK_REVIEWER:
            return AgentRunResult(
                output=ReviewResult(
                    verdict=ReviewVerdict.PASS,
                    summary="pass",
                )
            )
        if request.role == AgentRole.GOAL_REVIEWER:
            return AgentRunResult(
                output=GoalReviewResult(
                    verdict=ReviewVerdict.PASS,
                    summary="pass",
                )
            )
        if request.role == AgentRole.PLANNER:
            return AgentRunResult(
                output=NextStepDecision(
                    action=PlanAction.ESCALATE,
                    rationale="stop",
                )
            )
        raise AssertionError(f"unexpected role: {request.role}")


class DriverRequestTests(unittest.TestCase):
    def test_review_and_planning_requests_include_workspace_ref(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            driver = CapturingDriver()
            task = TaskSpec(
                id="task-1",
                title="Task",
                objective="Do work",
                acceptance_criteria=("criterion",),
            )
            goal = GoalSpec(
                id="goal-1",
                title="Goal",
                objective="Finish goal",
                success_criteria=("done",),
                dynamic_planning=True,
            )
            evidence = DeterministicEvidence(policy=PolicyEvidence())

            asyncio.run(
                review_task(
                    driver,
                    task=task,
                    report=WorkReport(summary="done"),
                    evidence=evidence,
                    patch_text="diff",
                    workspace=workspace,
                    run_id="RUN-test",
                )
            )
            asyncio.run(
                review_goal(
                    driver,
                    goal=goal,
                    task_results=(),
                    evidence=evidence,
                    patch_text="diff",
                    workspace=workspace,
                    run_id="RUN-test",
                )
            )
            asyncio.run(
                propose_next_steps(
                    driver,
                    goal=goal,
                    task_results=(),
                    evidence=evidence,
                    goal_review=GoalReviewResult(verdict=ReviewVerdict.FAIL, summary="fail"),
                    workspace=workspace,
                    run_id="RUN-test",
                )
            )

            self.assertEqual([request.workspace_ref for request in driver.requests], [str(workspace)] * 3)


if __name__ == "__main__":
    unittest.main()
