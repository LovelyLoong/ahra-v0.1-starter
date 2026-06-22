from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from ahra.domain import RunStatus
from ahra.ports import (
    AgentDriver,
    AgentDriverRegistry,
    AgentRole,
    AgentRunRequest,
    AgentRunResult,
)
from ahra.workflow_modules import WorkflowModuleError
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
    GoalReviewResult,
    GoalSpec,
    NextStepDecision,
    PlanAction,
    ReviewResult,
    ReviewVerdict,
    TaskRunResult,
    TaskSpec,
    WorkReport,
    WorkflowOutcome,
)
from ahra.reference_runner.policy import ChangeSummary, evaluate_policy
from ahra.reference_runner.review_contracts import enforce_task_review_contract
from ahra.reference_runner.standard_harness import TaskHarness
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


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


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
                artifact_dir=str(Path(temp) / "artifacts"),
                run_id="RUN-invocation",
            )
            result = asyncio.run(run_workflow(request, drivers=registry))
            self.assertEqual(result.status, WorkflowOutcome.ACCEPTED)
            artifact_dir = Path(result.artifact_dir)
            self.assertTrue((artifact_dir / "workflow-run-request.json").exists())
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
                "approvalMode": "manual",
            },
        }
        request = workflow_run_request_from_document(document)
        self.assertIsNotNone(request.task)
        self.assertEqual(request.task.policy, ChangePolicy())

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
        standard = load_workflow_run_request(ROOT / "examples/workflow_runs/standard-task.yaml")
        loop = load_workflow_run_request(ROOT / "examples/workflow_runs/loop-goal.yaml")
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
