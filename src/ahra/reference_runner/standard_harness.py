from __future__ import annotations

from pathlib import Path

from ahra.ports import AgentDriver

from .checks import run_checks
from .driver import execute_task, review_task
from .git_ops import LocalGitWorkspaceProvider
from .models import (
    CriterionAssessment,
    DeterministicEvidence,
    ReviewResult,
    ReviewVerdict,
    TaskAttemptRecord,
    TaskRunResult,
    TaskSpec,
    WorkflowOutcome,
)
from .policy import ChangeSummary, evaluate_policy
from .review_contracts import enforce_task_review_contract
from .runtime import LocalRuntimeProvider
from .store import ReferenceRunStore

PATCH_EXCERPT_CHARS = 60_000


def _excerpt(text: str, limit: int = PATCH_EXCERPT_CHARS) -> str:
    if len(text) <= limit:
        return text
    half = limit // 2
    return f"{text[:half]}\n\n... patch truncated ...\n\n{text[-half:]}"


def _deterministic_failure_review(evidence: DeterministicEvidence) -> ReviewResult:
    blockers = list(evidence.policy.violations)
    if evidence.verification_mutated_workspace:
        blockers.append(
            f"Verification commands modified the workspace: {evidence.verification_mutation_files}"
        )
    blockers.extend(
        f"Required check failed: {check.name}"
        for check in evidence.checks
        if check.required and not check.passed
    )
    return ReviewResult(
        verdict=ReviewVerdict.FAIL,
        summary="Semantic review was skipped because the deterministic gate failed.",
        criteria=(
            CriterionAssessment(
                criterion="Deterministic preconditions",
                passed=False,
                evidence="Required checks and policy must pass before semantic review.",
                concerns=tuple(blockers),
            ),
        ),
        blocking_issues=tuple(blockers),
        confidence=1.0,
    )


class TaskHarness:
    module_id = "standard-harness"

    def __init__(self, driver: AgentDriver, *, workspace_provider=None, runtime_provider=None) -> None:
        self.driver = driver
        self.workspace_provider = workspace_provider or LocalGitWorkspaceProvider()
        self.runtime_provider = runtime_provider or LocalRuntimeProvider()

    def collect_evidence(
        self,
        *,
        workspace_ref: str,
        checkpoint: str,
        task: TaskSpec,
        parent_policy=None,
        checks=(),
        patch_before_checks: str | None = None,
    ) -> tuple[DeterministicEvidence, str]:
        files = tuple(self.workspace_provider.changed_files(workspace_ref, checkpoint))
        added, deleted = self.workspace_provider.numstat(workspace_ref, checkpoint)
        full_patch = self.workspace_provider.patch(workspace_ref, checkpoint)
        policy = evaluate_policy(
            ChangeSummary(files=files, added_lines=added, deleted_lines=deleted),
            task.policy,
            parent_policy,
        )
        mutated = patch_before_checks is not None and full_patch != patch_before_checks
        evidence = DeterministicEvidence(
            policy=policy,
            checks=tuple(checks),
            verification_mutated_workspace=mutated,
            verification_mutation_files=files if mutated else (),
            patch_excerpt=_excerpt(full_patch),
        )
        return evidence, full_patch

    async def run_task(
        self,
        *,
        task: TaskSpec,
        workspace_ref: str,
        branch: str,
        run_id: str,
        store: ReferenceRunStore,
        parent_policy=None,
    ) -> TaskRunResult:
        workspace = Path(self.workspace_provider.resolve_path(workspace_ref))
        checkpoint = self.workspace_provider.current_head(workspace_ref)
        attempts: list[TaskAttemptRecord] = []
        feedback: str | None = None
        store.event("task_started", module_id=self.module_id, task_id=task.id, checkpoint=checkpoint)

        for attempt_number in range(1, task.max_attempts + 1):
            store.event("attempt_started", task_id=task.id, attempt=attempt_number)
            try:
                report = await execute_task(
                    self.driver,
                    task=task,
                    workspace=workspace,
                    feedback=feedback,
                    run_id=run_id,
                    attempt=attempt_number,
                )

                pre_evidence, full_patch = self.collect_evidence(
                    workspace_ref=workspace_ref,
                    checkpoint=checkpoint,
                    task=task,
                    parent_policy=parent_policy,
                )
                patch_before_checks = full_patch
                if pre_evidence.policy.passed:
                    check_results = run_checks(workspace, task.checks, self.runtime_provider)
                    evidence, full_patch = self.collect_evidence(
                        workspace_ref=workspace_ref,
                        checkpoint=checkpoint,
                        task=task,
                        parent_policy=parent_policy,
                        checks=check_results,
                        patch_before_checks=patch_before_checks,
                    )
                else:
                    evidence = pre_evidence

                patch_record = store.write_artifact(
                    f"tasks/{task.id}/attempt-{attempt_number}/patch.diff",
                    full_patch,
                    task_id=task.id,
                    kind="patch",
                    media_type="text/x-diff",
                    created_by=f"workflow-module:{self.module_id}",
                    input_refs=[task.id, run_id],
                )
                if evidence.verification_mutated_workspace:
                    store.write_artifact(
                        f"tasks/{task.id}/attempt-{attempt_number}/pre-check.patch",
                        patch_before_checks,
                        task_id=task.id,
                        kind="pre_check_patch",
                        media_type="text/x-diff",
                        created_by=f"workflow-module:{self.module_id}",
                        input_refs=[task.id, run_id],
                    )
                report_record = store.write_artifact(
                    f"tasks/{task.id}/attempt-{attempt_number}/work-report.json",
                    report,
                    task_id=task.id,
                    kind="work_report",
                    media_type="application/json",
                    created_by=f"workflow-module:{self.module_id}",
                    input_refs=[task.id, run_id],
                )
                deterministic_record = store.write_evidence(
                    f"tasks/{task.id}/attempt-{attempt_number}/deterministic-evidence.json",
                    evidence,
                    task_id=task.id,
                    kind="deterministic_gate",
                    refs=[patch_record["artifact_id"], report_record["artifact_id"]],
                )

                if evidence.passed:
                    review = await review_task(
                        self.driver,
                        task=task,
                        report=report,
                        evidence=evidence,
                        patch_text=full_patch,
                        workspace=workspace,
                        run_id=run_id,
                    )
                    review = enforce_task_review_contract(task, review)
                else:
                    review = _deterministic_failure_review(evidence)

                store.write_evidence(
                    f"tasks/{task.id}/attempt-{attempt_number}/review.json",
                    review,
                    task_id=task.id,
                    kind="semantic_review",
                    refs=[deterministic_record["evidence_id"]],
                )
                record = TaskAttemptRecord(
                    attempt=attempt_number,
                    work_report=report,
                    deterministic=evidence,
                    review=review,
                )
                attempts.append(record)
                store.event(
                    "attempt_evaluated",
                    task_id=task.id,
                    attempt=attempt_number,
                    deterministic_passed=evidence.passed,
                    review_verdict=review.verdict.value,
                )

                if evidence.passed and review.verdict == ReviewVerdict.PASS:
                    commit = self.workspace_provider.commit_all(
                        workspace_ref,
                        f"ahra({task.id}): {task.title}",
                    )
                    result = TaskRunResult(
                        run_id=run_id,
                        task_id=task.id,
                        status=WorkflowOutcome.ACCEPTED,
                        checkpoint=checkpoint,
                        commit=commit,
                        attempts=tuple(attempts),
                        message="Task passed deterministic and independent semantic gates.",
                        workspace=str(workspace),
                        branch=branch,
                        artifact_dir=str(store.run_dir),
                    )
                    store.event("task_accepted", task_id=task.id, commit=commit)
                    return result

                if evidence.passed and review.verdict == ReviewVerdict.NEEDS_HUMAN:
                    result = TaskRunResult(
                        run_id=run_id,
                        task_id=task.id,
                        status=WorkflowOutcome.NEEDS_HUMAN,
                        checkpoint=checkpoint,
                        attempts=tuple(attempts),
                        message="Independent reviewer requires human judgment.",
                        workspace=str(workspace),
                        branch=branch,
                        artifact_dir=str(store.run_dir),
                    )
                    store.event("task_needs_human", task_id=task.id)
                    return result

                if attempt_number < task.max_attempts:
                    feedback = "; ".join(review.blocking_issues) or review.summary
                    if evidence.verification_mutated_workspace:
                        self.workspace_provider.restore_patch(
                            workspace_ref,
                            checkpoint,
                            patch_before_checks,
                        )
                        store.event(
                            "verification_mutation_restored",
                            task_id=task.id,
                            attempt=attempt_number,
                        )
                    continue

                rejected_patch = (
                    patch_before_checks if evidence.verification_mutated_workspace else full_patch
                )
                store.write_artifact(
                    f"tasks/{task.id}/rejected.patch",
                    rejected_patch,
                    task_id=task.id,
                    kind="rejected_patch",
                    media_type="text/x-diff",
                    created_by=f"workflow-module:{self.module_id}",
                    input_refs=[task.id, run_id],
                )
                self.workspace_provider.rollback(workspace_ref, checkpoint)
                result = TaskRunResult(
                    run_id=run_id,
                    task_id=task.id,
                    status=WorkflowOutcome.REJECTED,
                    checkpoint=checkpoint,
                    attempts=tuple(attempts),
                    message="Task exhausted its bounded attempts and was rolled back.",
                    workspace=str(workspace),
                    branch=branch,
                    artifact_dir=str(store.run_dir),
                )
                store.event("task_rejected", task_id=task.id)
                return result
            except Exception as exc:
                attempts.append(TaskAttemptRecord(attempt=attempt_number, error=repr(exc)))
                store.event(
                    "attempt_error",
                    task_id=task.id,
                    attempt=attempt_number,
                    error=repr(exc),
                )
                if attempt_number < task.max_attempts:
                    feedback = f"The harness raised an execution error: {exc!r}. Recover safely."
                    continue
                self.workspace_provider.rollback(workspace_ref, checkpoint)
                return TaskRunResult(
                    run_id=run_id,
                    task_id=task.id,
                    status=WorkflowOutcome.ERROR,
                    checkpoint=checkpoint,
                    attempts=tuple(attempts),
                    message=f"Task failed with an execution error and was rolled back: {exc!r}",
                    workspace=str(workspace),
                    branch=branch,
                    artifact_dir=str(store.run_dir),
                )

        raise AssertionError("unreachable")
