from __future__ import annotations

import asyncio
import contextlib
import hashlib
import time
from pathlib import Path
from typing import Awaitable, TypeVar

from ahra.ports import AgentDriver, AgentOutputContractError

from .checks import run_checks
from .driver import execute_task, review_task
from .git_ops import LocalGitWorkspaceProvider
from .models import (
    CriterionAssessment,
    DeterministicEvidence,
    ExecutionPolicy,
    ReviewResult,
    ReviewVerdict,
    TaskAttemptRecord,
    TaskRunResult,
    TaskSpec,
    WorkflowOutcome,
    to_jsonable,
)
from .policy import ChangeSummary, evaluate_policy
from .review_contracts import enforce_task_review_contract
from .runtime import LocalRuntimeProvider
from .store import ReferenceRunStore

PATCH_EXCERPT_CHARS = 60_000
CONTRACT_ERROR_EXCERPT_CHARS = 20_000
T = TypeVar("T")


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


def _last_attempt_error(attempts: tuple[TaskAttemptRecord, ...]) -> str | None:
    for attempt in reversed(attempts):
        if attempt.error:
            return attempt.error
        if attempt.review and attempt.review.blocking_issues:
            return "; ".join(attempt.review.blocking_issues)
        if attempt.review and attempt.review.verdict != ReviewVerdict.PASS:
            return attempt.review.summary
    return None


def _record_terminal_failure(
    *,
    store: ReferenceRunStore,
    task: TaskSpec,
    result: TaskRunResult,
    execution_policy: ExecutionPolicy,
    refs: list[str] | None = None,
) -> None:
    record = store.write_evidence(
        f"tasks/{task.id}/terminal-failure.json",
        {
            "schema_version": "ahra/workflow-terminal-failure/0.1",
            "task_id": task.id,
            "run_id": result.run_id,
            "status": result.status.value,
            "summary": result.message,
            "attempt_count": len(result.attempts),
            "last_error": _last_attempt_error(result.attempts),
            "execution_policy": to_jsonable(execution_policy),
            "workspace": result.workspace,
            "branch": result.branch,
            "checkpoint": result.checkpoint,
            "artifact_dir": result.artifact_dir,
            "refs": refs or [],
            "attempts": [to_jsonable(attempt) for attempt in result.attempts],
        },
        task_id=task.id,
        kind="terminal_failure",
        refs=refs or [],
    )
    store.event(
        "terminal_failure_recorded",
        task_id=task.id,
        status=result.status.value,
        attempt_count=len(result.attempts),
        evidence_id=record["evidence_id"],
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
        execution_policy: ExecutionPolicy | None = None,
    ) -> None:
        self.driver = driver
        self.workspace_provider = workspace_provider or LocalGitWorkspaceProvider()
        self.runtime_provider = runtime_provider or LocalRuntimeProvider()
        self.runtime_profile_ref = runtime_profile_ref
        self.execution_policy = execution_policy or ExecutionPolicy()
        self._run_started_monotonic: float | None = None

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
        self._run_started_monotonic = time.monotonic()
        store.event("task_started", module_id=self.module_id, task_id=task.id, checkpoint=checkpoint)
        max_attempts = min(task.max_attempts, self.execution_policy.max_attempts)

        for attempt_number in range(1, max_attempts + 1):
            store.event("attempt_started", task_id=task.id, attempt=attempt_number)
            try:
                store.event("executor_started", task_id=task.id, attempt=attempt_number)
                report = await self._await_agent_phase(
                    execute_task(
                        self.driver,
                        task=task,
                        workspace=workspace,
                        feedback=feedback,
                        run_id=run_id,
                        attempt=attempt_number,
                        runtime_profile_ref=self.runtime_profile_ref,
                    ),
                    phase="executor",
                    task=task,
                    attempt=attempt_number,
                    store=store,
                    workspace_ref=workspace_ref,
                    checkpoint=checkpoint,
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
                            workspace_ref=workspace_ref,
                            checkpoint=checkpoint,
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
                        result = TaskRunResult(
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
                        _record_terminal_failure(
                            store=store,
                            task=task,
                            result=result,
                            execution_policy=self.execution_policy,
                        )
                        return result
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

                if attempt_number < max_attempts:
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
                rejected_patch_record = store.write_artifact(
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
                _record_terminal_failure(
                    store=store,
                    task=task,
                    result=result,
                    execution_policy=self.execution_policy,
                    refs=[rejected_patch_record["artifact_id"]],
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
                    retryable=attempt_number < max_attempts,
                    error=repr(exc),
                )
                if attempt_number < max_attempts:
                    feedback = f"The harness raised an execution error: {exc!r}. Recover safely."
                    continue
                self.workspace_provider.rollback(workspace_ref, checkpoint)
                result = TaskRunResult(
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
                _record_terminal_failure(
                    store=store,
                    task=task,
                    result=result,
                    execution_policy=self.execution_policy,
                )
                return result

        raise AssertionError("unreachable")

    async def _await_agent_phase(
        self,
        awaitable: Awaitable[T],
        *,
        phase: str,
        task: TaskSpec,
        attempt: int,
        store: ReferenceRunStore,
        workspace_ref: str,
        checkpoint: str,
    ) -> T:
        policy = self.execution_policy
        phase_started = time.monotonic()
        run_started = self._run_started_monotonic or phase_started
        last_progress = phase_started
        last_files = self._changed_files_or_empty(workspace_ref, checkpoint)
        worker = asyncio.create_task(awaitable)
        try:
            while True:
                now = time.monotonic()
                phase_elapsed = now - phase_started
                run_elapsed = now - run_started
                wall_remaining = policy.attempt_wall_timeout_seconds - phase_elapsed
                run_remaining = policy.run_deadline_seconds - run_elapsed
                idle_remaining = policy.idle_timeout_seconds - (now - last_progress)
                next_wait = max(
                    0.001,
                    min(
                        policy.heartbeat_interval_seconds,
                        wall_remaining,
                        run_remaining,
                        idle_remaining,
                    ),
                )
                try:
                    return await asyncio.wait_for(asyncio.shield(worker), timeout=next_wait)
                except TimeoutError:
                    now = time.monotonic()
                    files = self._changed_files_or_empty(workspace_ref, checkpoint)
                    if files != last_files:
                        last_files = files
                        last_progress = now
                    idle_elapsed = now - last_progress
                    store.event(
                        "agent_heartbeat",
                        task_id=task.id,
                        attempt=attempt,
                        phase=phase,
                        elapsed_seconds=round(now - phase_started, 3),
                        idle_seconds=round(idle_elapsed, 3),
                        changed_files=list(files),
                        heartbeat_interval_seconds=policy.heartbeat_interval_seconds,
                        idle_timeout_seconds=policy.idle_timeout_seconds,
                        attempt_wall_timeout_seconds=policy.attempt_wall_timeout_seconds,
                        run_deadline_seconds=policy.run_deadline_seconds,
                    )
                    if now - phase_started >= policy.attempt_wall_timeout_seconds:
                        raise TimeoutError(
                            f"{phase} exceeded attempt wall timeout "
                            f"({policy.attempt_wall_timeout_seconds}s)"
                        )
                    if now - run_started >= policy.run_deadline_seconds:
                        raise TimeoutError(
                            f"{phase} exceeded run deadline ({policy.run_deadline_seconds}s)"
                        )
                    if idle_elapsed >= policy.idle_timeout_seconds:
                        raise TimeoutError(
                            f"{phase} exceeded idle timeout ({policy.idle_timeout_seconds}s)"
                        )
        except BaseException:
            if not worker.done():
                worker.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await worker
            raise

    def _changed_files_or_empty(self, workspace_ref: str, checkpoint: str) -> tuple[str, ...]:
        try:
            return tuple(self.workspace_provider.changed_files(workspace_ref, checkpoint))
        except Exception:
            return ()

    async def _review_with_contract_retries(
        self,
        *,
        task: TaskSpec,
        report,
        evidence: DeterministicEvidence,
        full_patch: str,
        workspace: Path,
        workspace_ref: str,
        checkpoint: str,
        run_id: str,
        attempt_number: int,
        store: ReferenceRunStore,
    ) -> ReviewResult:
        contract_feedback: str | None = None
        max_review_attempts = self.execution_policy.max_attempts
        for review_attempt in range(1, max_review_attempts + 1):
            store.event(
                "reviewer_started",
                task_id=task.id,
                attempt=attempt_number,
                review_attempt=review_attempt,
            )
            try:
                review = await self._await_agent_phase(
                    review_task(
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
                    ),
                    phase="task_review",
                    task=task,
                    attempt=attempt_number,
                    store=store,
                    workspace_ref=workspace_ref,
                    checkpoint=checkpoint,
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
                    retryable=review_attempt < max_review_attempts,
                )
                if review_attempt >= max_review_attempts:
                    raise
                contract_feedback = _contract_feedback(exc)
        raise AssertionError("unreachable")
