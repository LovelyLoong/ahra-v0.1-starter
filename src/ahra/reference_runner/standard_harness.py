from __future__ import annotations

import hashlib
from pathlib import Path

from ahra.ports import AgentDriver, AgentOutputContractError

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
CONTRACT_ERROR_EXCERPT_CHARS = 20_000
REVIEW_CONTRACT_MAX_ATTEMPTS = 2


def _excerpt(text: str, limit: int = PATCH_EXCERPT_CHARS, *, label: str = "patch") -> str:
    if len(text) <= limit:
        return text
    half = limit // 2
    return f"{text[:half]}\n\n... {label} truncated ...\n\n{text[-half:]}"


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


def _contract_error_payload(error: AgentOutputContractError) -> dict[str, object]:
    payload: dict[str, object] = {
        "expected_output": error.expected_output,
        "message": str(error),
        "details": list(error.details),
    }
    if error.raw_output is not None:
        raw = str(error.raw_output)
        payload.update(
            {
                "raw_output_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                "raw_output_length": len(raw),
                "raw_output_excerpt": _excerpt(
                    raw,
                    CONTRACT_ERROR_EXCERPT_CHARS,
                    label="raw output",
                ),
            }
        )
    return payload


def _contract_feedback(error: AgentOutputContractError) -> str:
    detail = "; ".join(error.details) if error.details else str(error)
    return (
        "Your previous response did not satisfy the required output contract. "
        f"Return only the required JSON object for {error.expected_output}. "
        f"Contract error: {detail}"
    )


class TaskHarness:
    module_id = "standard-harness"

    def __init__(
        self,
        driver: AgentDriver,
        *,
        workspace_provider=None,
        runtime_provider=None,
        runtime_profile_ref: str | None = None,
    ) -> None:
        self.driver = driver
        self.workspace_provider = workspace_provider or LocalGitWorkspaceProvider()
        self.runtime_provider = runtime_provider or LocalRuntimeProvider()
        self.runtime_profile_ref = runtime_profile_ref

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
                store.event("executor_started", task_id=task.id, attempt=attempt_number)
                report = await execute_task(
                    self.driver,
                    task=task,
                    workspace=workspace,
                    feedback=feedback,
                    run_id=run_id,
                    attempt=attempt_number,
                    runtime_profile_ref=self.runtime_profile_ref,
                )
                store.event("executor_finished", task_id=task.id, attempt=attempt_number)

                store.event("deterministic_gate_started", task_id=task.id, attempt=attempt_number)
                pre_evidence, full_patch = self.collect_evidence(
                    workspace_ref=workspace_ref,
                    checkpoint=checkpoint,
                    task=task,
                    parent_policy=parent_policy,
                )
                patch_before_checks = full_patch
                if pre_evidence.policy.passed:
                    store.event("checks_started", task_id=task.id, attempt=attempt_number)
                    check_results = run_checks(workspace, task.checks, self.runtime_provider)
                    store.event(
                        "checks_finished",
                        task_id=task.id,
                        attempt=attempt_number,
                        check_count=len(check_results),
                        required_checks_passed=all(
                            check.passed for check in check_results if check.required
                        ),
                    )
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
                store.event(
                    "deterministic_gate_finished",
                    task_id=task.id,
                    attempt=attempt_number,
                    passed=evidence.passed,
                    policy_passed=evidence.policy.passed,
                    required_checks_passed=evidence.required_checks_passed,
                )

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
                    try:
                        review = await self._review_with_contract_retries(
                            task=task,
                            report=report,
                            evidence=evidence,
                            full_patch=full_patch,
                            workspace=workspace,
                            run_id=run_id,
                            attempt_number=attempt_number,
                            store=store,
                        )
                    except AgentOutputContractError as exc:
                        attempts.append(
                            TaskAttemptRecord(
                                attempt=attempt_number,
                                work_report=report,
                                deterministic=evidence,
                                error=repr(exc),
                            )
                        )
                        store.event(
                            "attempt_error",
                            task_id=task.id,
                            attempt=attempt_number,
                            phase="task_review",
                            retryable=False,
                            error=repr(exc),
                        )
                        self.workspace_provider.rollback(workspace_ref, checkpoint)
                        return TaskRunResult(
                            run_id=run_id,
                            task_id=task.id,
                            status=WorkflowOutcome.ERROR,
                            checkpoint=checkpoint,
                            attempts=tuple(attempts),
                            message=(
                                "Task review failed its output contract after bounded "
                                f"review retries and was rolled back: {exc!r}"
                            ),
                            workspace=str(workspace),
                            branch=branch,
                            artifact_dir=str(store.run_dir),
                        )
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
                    store.event("commit_started", task_id=task.id)
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
                    store.event("commit_finished", task_id=task.id, commit=commit)
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
                    phase="task_attempt",
                    retryable=attempt_number < task.max_attempts,
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

    async def _review_with_contract_retries(
        self,
        *,
        task: TaskSpec,
        report,
        evidence: DeterministicEvidence,
        full_patch: str,
        workspace: Path,
        run_id: str,
        attempt_number: int,
        store: ReferenceRunStore,
    ) -> ReviewResult:
        contract_feedback: str | None = None
        for review_attempt in range(1, REVIEW_CONTRACT_MAX_ATTEMPTS + 1):
            store.event(
                "reviewer_started",
                task_id=task.id,
                attempt=attempt_number,
                review_attempt=review_attempt,
            )
            try:
                review = await review_task(
                    self.driver,
                    task=task,
                    report=report,
                    evidence=evidence,
                    patch_text=full_patch,
                    workspace=workspace,
                    run_id=run_id,
                    attempt=attempt_number,
                    review_attempt=review_attempt,
                    contract_feedback=contract_feedback,
                    runtime_profile_ref=self.runtime_profile_ref,
                )
                review = enforce_task_review_contract(task, review)
                store.event(
                    "reviewer_finished",
                    task_id=task.id,
                    attempt=attempt_number,
                    review_attempt=review_attempt,
                    verdict=review.verdict.value,
                )
                return review
            except AgentOutputContractError as exc:
                error_record = store.write_artifact(
                    (
                        f"tasks/{task.id}/attempt-{attempt_number}/"
                        f"review-output-contract-error-{review_attempt}.json"
                    ),
                    _contract_error_payload(exc),
                    task_id=task.id,
                    kind="agent_output_contract_error",
                    media_type="application/json",
                    created_by=f"workflow-module:{self.module_id}",
                    input_refs=[task.id, run_id],
                )
                store.event(
                    "reviewer_output_invalid",
                    task_id=task.id,
                    attempt=attempt_number,
                    review_attempt=review_attempt,
                    expected_output=exc.expected_output,
                    details=list(exc.details),
                    artifact_id=error_record["artifact_id"],
                    retryable=review_attempt < REVIEW_CONTRACT_MAX_ATTEMPTS,
                )
                if review_attempt >= REVIEW_CONTRACT_MAX_ATTEMPTS:
                    raise
                contract_feedback = _contract_feedback(exc)
        raise AssertionError("unreachable")
