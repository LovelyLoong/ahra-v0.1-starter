from __future__ import annotations

from pathlib import Path

from ahra.ports import AgentDriver

from .checks import run_checks
from .driver import propose_next_steps, review_goal
from .git_ops import LocalGitWorkspaceProvider
from .models import (
    DeterministicEvidence,
    ExecutionPolicy,
    GoalRunResult,
    GoalSpec,
    PlanAction,
    ReviewVerdict,
    TaskRunResult,
    TaskSpec,
    WorkflowOutcome,
)
from .policy import ChangeSummary, evaluate_policy
from .review_contracts import enforce_goal_review_contract
from .runtime import LocalRuntimeProvider
from .standard_harness import PATCH_EXCERPT_CHARS, _excerpt
from .store import ReferenceRunStore
from .task_harness import TaskHarness


class LoopEngine:
    module_id = "loop-engineering"

    def __init__(
        self,
        driver: AgentDriver,
        *,
        workspace_provider=None,
        runtime_provider=None,
        runtime_profile_ref: str | None = None,
        execution_policy: ExecutionPolicy | None = None,
    ) -> None:
        self.driver = driver
        self.workspace_provider = workspace_provider or LocalGitWorkspaceProvider()
        self.runtime_provider = runtime_provider or LocalRuntimeProvider()
        self.runtime_profile_ref = runtime_profile_ref
        self.execution_policy = execution_policy or ExecutionPolicy()
        self.task_harness = TaskHarness(
            driver,
            workspace_provider=self.workspace_provider,
            runtime_provider=self.runtime_provider,
            runtime_profile_ref=runtime_profile_ref,
            execution_policy=self.execution_policy,
        )

    def _global_evidence(
        self,
        *,
        goal: GoalSpec,
        workspace_ref: str,
        base_commit: str,
    ) -> tuple[DeterministicEvidence, str]:
        files = tuple(self.workspace_provider.changed_files(workspace_ref, base_commit))
        added, deleted = self.workspace_provider.numstat(workspace_ref, base_commit)
        policy = evaluate_policy(
            ChangeSummary(files=files, added_lines=added, deleted_lines=deleted),
            goal.policy,
        )
        patch_before_checks = self.workspace_provider.patch(workspace_ref, base_commit)
        workspace_path = Path(self.workspace_provider.resolve_path(workspace_ref))
        checks = run_checks(workspace_path, goal.global_checks, self.runtime_provider) if policy.passed else ()

        files = tuple(self.workspace_provider.changed_files(workspace_ref, base_commit))
        added, deleted = self.workspace_provider.numstat(workspace_ref, base_commit)
        policy = evaluate_policy(
            ChangeSummary(files=files, added_lines=added, deleted_lines=deleted),
            goal.policy,
        )
        full_patch = self.workspace_provider.patch(workspace_ref, base_commit)
        mutated = full_patch != patch_before_checks
        return (
            DeterministicEvidence(
                policy=policy,
                checks=checks,
                verification_mutated_workspace=mutated,
                verification_mutation_files=files if mutated else (),
                patch_excerpt=_excerpt(full_patch, PATCH_EXCERPT_CHARS),
            ),
            full_patch,
        )

    async def run_goal(
        self,
        *,
        goal: GoalSpec,
        workspace_ref: str,
        branch: str,
        base_commit: str,
        run_id: str,
        store: ReferenceRunStore,
        pending_tasks: tuple[TaskSpec, ...] | None = None,
        completed_tasks: tuple[TaskRunResult, ...] | None = None,
        known_task_ids: set[str] | None = None,
        start_cycle: int = 1,
    ) -> GoalRunResult:
        completed = list(completed_tasks or ())
        queue = list(goal.tasks if pending_tasks is None else pending_tasks)
        if known_task_ids is None:
            known_ids = {task.id for task in goal.tasks}
            known_ids.update(task.id for task in queue)
            known_ids.update(result.task_id for result in completed)
        else:
            known_ids = set(known_task_ids)

        workspace_path = Path(self.workspace_provider.resolve_path(workspace_ref))
        workspace_display = str(workspace_path)

        if start_cycle > goal.max_cycles:
            return GoalRunResult(
                run_id=run_id,
                goal_id=goal.id,
                status=WorkflowOutcome.BLOCKED,
                branch=branch,
                workspace=workspace_display,
                artifact_dir=str(store.run_dir),
                completed_tasks=tuple(completed),
                final_commit=self.workspace_provider.current_head(workspace_ref),
                message=(
                    f"Cannot continue goal: next cycle {start_cycle} exceeds "
                    f"max_cycles {goal.max_cycles}."
                ),
            )

        if start_cycle == 1 and not completed:
            store.event("goal_started", module_id=self.module_id, goal_id=goal.id)
        else:
            store.event(
                "goal_resumed",
                goal_id=goal.id,
                start_cycle=start_cycle,
                pending_tasks=[task.id for task in queue],
            )

        for cycle in range(start_cycle, goal.max_cycles + 1):
            store.event("cycle_started", goal_id=goal.id, cycle=cycle)
            while queue:
                task = queue.pop(0)
                store.write_json(f"tasks/{task.id}/task-spec.json", task)
                result = await self.task_harness.run_task(
                    task=task,
                    workspace_ref=workspace_ref,
                    branch=branch,
                    run_id=run_id,
                    store=store,
                    parent_policy=goal.policy,
                )
                store.write_json(f"tasks/{task.id}/result.json", result)
                if result.status != WorkflowOutcome.ACCEPTED:
                    final = GoalRunResult(
                        run_id=run_id,
                        goal_id=goal.id,
                        status=(
                            WorkflowOutcome.NEEDS_HUMAN
                            if result.status == WorkflowOutcome.NEEDS_HUMAN
                            else WorkflowOutcome.BLOCKED
                        ),
                        branch=branch,
                        workspace=workspace_display,
                        artifact_dir=str(store.run_dir),
                        completed_tasks=tuple((*completed, result)),
                        final_commit=self.workspace_provider.current_head(workspace_ref),
                        message=f"Outer loop stopped at task {task.id}: {result.message}",
                    )
                    store.event("goal_stopped", goal_id=goal.id, task_id=task.id)
                    return final
                completed.append(result)

            evidence, full_patch = self._global_evidence(
                goal=goal,
                workspace_ref=workspace_ref,
                base_commit=base_commit,
            )
            store.write_artifact(
                f"cycles/{cycle}/cumulative.patch",
                full_patch,
                task_id=goal.id,
                kind="cumulative_patch",
                media_type="text/x-diff",
                created_by=f"workflow-module:{self.module_id}",
                input_refs=[goal.id, run_id],
            )
            store.write_evidence(
                f"cycles/{cycle}/global-evidence.json",
                evidence,
                task_id=goal.id,
                kind="global_deterministic_gate",
            )

            goal_review = await review_goal(
                self.driver,
                goal=goal,
                task_results=tuple(completed),
                evidence=evidence,
                patch_text=full_patch,
                workspace=workspace_path,
                run_id=run_id,
                runtime_profile_ref=self.runtime_profile_ref,
            )
            goal_review = enforce_goal_review_contract(goal, goal_review)
            store.write_evidence(
                f"cycles/{cycle}/goal-review.json",
                goal_review,
                task_id=goal.id,
                kind="goal_semantic_review",
            )

            if evidence.passed and goal_review.verdict == ReviewVerdict.PASS:
                result = GoalRunResult(
                    run_id=run_id,
                    goal_id=goal.id,
                    status=WorkflowOutcome.COMPLETE,
                    branch=branch,
                    workspace=workspace_display,
                    artifact_dir=str(store.run_dir),
                    completed_tasks=tuple(completed),
                    global_evidence=evidence,
                    goal_review=goal_review,
                    final_commit=self.workspace_provider.current_head(workspace_ref),
                    message="Goal passed cumulative deterministic checks and independent review.",
                )
                store.event("goal_complete", goal_id=goal.id, cycle=cycle)
                return result

            if goal_review.verdict == ReviewVerdict.NEEDS_HUMAN:
                return GoalRunResult(
                    run_id=run_id,
                    goal_id=goal.id,
                    status=WorkflowOutcome.NEEDS_HUMAN,
                    branch=branch,
                    workspace=workspace_display,
                    artifact_dir=str(store.run_dir),
                    completed_tasks=tuple(completed),
                    global_evidence=evidence,
                    goal_review=goal_review,
                    final_commit=self.workspace_provider.current_head(workspace_ref),
                    message="Overall goal review requires human judgment.",
                )

            if not goal.dynamic_planning:
                return GoalRunResult(
                    run_id=run_id,
                    goal_id=goal.id,
                    status=WorkflowOutcome.BLOCKED,
                    branch=branch,
                    workspace=workspace_display,
                    artifact_dir=str(store.run_dir),
                    completed_tasks=tuple(completed),
                    global_evidence=evidence,
                    goal_review=goal_review,
                    final_commit=self.workspace_provider.current_head(workspace_ref),
                    message="Goal verification failed and dynamic planning is disabled.",
                )

            decision = await propose_next_steps(
                self.driver,
                goal=goal,
                task_results=tuple(completed),
                evidence=evidence,
                goal_review=goal_review,
                workspace=workspace_path,
                run_id=run_id,
                runtime_profile_ref=self.runtime_profile_ref,
            )
            store.write_artifact(
                f"cycles/{cycle}/next-step.json",
                decision,
                task_id=goal.id,
                kind="next_step_plan",
                media_type="application/json",
                created_by=f"workflow-module:{self.module_id}",
                input_refs=[goal.id, run_id],
            )

            if decision.action == PlanAction.ESCALATE:
                return GoalRunResult(
                    run_id=run_id,
                    goal_id=goal.id,
                    status=WorkflowOutcome.BLOCKED,
                    branch=branch,
                    workspace=workspace_display,
                    artifact_dir=str(store.run_dir),
                    completed_tasks=tuple(completed),
                    global_evidence=evidence,
                    goal_review=goal_review,
                    next_step=decision,
                    final_commit=self.workspace_provider.current_head(workspace_ref),
                    message=decision.rationale,
                )

            duplicates = [task.id for task in decision.proposed_tasks if task.id in known_ids]
            if duplicates:
                return GoalRunResult(
                    run_id=run_id,
                    goal_id=goal.id,
                    status=WorkflowOutcome.BLOCKED,
                    branch=branch,
                    workspace=workspace_display,
                    artifact_dir=str(store.run_dir),
                    completed_tasks=tuple(completed),
                    global_evidence=evidence,
                    goal_review=goal_review,
                    next_step=decision,
                    final_commit=self.workspace_provider.current_head(workspace_ref),
                    message=f"Planner proposed duplicate task IDs: {duplicates}",
                )

            projected_total = len(known_ids) + len(decision.proposed_tasks)
            if projected_total > goal.max_total_tasks:
                return GoalRunResult(
                    run_id=run_id,
                    goal_id=goal.id,
                    status=WorkflowOutcome.BLOCKED,
                    branch=branch,
                    workspace=workspace_display,
                    artifact_dir=str(store.run_dir),
                    completed_tasks=tuple(completed),
                    global_evidence=evidence,
                    goal_review=goal_review,
                    next_step=decision,
                    final_commit=self.workspace_provider.current_head(workspace_ref),
                    message=(
                        "Planner exceeded max_total_tasks: "
                        f"{projected_total} > {goal.max_total_tasks}"
                    ),
                )

            if not goal.auto_execute_proposed_tasks:
                return GoalRunResult(
                    run_id=run_id,
                    goal_id=goal.id,
                    status=WorkflowOutcome.AWAITING_PLAN_APPROVAL,
                    branch=branch,
                    workspace=workspace_display,
                    artifact_dir=str(store.run_dir),
                    completed_tasks=tuple(completed),
                    global_evidence=evidence,
                    goal_review=goal_review,
                    next_step=decision,
                    final_commit=self.workspace_provider.current_head(workspace_ref),
                    message="Proposed tasks were saved for human approval.",
                )

            queue.extend(decision.proposed_tasks)
            known_ids.update(task.id for task in decision.proposed_tasks)

        return GoalRunResult(
            run_id=run_id,
            goal_id=goal.id,
            status=WorkflowOutcome.BLOCKED,
            branch=branch,
            workspace=workspace_display,
            artifact_dir=str(store.run_dir),
            completed_tasks=tuple(completed),
            final_commit=self.workspace_provider.current_head(workspace_ref),
            message=f"Maximum loop cycles reached: {goal.max_cycles}",
        )
