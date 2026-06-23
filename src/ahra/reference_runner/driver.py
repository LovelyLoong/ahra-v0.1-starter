from __future__ import annotations

from pathlib import Path
from typing import Any

from ahra.ports import AgentDriver, AgentDriverRegistry, AgentRole, AgentRunRequest, AgentRunResult
from .models import (
    DeterministicEvidence,
    GoalReviewResult,
    GoalSpec,
    NextStepDecision,
    ReviewResult,
    TaskRunResult,
    TaskSpec,
    WorkReport,
)


def _expect_output(result: AgentRunResult, output_type: type[Any]) -> Any:
    if not isinstance(result.output, output_type):
        raise TypeError(
            f"agent driver returned {type(result.output).__name__}; "
            f"expected {output_type.__name__}"
        )
    return result.output


async def execute_task(
    driver: AgentDriver,
    *,
    task: TaskSpec,
    workspace: Path,
    feedback: str | None,
    run_id: str,
    attempt: int,
) -> WorkReport:
    result = await driver.run(
        AgentRunRequest(
            role=AgentRole.EXECUTOR,
            run_id=run_id,
            expected_output="WorkReport",
            workspace_ref=str(workspace),
            attempt=attempt,
            payload={
                "task": task,
                "feedback": feedback,
            },
        )
    )
    return _expect_output(result, WorkReport)


async def review_task(
    driver: AgentDriver,
    *,
    task: TaskSpec,
    report: WorkReport,
    evidence: DeterministicEvidence,
    patch_text: str,
    workspace: Path,
    run_id: str,
) -> ReviewResult:
    result = await driver.run(
        AgentRunRequest(
            role=AgentRole.TASK_REVIEWER,
            run_id=run_id,
            expected_output="ReviewResult",
            workspace_ref=str(workspace),
            payload={
                "task": task,
                "report": report,
                "evidence": evidence,
                "patch_text": patch_text,
            },
        )
    )
    return _expect_output(result, ReviewResult)


async def review_goal(
    driver: AgentDriver,
    *,
    goal: GoalSpec,
    task_results: tuple[TaskRunResult, ...],
    evidence: DeterministicEvidence,
    patch_text: str,
    workspace: Path,
    run_id: str,
) -> GoalReviewResult:
    result = await driver.run(
        AgentRunRequest(
            role=AgentRole.GOAL_REVIEWER,
            run_id=run_id,
            expected_output="GoalReviewResult",
            workspace_ref=str(workspace),
            payload={
                "goal": goal,
                "task_results": task_results,
                "evidence": evidence,
                "patch_text": patch_text,
            },
        )
    )
    return _expect_output(result, GoalReviewResult)


async def propose_next_steps(
    driver: AgentDriver,
    *,
    goal: GoalSpec,
    task_results: tuple[TaskRunResult, ...],
    evidence: DeterministicEvidence,
    goal_review: GoalReviewResult,
    workspace: Path,
    run_id: str,
) -> NextStepDecision:
    result = await driver.run(
        AgentRunRequest(
            role=AgentRole.PLANNER,
            run_id=run_id,
            expected_output="NextStepDecision",
            workspace_ref=str(workspace),
            payload={
                "goal": goal,
                "task_results": task_results,
                "evidence": evidence,
                "goal_review": goal_review,
            },
        )
    )
    return _expect_output(result, NextStepDecision)
