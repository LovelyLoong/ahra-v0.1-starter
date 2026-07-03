from __future__ import annotations

import asyncio
import contextlib
import hashlib
import threading
import time
import weakref
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures.thread import _worker
from dataclasses import replace
from pathlib import Path
from typing import Awaitable, TypeVar

from ahra.capabilities import CapabilityGrant as RuntimeCapabilityGrant, LocalRuntimeGateway
from ahra.ports import AgentDriver, AgentOutputContractError

from .checks import run_checks
from .driver import execute_task, review_task
from .git_ops import LocalGitWorkspaceProvider
from .models import (
    CriterionAssessment,
    DeterministicEvidence,
    ExecutionPolicy,
    PolicyEvidence,
    ReviewResult,
    ReviewVerdict,
    TaskAttemptRecord,
    TaskRunResult,
    TaskSpec,
    WorkReport,
    WorkflowOutcome,
    to_jsonable,
)
from .policy import ChangeSummary, evaluate_policy
from .review_contracts import enforce_task_review_contract
from .runtime import LocalRuntimeProvider
from .store import ReferenceRunStore

PATCH_EXCERPT_CHARS = 60_000
CONTRACT_ERROR_EXCERPT_CHARS = 20_000
AGENT_PHASE_CANCEL_GRACE_SECONDS = 1.0
CHECKS_SKIPPED_POLICY_FAILED = "skipped_policy_failed"
T = TypeVar("T")


class _AgentPhaseRunner:
    """Run an AgentDriver phase outside the scheduler event loop.

    Some provider SDK calls may not finish cancellation promptly. A daemon
    thread keeps the scheduler timeout path able to return terminal state while
    still requesting cooperative cancellation for responsive drivers.
    """

    def __init__(self, awaitable: Awaitable[T]) -> None:
        self.future: Future[T] = Future()
        self._awaitable = awaitable
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task[T] | None = None
        self._started = threading.Event()
        self._thread = threading.Thread(target=self._run, name="ahra-agent-phase", daemon=True)

    def start(self) -> None:
        self._thread.start()
        self._started.wait(timeout=1.0)

    def cancel(self) -> None:
        loop = self._loop
        task = self._task
        if loop is None or task is None or task.done():
            return
        loop.call_soon_threadsafe(task.cancel)

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        loop.set_default_executor(_DaemonThreadPoolExecutor(thread_name_prefix="ahra-agent-phase-io"))
        self._loop = loop
        asyncio.set_event_loop(loop)
        task = loop.create_task(self._awaitable)
        self._task = task
        self._started.set()
        try:
            result = loop.run_until_complete(task)
        except BaseException as exc:
            if not self.future.done():
                self.future.set_exception(exc)
        else:
            if not self.future.done():
                self.future.set_result(result)
        finally:
            if task.done():
                with contextlib.suppress(BaseException):
                    loop.run_until_complete(loop.shutdown_asyncgens())
                with contextlib.suppress(BaseException):
                    loop.run_until_complete(loop.shutdown_default_executor())
                loop.close()


class _DaemonThreadPoolExecutor(ThreadPoolExecutor):
    def _adjust_thread_count(self) -> None:
        if self._idle_semaphore.acquire(timeout=0):
            return

        def weakref_cb(_, q=self._work_queue):
            q.put(None)

        num_threads = len(self._threads)
        if num_threads < self._max_workers:
            name = "%s_%d" % (self._thread_name_prefix or self, num_threads)
            thread = threading.Thread(
                name=name,
                target=_worker,
                args=(weakref.ref(self, weakref_cb), self._work_queue, self._initializer, self._initargs),
                daemon=True,
            )
            thread.start()
            self._threads.add(thread)


def _excerpt(text: str, limit: int = PATCH_EXCERPT_CHARS, *, label: str = "patch") -> str:
    if len(text) <= limit:
        return text
    half = limit // 2
    return f"{text[:half]}\n\n... {label} truncated ...\n\n{text[-half:]}"


def _verification_claim_note(evidence: DeterministicEvidence) -> str | None:
    if not evidence.agent_reported_verification_commands:
        return None
    if evidence.check_execution_status == "completed":
        return None
    commands = ", ".join(evidence.agent_reported_verification_commands)
    reason = evidence.check_skip_reason or evidence.check_execution_status
    return (
        "Agent-reported verification commands were not executed or recorded by "
        f"the deterministic gate ({reason}): {commands}"
    )


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
    if evidence.check_execution_status != "completed":
        blockers.append(
            evidence.check_skip_reason
            or f"Deterministic checks were not completed: {evidence.check_execution_status}"
        )
    claim_note = _verification_claim_note(evidence)
    non_blocking_issues = (claim_note,) if claim_note else ()
    summary = "Semantic review was skipped because the deterministic gate failed."
    if evidence.check_execution_status != "completed":
        summary = (
            "Semantic review was skipped because the deterministic gate failed; "
            "deterministic checks were not executed."
        )
    return ReviewResult(
        verdict=ReviewVerdict.FAIL,
        summary=summary,
        criteria=(
            CriterionAssessment(
                criterion="Deterministic preconditions",
                passed=False,
                evidence="Required checks and policy must pass before semantic review.",
                concerns=tuple((*blockers, *non_blocking_issues)),
            ),
        ),
        blocking_issues=tuple(blockers),
        non_blocking_issues=non_blocking_issues,
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


def _with_agent_reported_verification(
    evidence: DeterministicEvidence,
    report: WorkReport,
) -> DeterministicEvidence:
    return replace(
        evidence,
        agent_reported_verification_commands=tuple(report.verification_commands_run),
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
        runtime_gateway: LocalRuntimeGateway | None = None,
        capability_grants: tuple[RuntimeCapabilityGrant, ...] = (),
        plan_id: str | None = None,
        node_id: str | None = None,
        actor: str = "executor",
        semantic_review_enabled: bool = True,
        preserve_failed_workspace: bool = False,
    ) -> None:
        self.driver = driver
        self.workspace_provider = workspace_provider or LocalGitWorkspaceProvider()
        self.runtime_provider = runtime_provider or LocalRuntimeProvider()
        self.runtime_profile_ref = runtime_profile_ref
        self.execution_policy = execution_policy or ExecutionPolicy()
        self.runtime_gateway = runtime_gateway
        self.capability_grants = capability_grants
        self.plan_id = plan_id
        self.node_id = node_id
        self.actor = actor
        self.semantic_review_enabled = semantic_review_enabled
        self.preserve_failed_workspace = preserve_failed_workspace
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
        policy = self._with_write_capability_violations(policy, files)
        mutated = patch_before_checks is not None and full_patch != patch_before_checks
        evidence = DeterministicEvidence(
            policy=policy,
            checks=tuple(checks),
            verification_mutated_workspace=mutated,
            verification_mutation_files=files if mutated else (),
            patch_excerpt=_excerpt(full_patch),
        )
        return evidence, full_patch

    def _capture_failure_patch(
        self,
        *,
        store: ReferenceRunStore,
        task: TaskSpec,
        workspace_ref: str,
        checkpoint: str,
        attempt_number: int,
        run_id: str,
    ) -> dict | None:
        """Best-effort capture of the failed work as an untrusted audit artifact."""
        try:
            failure_patch = self.workspace_provider.patch(workspace_ref, checkpoint)
        except Exception:
            return None
        if not failure_patch.strip():
            return None
        return store.write_artifact(
            f"tasks/{task.id}/attempt-{attempt_number}/failure.patch",
            failure_patch,
            task_id=task.id,
            kind="failure_patch",
            media_type="text/x-diff",
            created_by=f"workflow-module:{self.module_id}",
            input_refs=[task.id, run_id],
        )

    def _discard_or_preserve_failed_work(
        self,
        *,
        store: ReferenceRunStore,
        task: TaskSpec,
        workspace_ref: str,
        checkpoint: str,
        attempt_number: int,
        restore_patch_text: str | None = None,
    ) -> bool:
        """Roll back failed work, or keep it in the workspace when preservation is enabled.

        Returns True when the workspace was rolled back to the checkpoint.
        """
        if self.preserve_failed_workspace:
            if restore_patch_text is not None:
                self.workspace_provider.restore_patch(workspace_ref, checkpoint, restore_patch_text)
            store.event(
                "failed_workspace_preserved",
                task_id=task.id,
                attempt=attempt_number,
                workspace=self.workspace_provider.resolve_path(workspace_ref),
                checkpoint=checkpoint,
            )
            return False
        self.workspace_provider.rollback(workspace_ref, checkpoint)
        return True

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
                    evidence = replace(
                        pre_evidence,
                        check_execution_status=CHECKS_SKIPPED_POLICY_FAILED,
                        check_skip_reason=(
                            "Policy gate failed before verification checks; no deterministic "
                            "check records were produced."
                        ),
                    )
                evidence = _with_agent_reported_verification(evidence, report)
                store.event(
                    "deterministic_gate_finished",
                    task_id=task.id,
                    attempt=attempt_number,
                    passed=evidence.passed,
                    policy_passed=evidence.policy.passed,
                    required_checks_passed=evidence.required_checks_passed,
                    check_execution_status=evidence.check_execution_status,
                    check_skip_reason=evidence.check_skip_reason,
                    agent_reported_verification_command_count=len(
                        evidence.agent_reported_verification_commands
                    ),
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
                    review_evidence_kind = "semantic_review"
                    if self.semantic_review_enabled:
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
                            failure_patch_record = self._capture_failure_patch(
                                store=store,
                                task=task,
                                workspace_ref=workspace_ref,
                                checkpoint=checkpoint,
                                attempt_number=attempt_number,
                                run_id=run_id,
                            )
                            rolled_back = self._discard_or_preserve_failed_work(
                                store=store,
                                task=task,
                                workspace_ref=workspace_ref,
                                checkpoint=checkpoint,
                                attempt_number=attempt_number,
                            )
                            result = TaskRunResult(
                                run_id=run_id,
                                task_id=task.id,
                                status=WorkflowOutcome.ERROR,
                                checkpoint=checkpoint,
                                attempts=tuple(attempts),
                                message=(
                                    "Task review failed its output contract after bounded "
                                    "review retries and was "
                                    f"{'rolled back' if rolled_back else 'preserved in the failed workspace'}: {exc!r}"
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
                                refs=(
                                    [failure_patch_record["artifact_id"]]
                                    if failure_patch_record
                                    else None
                                ),
                            )
                            return result
                    else:
                        store.event(
                            "semantic_review_skipped",
                            task_id=task.id,
                            attempt=attempt_number,
                            reason="semantic review was not declared by node gate policy",
                        )
                        review_evidence_kind = "semantic_review_skipped"
                        review = ReviewResult(
                            verdict=ReviewVerdict.PASS,
                            summary="Semantic review was skipped because no semantic review gate was declared.",
                            criteria=tuple(
                                CriterionAssessment(
                                    criterion=criterion,
                                    passed=True,
                                    evidence="Deterministic L0 gates passed.",
                                )
                                for criterion in task.acceptance_criteria
                            ),
                            confidence=1.0,
                        )
                else:
                    review_evidence_kind = "semantic_review"
                    review = _deterministic_failure_review(evidence)

                store.write_evidence(
                    f"tasks/{task.id}/attempt-{attempt_number}/review.json",
                    review,
                    task_id=task.id,
                    kind=review_evidence_kind,
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
                rolled_back = self._discard_or_preserve_failed_work(
                    store=store,
                    task=task,
                    workspace_ref=workspace_ref,
                    checkpoint=checkpoint,
                    attempt_number=attempt_number,
                    restore_patch_text=(
                        patch_before_checks if evidence.verification_mutated_workspace else None
                    ),
                )
                result = TaskRunResult(
                    run_id=run_id,
                    task_id=task.id,
                    status=WorkflowOutcome.REJECTED,
                    checkpoint=checkpoint,
                    attempts=tuple(attempts),
                    message=(
                        "Task exhausted its bounded attempts and was rolled back."
                        if rolled_back
                        else "Task exhausted its bounded attempts; failed work was preserved in the workspace."
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
                failure_patch_record = self._capture_failure_patch(
                    store=store,
                    task=task,
                    workspace_ref=workspace_ref,
                    checkpoint=checkpoint,
                    attempt_number=attempt_number,
                    run_id=run_id,
                )
                rolled_back = self._discard_or_preserve_failed_work(
                    store=store,
                    task=task,
                    workspace_ref=workspace_ref,
                    checkpoint=checkpoint,
                    attempt_number=attempt_number,
                )
                result = TaskRunResult(
                    run_id=run_id,
                    task_id=task.id,
                    status=WorkflowOutcome.ERROR,
                    checkpoint=checkpoint,
                    attempts=tuple(attempts),
                    message=(
                        f"Task failed with an execution error and was rolled back: {exc!r}"
                        if rolled_back
                        else f"Task failed with an execution error; failed work was preserved in the workspace: {exc!r}"
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
                    refs=(
                        [failure_patch_record["artifact_id"]]
                        if failure_patch_record
                        else None
                    ),
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
        runner = _AgentPhaseRunner(awaitable)
        runner.start()
        worker = asyncio.wrap_future(runner.future)
        abandoned = False
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
                done, _ = await asyncio.wait({worker}, timeout=next_wait)
                if done:
                    return worker.result()
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
                    abandoned = await self._cancel_agent_phase(
                        runner,
                        worker,
                        phase=phase,
                        task=task,
                        attempt=attempt,
                        store=store,
                        reason="attempt_wall_timeout",
                    )
                    raise TimeoutError(
                        f"{phase} exceeded attempt wall timeout "
                        f"({policy.attempt_wall_timeout_seconds}s)"
                    )
                if now - run_started >= policy.run_deadline_seconds:
                    abandoned = await self._cancel_agent_phase(
                        runner,
                        worker,
                        phase=phase,
                        task=task,
                        attempt=attempt,
                        store=store,
                        reason="run_deadline",
                    )
                    raise TimeoutError(
                        f"{phase} exceeded run deadline ({policy.run_deadline_seconds}s)"
                    )
                if idle_elapsed >= policy.idle_timeout_seconds:
                    abandoned = await self._cancel_agent_phase(
                        runner,
                        worker,
                        phase=phase,
                        task=task,
                        attempt=attempt,
                        store=store,
                        reason="idle_timeout",
                    )
                    raise TimeoutError(
                        f"{phase} exceeded idle timeout ({policy.idle_timeout_seconds}s)"
                    )
        except BaseException:
            if not worker.done() and not abandoned:
                await self._cancel_agent_phase(
                    runner,
                    worker,
                    phase=phase,
                    task=task,
                    attempt=attempt,
                    store=store,
                    reason="external_cancellation",
                )
            raise

    async def _cancel_agent_phase(
        self,
        runner: _AgentPhaseRunner,
        worker: asyncio.Future[T],
        *,
        phase: str,
        task: TaskSpec,
        attempt: int,
        store: ReferenceRunStore,
        reason: str,
    ) -> bool:
        runner.cancel()
        done, _ = await asyncio.wait({worker}, timeout=AGENT_PHASE_CANCEL_GRACE_SECONDS)
        if done:
            with contextlib.suppress(BaseException):
                worker.result()
            return True
        store.event(
            "agent_phase_cancel_grace_exceeded",
            task_id=task.id,
            attempt=attempt,
            phase=phase,
            reason=reason,
            cancel_grace_seconds=AGENT_PHASE_CANCEL_GRACE_SECONDS,
        )
        return True

    def _changed_files_or_empty(self, workspace_ref: str, checkpoint: str) -> tuple[str, ...]:
        try:
            return tuple(self.workspace_provider.changed_files(workspace_ref, checkpoint))
        except Exception:
            return ()

    def _with_write_capability_violations(
        self,
        policy: PolicyEvidence,
        files: tuple[str, ...],
    ) -> PolicyEvidence:
        if self.runtime_gateway is None or not self.capability_grants:
            return policy
        plan_id = self.plan_id
        node_id = self.node_id
        if not plan_id or not node_id:
            return replace(policy, violations=tuple((*policy.violations, "capability context missing for filesystem.write authorization")))
        write_grants = tuple(grant for grant in self.capability_grants if grant.action == "filesystem.write")
        if not files:
            return policy
        violations = list(policy.violations)
        for relative_path in files:
            grant = _grant_for_resource(write_grants, relative_path)
            if grant is None:
                violations.append(f"capability grant missing for filesystem.write:{relative_path}")
                continue
            record = self.runtime_gateway.authorize_write_path(
                grant,
                plan_id=plan_id,
                node_id=node_id,
                actor=self.actor,
                relative_path=relative_path,
            )
            if not record.allowed:
                violations.append(f"capability denied filesystem.write:{relative_path}:{record.reason_code}")
        if tuple(violations) == policy.violations:
            return policy
        return replace(policy, violations=tuple(violations))

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


def _grant_for_resource(
    grants: tuple[RuntimeCapabilityGrant, ...],
    resource: str,
) -> RuntimeCapabilityGrant | None:
    normalized = resource.replace("\\", "/")
    for grant in grants:
        if any(_resource_matches(normalized, pattern) for pattern in grant.resources):
            return grant
    return None


def _resource_matches(resource: str, pattern: str) -> bool:
    import fnmatch

    normalized_pattern = pattern.replace("\\", "/")
    return resource == normalized_pattern or fnmatch.fnmatch(resource, normalized_pattern)
