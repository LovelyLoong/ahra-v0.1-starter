from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from ahra.domain import RunStatus
from ahra.ports import (
    AgentDriver,
    AgentDriverRegistry,
    AgentOutputContractError,
    AgentRole,
    AgentRunRequest,
    AgentRunResult,
)
from ahra.workflow_modules import WorkflowModuleError
from ahra.reference_runner.awkp_task import task_from_awkp_markdown
from ahra.reference_runner.checks import run_check
from ahra.reference_runner.invocation import (
    PlanApprovalDecision,
    WorkflowRunRequest,
    WorkflowResumeRequest,
    load_workflow_run_request,
    resume_workflow,
    run_workflow,
    workflow_run_request_from_document,
)
from ahra.reference_runner.loop_engineering import LoopEngine
from ahra.reference_runner.models import (
    ChangePolicy,
    CheckSpec,
    CriterionAssessment,
    DeterministicEvidence,
    ExecutionPolicy,
    GoalReviewResult,
    GoalSpec,
    NextStepDecision,
    PlanAction,
    ReviewResult,
    ReviewVerdict,
    SchedulerDecision,
    TaskRunResult,
    TaskSpec,
    WorkReport,
    WorkflowOutcome,
)
from ahra.reference_runner.policy import ChangeSummary, evaluate_policy
from ahra.reference_runner.review_contracts import enforce_task_review_contract
from ahra.reference_runner.task_harness import TaskHarness
from ahra.reference_runner.store import FileRunStore

ROOT = Path(__file__).resolve().parents[1]


class FakeDriver(AgentDriver):
    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        if request.role == AgentRole.EXECUTOR:
            workspace = Path(str(request.workspace_ref))
            (workspace / "value.py").write_text("VALUE = 2\n", encoding="utf-8")
            return AgentRunResult(output=WorkReport(summary="Updated value", changed_files=("value.py",)))
        if request.role == AgentRole.TASK_REVIEWER:
            task = request.payload["task"]
            return AgentRunResult(
                output=ReviewResult(
                    verdict=ReviewVerdict.PASS,
                    summary="Criterion is supported.",
                    criteria=tuple(
                        CriterionAssessment(
                            criterion=criterion,
                            passed=True,
                            evidence="Deterministic check passed.",
                        )
                        for criterion in task.acceptance_criteria
                    ),
                    confidence=0.99,
                )
            )
        if request.role == AgentRole.GOAL_REVIEWER:
            goal = request.payload["goal"]
            return AgentRunResult(
                output=GoalReviewResult(
                    verdict=ReviewVerdict.PASS,
                    summary="Goal passed.",
                    satisfied_criteria=goal.success_criteria,
                    confidence=0.99,
                )
            )
        if request.role == AgentRole.PLANNER:
            return AgentRunResult(
                output=NextStepDecision(action=PlanAction.ESCALATE, rationale="Not needed.")
            )
        raise AssertionError(f"unexpected role: {request.role}")


class PrepublishingAwkpDriver(FakeDriver):
    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        result = await super().run(request)
        if request.role == AgentRole.EXECUTOR:
            workspace = Path(str(request.workspace_ref))
            task = request.payload["task"]
            _publish_fixture_awkp_review(workspace, task.id, str(request.run_id))
        return result


class PlanningDriver(AgentDriver):
    def __init__(self) -> None:
        self.planner_calls = 0

    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        if request.role == AgentRole.EXECUTOR:
            workspace = Path(str(request.workspace_ref))
            task = request.payload["task"]
            value = 3 if task.id == "set-value-3" else 2
            (workspace / "value.py").write_text(f"VALUE = {value}\n", encoding="utf-8")
            return AgentRunResult(
                output=WorkReport(summary=f"Updated value to {value}", changed_files=("value.py",))
            )
        if request.role == AgentRole.TASK_REVIEWER:
            task = request.payload["task"]
            return AgentRunResult(
                output=ReviewResult(
                    verdict=ReviewVerdict.PASS,
                    summary="Criterion is supported.",
                    criteria=tuple(
                        CriterionAssessment(
                            criterion=criterion,
                            passed=True,
                            evidence="Deterministic check passed.",
                        )
                        for criterion in task.acceptance_criteria
                    ),
                    confidence=0.99,
                )
            )
        if request.role == AgentRole.GOAL_REVIEWER:
            goal = request.payload["goal"]
            return AgentRunResult(
                output=GoalReviewResult(
                    verdict=ReviewVerdict.PASS,
                    summary="Goal criteria are addressed.",
                    satisfied_criteria=goal.success_criteria,
                    confidence=0.99,
                )
            )
        if request.role == AgentRole.PLANNER:
            self.planner_calls += 1
            return AgentRunResult(
                output=NextStepDecision(
                    action=PlanAction.ADD_TASKS,
                    rationale="Set final value to satisfy the global gate.",
                    proposed_tasks=(_task_for_value(3),),
                )
            )
        raise AssertionError(f"unexpected role: {request.role}")


class ReviewerContractRetryDriver(AgentDriver):
    def __init__(self, *, invalid_review_responses: int) -> None:
        self.invalid_review_responses = invalid_review_responses
        self.executor_calls = 0
        self.reviewer_calls = 0

    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        if request.role == AgentRole.EXECUTOR:
            self.executor_calls += 1
            workspace = Path(str(request.workspace_ref))
            (workspace / "value.py").write_text("VALUE = 2\n", encoding="utf-8")
            return AgentRunResult(output=WorkReport(summary="Updated value", changed_files=("value.py",)))
        if request.role == AgentRole.TASK_REVIEWER:
            self.reviewer_calls += 1
            if self.reviewer_calls <= self.invalid_review_responses:
                raise AgentOutputContractError(
                    "ReviewResult",
                    "<root>: 'verdict' is a required property",
                    raw_output='{"status":"pass","findings":[]}',
                    details=("<root>: 'verdict' is a required property",),
                )
            task = request.payload["task"]
            return AgentRunResult(
                output=ReviewResult(
                    verdict=ReviewVerdict.PASS,
                    summary="Criterion is supported after contract retry.",
                    criteria=tuple(
                        CriterionAssessment(
                            criterion=criterion,
                            passed=True,
                            evidence="Deterministic check passed.",
                        )
                        for criterion in task.acceptance_criteria
                    ),
                    confidence=0.99,
                )
            )
        raise AssertionError(f"unexpected role: {request.role}")


class SlowExecutorDriver(AgentDriver):
    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        if request.role == AgentRole.EXECUTOR:
            await asyncio.sleep(2)
            return AgentRunResult(output=WorkReport(summary="too late"))
        if request.role == AgentRole.TASK_REVIEWER:
            return AgentRunResult(
                output=ReviewResult(
                    verdict=ReviewVerdict.PASS,
                    summary="not reached",
                    confidence=1.0,
                )
            )
        raise AssertionError(f"unexpected role: {request.role}")


class CancellationResistantExecutorDriver(AgentDriver):
    def __init__(self, *, cancel_delay_seconds: float = 5.0) -> None:
        self.cancel_delay_seconds = cancel_delay_seconds

    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        if request.role == AgentRole.EXECUTOR:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                await asyncio.sleep(self.cancel_delay_seconds)
                raise
        if request.role == AgentRole.TASK_REVIEWER:
            return AgentRunResult(
                output=ReviewResult(
                    verdict=ReviewVerdict.PASS,
                    summary="not reached",
                    confidence=1.0,
                )
            )
        raise AssertionError(f"unexpected role: {request.role}")


class ToThreadExecutorDriver(FakeDriver):
    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        if request.role == AgentRole.EXECUTOR:
            await asyncio.to_thread(lambda: None)
        return await super().run(request)


class ToThreadBlockingExecutorDriver(AgentDriver):
    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        if request.role == AgentRole.EXECUTOR:
            await asyncio.to_thread(time.sleep, 5.0)
            return AgentRunResult(output=WorkReport(summary="too late"))
        if request.role == AgentRole.TASK_REVIEWER:
            return AgentRunResult(
                output=ReviewResult(
                    verdict=ReviewVerdict.PASS,
                    summary="not reached",
                    confidence=1.0,
                )
            )
        raise AssertionError(f"unexpected role: {request.role}")


class FlakyExecutorDriver(FakeDriver):
    def __init__(self) -> None:
        self.executor_calls = 0

    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        if request.role == AgentRole.EXECUTOR:
            self.executor_calls += 1
            if self.executor_calls == 1:
                raise RuntimeError("transient executor failure")
        return await super().run(request)


class RejectingReviewerDriver(FakeDriver):
    def __init__(self) -> None:
        self.executor_calls = 0
        self.reviewer_calls = 0

    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        if request.role == AgentRole.EXECUTOR:
            self.executor_calls += 1
            return await super().run(request)
        if request.role == AgentRole.TASK_REVIEWER:
            self.reviewer_calls += 1
            task = request.payload["task"]
            return AgentRunResult(
                output=ReviewResult(
                    verdict=ReviewVerdict.FAIL,
                    summary="Reviewer rejected the attempted change.",
                    criteria=tuple(
                        CriterionAssessment(
                            criterion=criterion,
                            passed=False,
                            evidence="Reviewer found the criterion unsupported.",
                            concerns=("Reviewer rejected",),
                        )
                        for criterion in task.acceptance_criteria
                    ),
                    blocking_issues=("Reviewer rejected",),
                    confidence=0.9,
                )
            )
        return await super().run(request)


class RecordingRuntime:
    def __init__(self) -> None:
        self.command: tuple[str, ...] | None = None

    def provision(self, profile_ref: str, workspace_ref: str, identity: str) -> str:
        return workspace_ref

    def exec(self, handle: str, command: list[str], env: dict[str, str], deadline) -> dict[str, object]:
        self.command = tuple(command)
        return {"exit_code": 0, "timed_out": False, "stdout": "ok", "stderr": ""}

    def destroy(self, handle: str) -> None:
        return None


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def _live_asyncio_default_executor_threads() -> list[str]:
    return sorted(
        thread.name
        for thread in threading.enumerate()
        if thread.name.startswith("asyncio_") and thread.is_alive() and not thread.daemon
    )


def _live_non_daemon_agent_phase_threads() -> list[str]:
    prefixes = ("asyncio_", "ahra-agent-phase", "ahra-agent-phase-io")
    return sorted(
        thread.name
        for thread in threading.enumerate()
        if thread.name.startswith(prefixes) and thread.is_alive() and not thread.daemon
    )


def _init_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "value.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(
        repo,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-q",
        "-m",
        "initial",
    )
    return repo


def _write_awkp_task(
    repo: Path,
    *,
    state: str = "ready",
    depends_on: tuple[str, ...] = (),
    verification_lines: tuple[str, ...] = (),
) -> Path:
    task_id = "TASK-9001"
    task_dir = repo / "work" / "tasks" / task_id
    task_dir.mkdir(parents=True)
    (task_dir / "handoffs").mkdir()
    depends = "[" + ", ".join(depends_on) + "]"
    (task_dir / "task.md").write_text(
        "\n".join(
            [
                "---",
                "type: WorkItem",
                f"id: {task_id}",
                "schema_version: awkp/0.1",
                "title: Set value to 2 through formal workflow",
                "description: Exercise formal AWKP workflow publication.",
                "context_id: CTX-test",
                "priority: P1",
                "risk_level: R1",
                "requester: human:test",
                "reviewer: agent:verifier",
                "created_at: 2026-06-23T00:00:00Z",
                f"depends_on: {depends}",
                "input_refs: []",
                "output_contract:",
                "  - kind: code_change",
                "---",
                "",
                "# Goal",
                "",
                "Set VALUE to 2.",
                "",
                "# Scope",
                "",
                "- Update value.py only.",
                "",
                "# Non-goals",
                "",
                "- Do not complete the task without EvidenceGate.",
                "",
                "# Acceptance criteria",
                "",
                "- [ ] VALUE equals 2.",
                "",
                "# Verification method",
                "",
                *verification_lines,
                "",
            ]
        ),
        encoding="utf-8",
    )
    (task_dir / "state.json").write_text(
        json.dumps(
            {
                "schema_version": "awkp/0.1",
                "task_id": task_id,
                "context_id": "CTX-test",
                "state": state,
                "state_version": 1,
                "owner": None,
                "attempt": 0,
                "lease": None,
                "next_action": "Run formal workflow.",
                "pause_reason": None,
                "blockers": [],
                "artifact_refs": [],
                "evidence_refs": [],
                "updated_at": "2026-06-23T00:00:00Z",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (task_dir / "artifact-manifest.json").write_text(
        json.dumps({"schema_version": "awkp/0.1", "task_id": task_id, "artifacts": []}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    (task_dir / "evidence-manifest.json").write_text(
        json.dumps({"schema_version": "awkp/0.1", "task_id": task_id, "evidence": []}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    (task_dir / "events.jsonl").write_text(
        json.dumps(
            {
                "schema_version": "awkp/0.1",
                "event_id": f"EVT-{task_id}-0001",
                "idempotency_key": f"{task_id}:create",
                "task_id": task_id,
                "context_id": "CTX-test",
                "event_type": "task_created",
                "actor": "human:test",
                "occurred_at": "2026-06-23T00:00:00Z",
                "causation_id": None,
                "correlation_id": "CTX-test",
                "from_state": None,
                "to_state": state,
                "reason": "Fixture task.",
                "refs": ["task.md"],
            },
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    return task_dir


def _publish_fixture_awkp_review(workspace: Path, task_id: str, run_id: str) -> None:
    task_dir = workspace / "work" / "tasks" / task_id
    now = "2026-06-23T00:01:00Z"
    report_name = "implementation-report.json"
    report_path = task_dir / "evidence" / report_name
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_bytes = (
        json.dumps(
            {
                "schema_version": "ahra/test-implementation-report/0.1",
                "task_id": task_id,
                "run_id": run_id,
                "summary": "Executor prepublished task-local review evidence.",
            },
            indent=2,
        )
        + "\n"
    ).encode("utf-8")
    report_path.write_bytes(report_bytes)
    report_digest = hashlib.sha256(report_bytes).hexdigest()

    artifact_id = f"ART-{task_id}-0001"
    evidence_id = f"EVD-{task_id}-0001"
    artifact_manifest_path = task_dir / "artifact-manifest.json"
    evidence_manifest_path = task_dir / "evidence-manifest.json"
    artifact_manifest = json.loads(artifact_manifest_path.read_text(encoding="utf-8"))
    evidence_manifest = json.loads(evidence_manifest_path.read_text(encoding="utf-8"))
    artifact_manifest["artifacts"].append(
        {
            "artifact_id": artifact_id,
            "task_id": task_id,
            "kind": "implementation_report",
            "name": report_name,
            "uri": f"local://evidence/{report_name}",
            "sha256": report_digest,
            "media_type": "application/json",
            "created_by": f"agent:executor:{run_id}",
            "created_at": now,
            "input_refs": ["task.md"],
            "evidence_refs": [evidence_id],
            "supersedes": None,
        }
    )
    evidence_manifest["evidence"].append(
        {
            "evidence_id": evidence_id,
            "task_id": task_id,
            "kind": "implementation_report",
            "name": report_name,
            "uri": f"local://evidence/{report_name}",
            "sha256": report_digest,
            "media_type": "application/json",
            "created_by": f"agent:executor:{run_id}",
            "created_at": now,
            "refs": [artifact_id],
        }
    )
    artifact_manifest_path.write_text(json.dumps(artifact_manifest, indent=2) + "\n", encoding="utf-8")
    evidence_manifest_path.write_text(json.dumps(evidence_manifest, indent=2) + "\n", encoding="utf-8")

    handoff_path = task_dir / "handoffs" / "HANDOFF-0001.md"
    handoff_path.parent.mkdir(parents=True, exist_ok=True)
    handoff_path.write_text(
        "\n".join(
            [
                "---",
                "type: Handoff",
                f"id: HANDOFF-{task_id}-0001",
                "schema_version: awkp/0.1",
                "title: Fixture prepublished review",
                f"created_at: {now}",
                f"source_refs: [../task.md, ../state.json, ../evidence/{report_name}]",
                "---",
                "",
                "# Status",
                "",
                "Executor prepublished review evidence before the harness finalizer.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    event_path = task_dir / "events.jsonl"
    for index, event_type in enumerate(("artifact_published", "review_requested"), start=3):
        with event_path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "schema_version": "awkp/0.1",
                        "event_id": f"EVT-{task_id}-{index:04d}",
                        "idempotency_key": f"{task_id}:fixture:{event_type}:{run_id}",
                        "task_id": task_id,
                        "context_id": "CTX-test",
                        "event_type": event_type,
                        "actor": f"agent:executor:{run_id}",
                        "occurred_at": now,
                        "causation_id": f"EVT-{task_id}-0002" if index == 3 else f"EVT-{task_id}-0003",
                        "correlation_id": "CTX-test",
                        "from_state": "working" if index == 3 else "working",
                        "to_state": "working" if index == 3 else "review",
                        "reason": "Fixture executor prepublished review evidence.",
                        "refs": ["state.json", f"evidence/{report_name}"],
                    },
                    separators=(",", ":"),
                )
                + "\n"
            )

    state_path = task_dir / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update(
        {
            "state": "review",
            "state_version": int(state["state_version"]) + 1,
            "owner": None,
            "lease": None,
            "next_action": "Run independent EvidenceGate review.",
            "artifact_refs": [artifact_id],
            "evidence_refs": [evidence_id],
            "updated_at": now,
        }
    )
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def _task() -> TaskSpec:
    return _task_for_value(2)


def _task_for_value(value: int) -> TaskSpec:
    return TaskSpec(
        id=f"set-value-{value}" if value != 2 else "set-value",
        title=f"Set value to {value}",
        objective=f"Set VALUE to {value}",
        acceptance_criteria=(f"VALUE equals {value}",),
        checks=(
            CheckSpec(
                name=f"value {value} check",
                argv=(sys.executable, "-c", f"import value; assert value.VALUE == {value}"),
            ),
        ),
        policy=ChangePolicy(
            allowed_globs=("value.py",),
            protected_globs=(),
            sensitive_globs=(),
            max_changed_files=1,
            max_added_lines=5,
            max_deleted_lines=5,
        ),
    )


def _planning_goal() -> GoalSpec:
    return GoalSpec(
        id="value-planning-goal",
        title="Set final project value",
        objective="VALUE must equal 3",
        success_criteria=("VALUE equals 3",),
        tasks=(_task(),),
        global_checks=(
            CheckSpec(
                name="global value 3 check",
                argv=(sys.executable, "-c", "import value; assert value.VALUE == 3"),
            ),
        ),
        policy=ChangePolicy(
            allowed_globs=("value.py",),
            protected_globs=(),
            sensitive_globs=(),
            max_changed_files=1,
            max_added_lines=5,
            max_deleted_lines=5,
        ),
        max_cycles=3,
        max_total_tasks=3,
        dynamic_planning=True,
        auto_execute_proposed_tasks=False,
    )


def _minimal_task_mapping() -> dict[str, object]:
    return {
        "id": "minimal-task",
        "title": "Minimal task",
        "objective": "Exercise schema-valid defaults",
        "acceptance_criteria": ["The task can be loaded"],
    }


class ReferencePolicyAndReviewTests(unittest.TestCase):
    def test_parent_policy_is_additional_boundary(self) -> None:
        evidence = evaluate_policy(
            ChangeSummary(files=("README.md",), added_lines=1, deleted_lines=0),
            ChangePolicy(allowed_globs=("**",), protected_globs=(), sensitive_globs=()),
            ChangePolicy(allowed_globs=("src/**",), protected_globs=(), sensitive_globs=()),
        )
        self.assertFalse(evidence.passed)
        self.assertTrue(any("goal policy does not allow" in item for item in evidence.violations))

    def test_incomplete_reviewer_pass_is_converted_to_fail(self) -> None:
        task = TaskSpec(
            id="review-contract",
            title="Review contract",
            objective="Check criterion coverage",
            acceptance_criteria=("criterion A", "criterion B"),
        )
        review = ReviewResult(
            verdict=ReviewVerdict.PASS,
            summary="Looks good.",
            criteria=(
                CriterionAssessment(
                    criterion="criterion A",
                    passed=True,
                    evidence="Evidence A",
                ),
            ),
            confidence=0.9,
        )
        enforced = enforce_task_review_contract(task, review)
        self.assertEqual(enforced.verdict, ReviewVerdict.FAIL)
        self.assertTrue(any("omitted" in item for item in enforced.blocking_issues))


class StandardHarnessTests(unittest.TestCase):
    def test_task_harness_accepts_and_commits(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = _init_repo(Path(temp))
            result = asyncio.run(
                TaskHarness(FakeDriver()).run_task(
                    task=_task(),
                    workspace_ref=str(repo),
                    branch="test-branch",
                    run_id="RUN-test",
                    store=FileRunStore(Path(temp) / "artifacts"),
                )
            )
            self.assertEqual(result.status, WorkflowOutcome.ACCEPTED)
            self.assertEqual(result.status.to_ahra_run_status(), RunStatus.SUCCEEDED)
            self.assertIsNotNone(result.commit)
            self.assertEqual((repo / "value.py").read_text(encoding="utf-8"), "VALUE = 2\n")
            artifact_dir = Path(result.artifact_dir)
            events = [
                json.loads(line)
                for line in (artifact_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            schema = json.loads((ROOT / "contracts/schemas/event.schema.json").read_text(encoding="utf-8"))
            validator = Draft202012Validator(schema, format_checker=FormatChecker())
            for event in events:
                self.assertEqual(list(validator.iter_errors(event)), [])
            manifest = json.loads((artifact_dir / "artifact-manifest.json").read_text(encoding="utf-8"))
            evidence_manifest = json.loads((artifact_dir / "evidence-manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["artifacts"])
            self.assertTrue(evidence_manifest["evidence"])
            for record in (*manifest["artifacts"], *evidence_manifest["evidence"]):
                self.assertRegex(record["sha256"], r"^[a-f0-9]{64}$")
                self.assertTrue(record["uri"].startswith("local://"))

    def test_retryable_executor_failure_uses_bounded_next_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = _init_repo(Path(temp))
            driver = FlakyExecutorDriver()
            result = asyncio.run(
                TaskHarness(driver).run_task(
                    task=_task(),
                    workspace_ref=str(repo),
                    branch="test-branch",
                    run_id="RUN-flaky-executor",
                    store=FileRunStore(Path(temp) / "artifacts"),
                )
            )
            self.assertEqual(result.status, WorkflowOutcome.ACCEPTED)
            self.assertEqual(driver.executor_calls, 2)
            self.assertEqual([attempt.attempt for attempt in result.attempts], [1, 2])
            artifact_dir = Path(result.artifact_dir)
            events = [
                json.loads(line)
                for line in (artifact_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            first_error = next(
                event for event in events if event["type"] == "dev.ahra.workflow.attempt_error.v1"
            )
            self.assertTrue(first_error["data"]["retryable"])

    def test_agent_phase_timeout_does_not_wait_for_unresponsive_cancel_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = _init_repo(Path(temp))
            started = time.perf_counter()
            result = asyncio.run(
                TaskHarness(
                    CancellationResistantExecutorDriver(cancel_delay_seconds=5.0),
                    execution_policy=ExecutionPolicy(
                        max_attempts=1,
                        idle_timeout_seconds=1,
                        heartbeat_interval_seconds=1,
                        attempt_wall_timeout_seconds=1,
                        run_deadline_seconds=2,
                    ),
                ).run_task(
                    task=_task(),
                    workspace_ref=str(repo),
                    branch="test-branch",
                    run_id="RUN-unresponsive-cancel",
                    store=FileRunStore(Path(temp) / "artifacts"),
                )
            )
            elapsed = time.perf_counter() - started

            self.assertEqual(result.status, WorkflowOutcome.ERROR)
            self.assertLess(elapsed, 3.0)
            events = [
                json.loads(line)
                for line in (Path(result.artifact_dir) / "events.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertTrue(
                any(event["type"] == "dev.ahra.workflow.agent_phase_cancel_grace_exceeded.v1" for event in events)
            )

    def test_agent_phase_shutdown_closes_default_executor_threads(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = _init_repo(Path(temp))
            result = asyncio.run(
                TaskHarness(ToThreadExecutorDriver()).run_task(
                    task=_task(),
                    workspace_ref=str(repo),
                    branch="test-branch",
                    run_id="RUN-to-thread",
                    store=FileRunStore(Path(temp) / "artifacts"),
                )
            )

            self.assertEqual(result.status, WorkflowOutcome.ACCEPTED)
            deadline = time.perf_counter() + 1.0
            while _live_asyncio_default_executor_threads() and time.perf_counter() < deadline:
                time.sleep(0.01)
            self.assertEqual(_live_asyncio_default_executor_threads(), [])

    def test_agent_phase_timeout_does_not_leave_non_daemon_to_thread_worker(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = _init_repo(Path(temp))
            started = time.perf_counter()
            result = asyncio.run(
                TaskHarness(
                    ToThreadBlockingExecutorDriver(),
                    execution_policy=ExecutionPolicy(
                        max_attempts=1,
                        idle_timeout_seconds=1,
                        heartbeat_interval_seconds=1,
                        attempt_wall_timeout_seconds=1,
                        run_deadline_seconds=2,
                    ),
                ).run_task(
                    task=_task(),
                    workspace_ref=str(repo),
                    branch="test-branch",
                    run_id="RUN-to-thread-timeout",
                    store=FileRunStore(Path(temp) / "artifacts"),
                )
            )
            elapsed = time.perf_counter() - started

            self.assertEqual(result.status, WorkflowOutcome.ERROR)
            self.assertLess(elapsed, 3.0)
            self.assertEqual(_live_non_daemon_agent_phase_threads(), [])

    def test_local_project_python_check_uses_uv_environment(self) -> None:
        if shutil.which("uv") is None:
            self.skipTest("uv is not available")
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            (workspace / "pyproject.toml").write_text(
                "[project]\nname='test'\nversion='0.0.0'\n",
                encoding="utf-8",
            )
            runtime = RecordingRuntime()
            evidence = run_check(
                workspace,
                CheckSpec(name="check", argv=("python", "scripts\\check.py")),
                runtime=runtime,
            )
            self.assertEqual(runtime.command, ("uv", "run", "python", "-B", "scripts\\check.py"))
            self.assertEqual(evidence.argv, ("uv", "run", "python", "-B", "scripts\\check.py"))

    def test_reviewer_output_contract_retry_does_not_rerun_executor(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = _init_repo(Path(temp))
            driver = ReviewerContractRetryDriver(invalid_review_responses=1)
            result = asyncio.run(
                TaskHarness(driver).run_task(
                    task=_task(),
                    workspace_ref=str(repo),
                    branch="test-branch",
                    run_id="RUN-review-contract-retry",
                    store=FileRunStore(Path(temp) / "artifacts"),
                )
            )
            self.assertEqual(result.status, WorkflowOutcome.ACCEPTED)
            self.assertEqual(driver.executor_calls, 1)
            self.assertEqual(driver.reviewer_calls, 2)
            artifact_dir = Path(result.artifact_dir)
            events = [
                json.loads(line)
                for line in (artifact_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            event_types = {event["type"] for event in events}
            self.assertIn("dev.ahra.workflow.reviewer_output_invalid.v1", event_types)
            manifest = json.loads((artifact_dir / "artifact-manifest.json").read_text(encoding="utf-8"))
            names = {record["name"] for record in manifest["artifacts"]}
            self.assertIn("review-output-contract-error-1.json", names)

    def test_reviewer_output_contract_exhaustion_does_not_start_next_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = _init_repo(Path(temp))
            driver = ReviewerContractRetryDriver(invalid_review_responses=2)
            result = asyncio.run(
                TaskHarness(driver).run_task(
                    task=_task(),
                    workspace_ref=str(repo),
                    branch="test-branch",
                    run_id="RUN-review-contract-error",
                    store=FileRunStore(Path(temp) / "artifacts"),
                )
            )
            self.assertEqual(result.status, WorkflowOutcome.ERROR)
            self.assertEqual(driver.executor_calls, 1)
            self.assertEqual(driver.reviewer_calls, 2)
            self.assertEqual((repo / "value.py").read_text(encoding="utf-8"), "VALUE = 1\n")

    def test_reviewer_output_contract_retry_honors_max_attempts_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = _init_repo(Path(temp))
            driver = ReviewerContractRetryDriver(invalid_review_responses=2)
            result = asyncio.run(
                TaskHarness(
                    driver,
                    execution_policy=ExecutionPolicy(max_attempts=1),
                ).run_task(
                    task=_task(),
                    workspace_ref=str(repo),
                    branch="test-branch",
                    run_id="RUN-review-policy-limit",
                    store=FileRunStore(Path(temp) / "artifacts"),
                )
            )
            self.assertEqual(result.status, WorkflowOutcome.ERROR)
            self.assertEqual(driver.executor_calls, 1)
            self.assertEqual(driver.reviewer_calls, 1)
            artifact_dir = Path(result.artifact_dir)
            manifest = json.loads((artifact_dir / "artifact-manifest.json").read_text(encoding="utf-8"))
            names = {record["name"] for record in manifest["artifacts"]}
            self.assertIn("review-output-contract-error-1.json", names)
            self.assertNotIn("review-output-contract-error-2.json", names)

    def test_executor_timeout_records_terminal_failure_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = _init_repo(Path(temp))
            result = asyncio.run(
                TaskHarness(
                    SlowExecutorDriver(),
                    execution_policy=ExecutionPolicy(
                        max_attempts=1,
                        idle_timeout_seconds=1,
                        heartbeat_interval_seconds=1,
                        attempt_wall_timeout_seconds=1,
                        run_deadline_seconds=5,
                    ),
                ).run_task(
                    task=_task(),
                    workspace_ref=str(repo),
                    branch="test-branch",
                    run_id="RUN-timeout",
                    store=FileRunStore(Path(temp) / "artifacts"),
                )
            )
            self.assertEqual(result.status, WorkflowOutcome.ERROR)
            artifact_dir = Path(result.artifact_dir)
            self.assertTrue((artifact_dir / "tasks/set-value/terminal-failure.json").exists())
            events = [
                json.loads(line)
                for line in (artifact_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            event_types = {event["type"] for event in events}
            self.assertIn("dev.ahra.workflow.agent_heartbeat.v1", event_types)
            self.assertIn("dev.ahra.workflow.terminal_failure_recorded.v1", event_types)
            evidence_manifest = json.loads((artifact_dir / "evidence-manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(
                any(record["kind"] == "terminal_failure" for record in evidence_manifest["evidence"])
            )


class WorkflowInvocationTests(unittest.TestCase):
    def test_driver_registry_fails_closed(self) -> None:
        registry = AgentDriverRegistry()
        registry.register("fake-reference", FakeDriver())
        with self.assertRaisesRegex(ValueError, "duplicate"):
            registry.register("fake-reference", FakeDriver())
        with self.assertRaisesRegex(ValueError, "unknown"):
            registry.get("missing-driver")

    def test_workflow_run_request_starts_standard_harness(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = _init_repo(Path(temp))
            registry = AgentDriverRegistry()
            registry.register("fake-reference", FakeDriver())
            request = WorkflowRunRequest(
                name="test-standard-task",
                module_id="standard-harness",
                workspace_ref=str(repo),
                driver_ref="fake-reference",
                store_ref="local-file",
                approval_mode="manual",
                task=_task(),
                scheduler_decision=SchedulerDecision(
                    scheduler="agent:test-scheduler",
                    rationale="Fixture task should use a short bounded policy.",
                    escalation_policy="fail_closed",
                    execution_policy=ExecutionPolicy(
                        max_attempts=1,
                        idle_timeout_seconds=30,
                        heartbeat_interval_seconds=5,
                        attempt_wall_timeout_seconds=60,
                        run_deadline_seconds=120,
                    ),
                ),
                artifact_dir=str(Path(temp) / "artifacts"),
                run_id="RUN-invocation",
            )
            result = asyncio.run(run_workflow(request, drivers=registry))
            self.assertEqual(result.status, WorkflowOutcome.ACCEPTED)
            artifact_dir = Path(result.artifact_dir)
            self.assertTrue((artifact_dir / "workflow-run-request.json").exists())
            self.assertTrue((artifact_dir / "scheduler-decision.json").exists())
            self.assertTrue((artifact_dir / "workflow-run-result.json").exists())
            self.assertTrue((artifact_dir / "workspace.json").exists())
            self.assertTrue((artifact_dir / "artifact-manifest.json").exists())
            self.assertTrue((artifact_dir / "evidence-manifest.json").exists())
            self.assertEqual((repo / "value.py").read_text(encoding="utf-8"), "VALUE = 1\n")
            isolated_workspace = Path(result.result.workspace)
            self.assertNotEqual(isolated_workspace.resolve(), repo.resolve())
            self.assertTrue(isolated_workspace.is_relative_to(artifact_dir.resolve()))
            self.assertEqual(
                (isolated_workspace / "value.py").read_text(encoding="utf-8"),
                "VALUE = 2\n",
            )
            scheduler = json.loads((artifact_dir / "scheduler-decision.json").read_text(encoding="utf-8"))
            self.assertEqual(scheduler["scheduler"], "agent:test-scheduler")
            request_artifact = json.loads((artifact_dir / "workflow-run-request.json").read_text(encoding="utf-8"))
            self.assertEqual(request_artifact["task"]["max_attempts"], 1)

    def test_awkp_verification_parser_skips_non_command_notes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = _init_repo(Path(temp))
            task_dir = _write_awkp_task(
                repo,
                verification_lines=(
                    "- `python scripts\\check.py`",
                    "- `git diff --check`",
                    "- A failing workflow fixture that reaches the configured attempt limit.",
                ),
            )
            task = task_from_awkp_markdown(task_dir / "task.md")
            self.assertEqual(
                [check.argv for check in task.checks],
                [("python", "scripts\\check.py"), ("git", "diff", "--check")],
            )

    def test_formal_awkp_task_run_integrates_source_and_moves_task_to_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = _init_repo(Path(temp))
            task_dir = _write_awkp_task(repo)
            _git(repo, "add", ".")
            _git(
                repo,
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "-q",
                "-m",
                "add formal task",
            )
            registry = AgentDriverRegistry()
            registry.register("fake-reference", FakeDriver())
            request = workflow_run_request_from_document(
                {
                    "apiVersion": "ahra.dev/v1alpha1",
                    "kind": "WorkflowRunRequest",
                    "metadata": {"name": "formal-task-loader"},
                    "spec": {
                        "moduleId": "standard-harness",
                        "input": {"taskRef": str(task_dir / "task.md")},
                        "workspaceRef": str(repo),
                        "driverRef": "fake-reference",
                        "storeRef": "local-file",
                        "artifactDir": str(Path(temp) / "artifacts"),
                        "runId": "RUN-formal-awkp",
                        "approvalMode": "manual",
                    },
                }
            )
            result = asyncio.run(run_workflow(request, drivers=registry))
            self.assertEqual(result.status, WorkflowOutcome.ACCEPTED)
            self.assertEqual((repo / "value.py").read_text(encoding="utf-8"), "VALUE = 2\n")
            state = json.loads((task_dir / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["state"], "review")
            self.assertIsNone(state["lease"])
            self.assertTrue(state["artifact_refs"])
            self.assertTrue(state["evidence_refs"])
            self.assertTrue(any(path.name.startswith("HANDOFF-") for path in (task_dir / "handoffs").glob("*.md")))
            source_events = [
                json.loads(line)
                for line in (task_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(source_events[-1]["event_type"], "review_requested")
            run_events = [
                json.loads(line)
                for line in (Path(result.artifact_dir) / "events.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertTrue(
                any(event["type"] == "dev.ahra.workflow.source_workspace_integrated.v1" for event in run_events)
            )

    def test_formal_awkp_task_accepts_agent_prepublished_review_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = _init_repo(Path(temp))
            task_dir = _write_awkp_task(repo)
            _git(repo, "add", ".")
            _git(
                repo,
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "-q",
                "-m",
                "add formal task",
            )
            registry = AgentDriverRegistry()
            registry.register("prepublishing-reference", PrepublishingAwkpDriver())
            request = workflow_run_request_from_document(
                {
                    "apiVersion": "ahra.dev/v1alpha1",
                    "kind": "WorkflowRunRequest",
                    "metadata": {"name": "formal-task-prepublished-review"},
                    "spec": {
                        "moduleId": "standard-harness",
                        "input": {"taskRef": str(task_dir / "task.md")},
                        "workspaceRef": str(repo),
                        "driverRef": "prepublishing-reference",
                        "storeRef": "local-file",
                        "artifactDir": str(Path(temp) / "artifacts"),
                        "runId": "RUN-formal-awkp-prepublished-review",
                        "approvalMode": "manual",
                    },
                }
            )
            result = asyncio.run(run_workflow(request, drivers=registry))
            self.assertEqual(result.status, WorkflowOutcome.ACCEPTED)
            self.assertTrue((Path(result.artifact_dir) / "workflow-run-result.json").exists())
            self.assertEqual((repo / "value.py").read_text(encoding="utf-8"), "VALUE = 2\n")
            state = json.loads((task_dir / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["state"], "review")
            self.assertIsNone(state["lease"])
            artifact_manifest = json.loads((task_dir / "artifact-manifest.json").read_text(encoding="utf-8"))
            artifact_names = {record["name"] for record in artifact_manifest["artifacts"]}
            self.assertIn("implementation-report.json", artifact_names)
            self.assertIn("workflow-run-RUN-formal-awkp-prepublished-review.json", artifact_names)
            handoff_names = {path.name for path in (task_dir / "handoffs").glob("HANDOFF-*.md")}
            self.assertGreaterEqual(len(handoff_names), 2)
            source_events = [
                json.loads(line)
                for line in (task_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(source_events[-1]["event_type"], "review_requested")
            self.assertEqual(source_events[-1]["from_state"], "review")
            run_events = [
                json.loads(line)
                for line in (Path(result.artifact_dir) / "events.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertTrue(
                any(event["type"] == "dev.ahra.workflow.source_workspace_integrated.v1" for event in run_events)
            )

    def test_formal_awkp_task_exhausted_failure_publishes_failure_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = _init_repo(Path(temp))
            task_dir = _write_awkp_task(repo)
            _git(repo, "add", ".")
            _git(
                repo,
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "-q",
                "-m",
                "add formal task",
            )
            registry = AgentDriverRegistry()
            registry.register("rejecting-reference", RejectingReviewerDriver())
            request = workflow_run_request_from_document(
                {
                    "apiVersion": "ahra.dev/v1alpha1",
                    "kind": "WorkflowRunRequest",
                    "metadata": {"name": "formal-task-failure"},
                    "spec": {
                        "moduleId": "standard-harness",
                        "input": {"taskRef": str(task_dir / "task.md")},
                        "workspaceRef": str(repo),
                        "driverRef": "rejecting-reference",
                        "storeRef": "local-file",
                        "artifactDir": str(Path(temp) / "artifacts"),
                        "runId": "RUN-formal-awkp-failure",
                        "schedulerDecision": {
                            "scheduler": "agent:test-scheduler",
                            "rationale": "Exercise exhausted formal failure publication.",
                            "escalationPolicy": "fail_closed",
                            "executionPolicy": {"maxAttempts": 2},
                        },
                        "approvalMode": "manual",
                    },
                }
            )
            result = asyncio.run(run_workflow(request, drivers=registry))
            self.assertEqual(result.status, WorkflowOutcome.REJECTED)
            self.assertEqual((repo / "value.py").read_text(encoding="utf-8"), "VALUE = 1\n")

            state = json.loads((task_dir / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["state"], "review")
            self.assertNotEqual(state["state"], "completed")
            self.assertIsNone(state["lease"])
            self.assertEqual(state["attempt"], 1)
            self.assertTrue(state["artifact_refs"])
            self.assertTrue(state["evidence_refs"])
            self.assertTrue(state["blockers"])

            artifact_manifest = json.loads((task_dir / "artifact-manifest.json").read_text(encoding="utf-8"))
            evidence_manifest = json.loads((task_dir / "evidence-manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(
                any(record["kind"] == "workflow_failure_report" for record in artifact_manifest["artifacts"])
            )
            self.assertTrue(
                any(record["kind"] == "workflow_failure_report" for record in evidence_manifest["evidence"])
            )
            failure_report = task_dir / "evidence" / "workflow-run-RUN-formal-awkp-failure-failure.json"
            self.assertTrue(failure_report.exists())
            report = json.loads(failure_report.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "rejected")
            self.assertEqual(report["attempt_count"], 2)
            self.assertEqual(report["last_error"], "Reviewer rejected")
            self.assertTrue(report["terminal_failure_record"].endswith("terminal-failure.json"))
            self.assertTrue(any(path.name.startswith("HANDOFF-") for path in (task_dir / "handoffs").glob("*.md")))
            source_events = [
                json.loads(line)
                for line in (task_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(source_events[-1]["event_type"], "review_requested")
            self.assertIn("terminal failure", source_events[-1]["reason"])
            run_events = [
                json.loads(line)
                for line in (Path(result.artifact_dir) / "events.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertTrue(
                any(event["type"] == "dev.ahra.workflow.source_workspace_integrated.v1" for event in run_events)
            )

    def test_formal_awkp_task_requires_ready_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = _init_repo(Path(temp))
            task_dir = _write_awkp_task(repo, state="queued")
            _git(repo, "add", ".")
            _git(
                repo,
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "-q",
                "-m",
                "add queued task",
            )
            registry = AgentDriverRegistry()
            registry.register("fake-reference", FakeDriver())
            request = workflow_run_request_from_document(
                {
                    "apiVersion": "ahra.dev/v1alpha1",
                    "kind": "WorkflowRunRequest",
                    "metadata": {"name": "queued-task"},
                    "spec": {
                        "moduleId": "standard-harness",
                        "input": {"taskRef": str(task_dir / "task.md")},
                        "workspaceRef": str(repo),
                        "driverRef": "fake-reference",
                        "storeRef": "local-file",
                        "artifactDir": str(Path(temp) / "artifacts"),
                        "approvalMode": "manual",
                    },
                }
            )
            with self.assertRaisesRegex(ValueError, "requires AWKP task state 'ready'"):
                asyncio.run(run_workflow(request, drivers=registry))
            self.assertFalse((Path(temp) / "artifacts").exists())

    def test_run_workflow_rejects_invalid_direct_request_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = _init_repo(Path(temp))
            registry = AgentDriverRegistry()
            registry.register("fake-reference", FakeDriver())
            request = WorkflowRunRequest(
                name="test-invalid-approval",
                module_id="standard-harness",
                workspace_ref=str(repo),
                driver_ref="fake-reference",
                store_ref="local-file",
                approval_mode="banana",
                task=_task(),
                artifact_dir=str(Path(temp) / "artifacts"),
                run_id="RUN-invalid-approval",
            )
            with self.assertRaisesRegex(ValueError, "approvalMode"):
                asyncio.run(run_workflow(request, drivers=registry))
            self.assertEqual((repo / "value.py").read_text(encoding="utf-8"), "VALUE = 1\n")

    def test_unknown_workflow_module_fails_before_artifact_store_creation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = _init_repo(Path(temp))
            artifact_dir = Path(temp) / "artifacts"
            registry = AgentDriverRegistry()
            registry.register("fake-reference", FakeDriver())
            request = WorkflowRunRequest(
                name="test-unknown-module",
                module_id="missing-module",
                workspace_ref=str(repo),
                driver_ref="fake-reference",
                store_ref="local-file",
                approval_mode="manual",
                task=_task(),
                artifact_dir=str(artifact_dir),
                run_id="RUN-unknown-module",
            )
            with self.assertRaisesRegex(WorkflowModuleError, "unknown workflow module"):
                asyncio.run(run_workflow(request, drivers=registry))
            self.assertFalse(artifact_dir.exists())

    def test_document_loader_validates_workflow_run_request_schema(self) -> None:
        document = {
            "apiVersion": "ahra.dev/v1alpha1",
            "kind": "WorkflowRunRequest",
            "metadata": {"name": "invalid-approval"},
            "spec": {
                "moduleId": "standard-harness",
                "input": {"task": _minimal_task_mapping()},
                "workspaceRef": ".",
                "driverRef": "fake-reference",
                "storeRef": "local-file",
                "approvalMode": "banana",
            },
        }
        with self.assertRaisesRegex(ValueError, "schema validation failed.*approvalMode"):
            workflow_run_request_from_document(document)

    def test_minimal_embedded_task_uses_default_policy(self) -> None:
        document = {
            "apiVersion": "ahra.dev/v1alpha1",
            "kind": "WorkflowRunRequest",
            "metadata": {"name": "minimal-task"},
            "spec": {
                "moduleId": "standard-harness",
                "input": {"task": _minimal_task_mapping()},
                "workspaceRef": ".",
                "driverRef": "fake-reference",
                "storeRef": "local-file",
                "runtimeProfileRef": "examples/runtimes/local-worktree.yaml",
                "approvalMode": "manual",
            },
        }
        request = workflow_run_request_from_document(document)
        self.assertIsNotNone(request.task)
        self.assertEqual(request.task.policy, ChangePolicy())
        self.assertEqual(request.runtime_profile_ref, "examples/runtimes/local-worktree.yaml")

    def test_scheduler_decision_policy_loads_from_request_surface(self) -> None:
        document = {
            "apiVersion": "ahra.dev/v1alpha1",
            "kind": "WorkflowRunRequest",
            "metadata": {"name": "scheduled-task"},
            "spec": {
                "moduleId": "standard-harness",
                "input": {"task": _minimal_task_mapping()},
                "workspaceRef": ".",
                "driverRef": "fake-reference",
                "storeRef": "local-file",
                "schedulerDecision": {
                    "scheduler": "agent:codex",
                    "rationale": "Small task, use one attempt for fixture coverage.",
                    "escalationPolicy": "fail_closed",
                    "executionPolicy": {
                        "maxAttempts": 1,
                        "startupTimeoutSeconds": 10,
                        "idleTimeoutSeconds": 20,
                        "heartbeatIntervalSeconds": 5,
                        "attemptWallTimeoutSeconds": 30,
                        "runDeadlineSeconds": 60,
                    },
                },
                "approvalMode": "manual",
            },
        }
        request = workflow_run_request_from_document(document)
        self.assertEqual(request.scheduler_decision.scheduler, "agent:codex")
        self.assertEqual(request.scheduler_decision.execution_policy.max_attempts, 1)

    def test_invalid_scheduler_policy_fails_before_execution(self) -> None:
        document = {
            "apiVersion": "ahra.dev/v1alpha1",
            "kind": "WorkflowRunRequest",
            "metadata": {"name": "invalid-scheduler-policy"},
            "spec": {
                "moduleId": "standard-harness",
                "input": {"task": _minimal_task_mapping()},
                "workspaceRef": ".",
                "driverRef": "fake-reference",
                "storeRef": "local-file",
                "schedulerDecision": {
                    "scheduler": "agent:codex",
                    "rationale": "Invalid policy should fail closed.",
                    "escalationPolicy": "fail_closed",
                    "executionPolicy": {
                        "maxAttempts": 1,
                        "idleTimeoutSeconds": 60,
                        "heartbeatIntervalSeconds": 120,
                        "attemptWallTimeoutSeconds": 60,
                        "runDeadlineSeconds": 120,
                    },
                },
                "approvalMode": "manual",
            },
        }
        with self.assertRaisesRegex(ValueError, "heartbeat_interval_seconds"):
            workflow_run_request_from_document(document)

    def test_approval_mode_controls_loop_planning_behavior(self) -> None:
        outcomes = {}
        for approval_mode in ("manual", "auto", "disabled"):
            with self.subTest(approval_mode=approval_mode):
                envelope, driver = self._run_loop_request_with_approval_mode(approval_mode)
                outcomes[approval_mode] = envelope.status
                if approval_mode == "manual":
                    self.assertEqual(envelope.status, WorkflowOutcome.AWAITING_PLAN_APPROVAL)
                    self.assertIsNotNone(envelope.result.next_step)
                    self.assertEqual(driver.planner_calls, 1)
                elif approval_mode == "auto":
                    self.assertEqual(envelope.status, WorkflowOutcome.COMPLETE)
                    self.assertEqual(len(envelope.result.completed_tasks), 2)
                    self.assertEqual(driver.planner_calls, 1)
                else:
                    self.assertEqual(envelope.status, WorkflowOutcome.BLOCKED)
                    self.assertIsNone(envelope.result.next_step)
                    self.assertEqual(driver.planner_calls, 0)
        self.assertEqual(
            outcomes,
            {
                "manual": WorkflowOutcome.AWAITING_PLAN_APPROVAL,
                "auto": WorkflowOutcome.COMPLETE,
                "disabled": WorkflowOutcome.BLOCKED,
            },
        )

    def test_manual_loop_resume_requires_matching_plan_digest_and_completes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = _init_repo(Path(temp))
            driver = PlanningDriver()
            registry = AgentDriverRegistry()
            registry.register("planning-reference", driver)
            artifact_dir = Path(temp) / "artifacts"
            run_request = WorkflowRunRequest(
                name="test-loop-manual-resume",
                module_id="loop-engineering",
                workspace_ref=str(repo),
                driver_ref="planning-reference",
                store_ref="local-file",
                approval_mode="manual",
                goal=_planning_goal(),
                artifact_dir=str(artifact_dir),
                run_id="RUN-loop-resume",
            )
            paused = asyncio.run(run_workflow(run_request, drivers=registry))
            self.assertEqual(paused.status, WorkflowOutcome.AWAITING_PLAN_APPROVAL)
            isolated_workspace = Path(paused.result.workspace)
            self.assertNotEqual(isolated_workspace.resolve(), repo.resolve())
            self.assertEqual((repo / "value.py").read_text(encoding="utf-8"), "VALUE = 1\n")
            self.assertEqual(
                (isolated_workspace / "value.py").read_text(encoding="utf-8"),
                "VALUE = 2\n",
            )
            plan_artifact = artifact_dir / "cycles" / "1" / "next-step.json"
            plan_sha256 = hashlib.sha256(plan_artifact.read_bytes()).hexdigest()

            bad_resume = WorkflowResumeRequest(
                name="bad-resume",
                run_id="RUN-loop-resume",
                module_id="loop-engineering",
                workspace_ref=str(repo),
                driver_ref="planning-reference",
                store_ref="local-file",
                artifact_dir=str(artifact_dir),
                approval=PlanApprovalDecision(
                    actor="human:maintainer",
                    approved=True,
                    reason="Approve the proposed bounded task.",
                    plan_artifact="cycles/1/next-step.json",
                    expected_plan_sha256="0" * 64,
                ),
            )
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                asyncio.run(resume_workflow(bad_resume, drivers=registry))

            resume_request = WorkflowResumeRequest(
                name="approve-resume",
                run_id="RUN-loop-resume",
                module_id="loop-engineering",
                workspace_ref=str(repo),
                driver_ref="planning-reference",
                store_ref="local-file",
                artifact_dir=str(artifact_dir),
                approval=PlanApprovalDecision(
                    actor="human:maintainer",
                    approved=True,
                    reason="Approve the proposed bounded task.",
                    plan_artifact="cycles/1/next-step.json",
                    expected_plan_sha256=plan_sha256,
                    approved_task_ids=("set-value-3",),
                ),
            )
            resumed = asyncio.run(resume_workflow(resume_request, drivers=registry))
            self.assertEqual(resumed.status, WorkflowOutcome.COMPLETE)
            self.assertEqual(len(resumed.result.completed_tasks), 2)
            self.assertEqual(Path(resumed.result.workspace).resolve(), isolated_workspace.resolve())
            self.assertEqual((repo / "value.py").read_text(encoding="utf-8"), "VALUE = 1\n")
            self.assertEqual(
                (isolated_workspace / "value.py").read_text(encoding="utf-8"),
                "VALUE = 3\n",
            )
            self.assertTrue((artifact_dir / "workflow-resume-request.json").exists())
            self.assertTrue((artifact_dir / "workflow-resume-result.json").exists())
            manifest = json.loads((artifact_dir / "artifact-manifest.json").read_text(encoding="utf-8"))
            names = {record["name"] for record in manifest["artifacts"]}
            self.assertIn("workflow-run-request.json", names)
            self.assertIn("workspace.json", names)
            self.assertIn("workflow-resume-request.json", names)

    def test_examples_load_as_workflow_run_requests(self) -> None:
        standard = load_workflow_run_request(ROOT / "examples/workflow_runs/fixtures/standard-task.yaml")
        loop = load_workflow_run_request(ROOT / "examples/workflow_runs/fixtures/loop-goal.yaml")
        self.assertEqual(standard.module_id, "standard-harness")
        self.assertIsNotNone(standard.task)
        self.assertEqual(loop.module_id, "loop-engineering")
        self.assertIsNotNone(loop.goal)

    def _run_loop_request_with_approval_mode(
        self, approval_mode: str
    ) -> tuple[object, PlanningDriver]:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        repo = _init_repo(Path(temp.name))
        driver = PlanningDriver()
        registry = AgentDriverRegistry()
        registry.register("planning-reference", driver)
        request = WorkflowRunRequest(
            name=f"test-loop-{approval_mode}",
            module_id="loop-engineering",
            workspace_ref=str(repo),
            driver_ref="planning-reference",
            store_ref="local-file",
            approval_mode=approval_mode,
            goal=_planning_goal(),
            artifact_dir=str(Path(temp.name) / "artifacts"),
            run_id=f"RUN-loop-{approval_mode}",
        )
        return asyncio.run(run_workflow(request, drivers=registry)), driver


class LoopEngineeringTests(unittest.TestCase):
    def test_loop_engineering_completes_after_global_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = _init_repo(Path(temp))
            base_commit = _git(repo, "rev-parse", "HEAD")
            goal = GoalSpec(
                id="value-goal",
                title="Set project value",
                objective="VALUE must equal 2",
                success_criteria=("VALUE equals 2",),
                tasks=(_task(),),
                global_checks=(
                    CheckSpec(
                        name="global value check",
                        argv=(sys.executable, "-c", "import value; assert value.VALUE == 2"),
                    ),
                ),
                policy=ChangePolicy(
                    allowed_globs=("value.py",),
                    protected_globs=(),
                    sensitive_globs=(),
                    max_changed_files=1,
                    max_added_lines=5,
                    max_deleted_lines=5,
                ),
            )
            result = asyncio.run(
                LoopEngine(FakeDriver()).run_goal(
                    goal=goal,
                    workspace_ref=str(repo),
                    branch="test-branch",
                    base_commit=base_commit,
                    run_id="RUN-goal",
                    store=FileRunStore(Path(temp) / "artifacts"),
                )
            )
            self.assertEqual(result.status, WorkflowOutcome.COMPLETE)
            self.assertEqual(result.status.to_ahra_run_status(), RunStatus.SUCCEEDED)
            self.assertIsNotNone(result.global_evidence)
            self.assertTrue(result.global_evidence.passed)


if __name__ == "__main__":
    unittest.main()
