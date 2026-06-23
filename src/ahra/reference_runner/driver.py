from __future__ import annotations

from pathlib import Path
from typing import Any

from ahra.ports import (
    AgentDriver,
    AgentDriverRegistry,
    AgentOutputContractError,
    AgentRole,
    AgentRunRequest,
    AgentRunResult,
    AgentRuntimeProfile,
)
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
from .output_contracts import output_contract


def _expect_output(result: AgentRunResult, output_type: type[Any]) -> Any:
    if not isinstance(result.output, output_type):
        raise AgentOutputContractError(
            output_type.__name__,
            f"agent driver returned {type(result.output).__name__}; expected {output_type.__name__}",
        )
    return result.output


def runtime_profile_for_role(
    role: AgentRole,
    *,
    profile_ref: str | None = None,
) -> AgentRuntimeProfile:
    base_ref = profile_ref or "reference-runner/default"
    if role == AgentRole.EXECUTOR:
        return AgentRuntimeProfile(
            profile_ref=f"{base_ref}#executor",
            sandbox="workspace_write",
            capabilities=(
                "filesystem.read",
                "filesystem.write",
                "shell.exec",
                "git.diff",
            ),
        )
    if role in (AgentRole.TASK_REVIEWER, AgentRole.GOAL_REVIEWER):
        return AgentRuntimeProfile(
            profile_ref=f"{base_ref}#reviewer",
            sandbox="read_only",
            capabilities=("filesystem.read", "git.diff", "artifact.read"),
        )
    if role == AgentRole.PLANNER:
        return AgentRuntimeProfile(
            profile_ref=f"{base_ref}#planner",
            sandbox="read_only",
            capabilities=("filesystem.read", "artifact.read"),
        )
    raise ValueError(f"unsupported agent role: {role}")


async def execute_task(
    driver: AgentDriver,
    *,
    task: TaskSpec,
    workspace: Path,
    feedback: str | None,
    run_id: str,
    attempt: int,
    runtime_profile_ref: str | None = None,
) -> WorkReport:
    result = await driver.run(
        AgentRunRequest(
            role=AgentRole.EXECUTOR,
            run_id=run_id,
            expected_output="WorkReport",
            output_contract=output_contract("WorkReport"),
            runtime_profile=runtime_profile_for_role(
                AgentRole.EXECUTOR,
                profile_ref=runtime_profile_ref,
            ),
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
    attempt: int | None = None,
    review_attempt: int | None = None,
    contract_feedback: str | None = None,
    runtime_profile_ref: str | None = None,
) -> ReviewResult:
    payload: dict[str, Any] = {
        "task": task,
        "report": report,
        "evidence": evidence,
        "patch_text": patch_text,
    }
    if contract_feedback:
        payload["contract_feedback"] = contract_feedback
    result = await driver.run(
        AgentRunRequest(
            role=AgentRole.TASK_REVIEWER,
            run_id=run_id,
            expected_output="ReviewResult",
            output_contract=output_contract("ReviewResult"),
            runtime_profile=runtime_profile_for_role(
                AgentRole.TASK_REVIEWER,
                profile_ref=runtime_profile_ref,
            ),
            workspace_ref=str(workspace),
            attempt=attempt,
            metadata={
                "phase": "task_review",
                "review_attempt": review_attempt,
            },
            payload=payload,
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
    runtime_profile_ref: str | None = None,
) -> GoalReviewResult:
    result = await driver.run(
        AgentRunRequest(
            role=AgentRole.GOAL_REVIEWER,
            run_id=run_id,
            expected_output="GoalReviewResult",
            output_contract=output_contract("GoalReviewResult"),
            runtime_profile=runtime_profile_for_role(
                AgentRole.GOAL_REVIEWER,
                profile_ref=runtime_profile_ref,
            ),
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
    runtime_profile_ref: str | None = None,
) -> NextStepDecision:
    result = await driver.run(
        AgentRunRequest(
            role=AgentRole.PLANNER,
            run_id=run_id,
            expected_output="NextStepDecision",
            output_contract=output_contract("NextStepDecision"),
            runtime_profile=runtime_profile_for_role(
                AgentRole.PLANNER,
                profile_ref=runtime_profile_ref,
            ),
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
