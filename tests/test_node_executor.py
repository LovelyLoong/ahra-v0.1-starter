from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from ahra.capabilities import CapabilityGrant as RuntimeCapabilityGrant
from ahra.evidence_v2 import canonical_fingerprint
from ahra.node_executor import (
    NodeExecutionRequest,
    NodeExecutionResult,
    NodeExecutionStatus,
    NodeExecutorRegistry,
)
from ahra.ports import AgentDriver, AgentRole, AgentRunRequest, AgentRunResult
from ahra.reference_runner.bounded_task import (
    BOUNDED_TASK_EXECUTOR_RELEASE,
    BoundedTaskExecutor,
    build_standard_harness_compatibility_request,
    compatibility_plan_for_task,
    runtime_grants_for_node,
)
from ahra.reference_runner.models import (
    ChangePolicy,
    CheckSpec,
    CriterionAssessment,
    ReviewResult,
    ReviewVerdict,
    TaskSpec,
    WorkReport,
    WorkflowOutcome,
)
from ahra.reference_runner.store import FileRunStore


class NodeWritingDriver(AgentDriver):
    def __init__(self, *, target: str = "value.py", value: int = 2) -> None:
        self.target = target
        self.value = value
        self.executor_calls = 0
        self.reviewer_calls = 0

    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        if request.role == AgentRole.EXECUTOR:
            self.executor_calls += 1
            workspace = Path(str(request.workspace_ref))
            (workspace / self.target).write_text(f"VALUE = {self.value}\n", encoding="utf-8")
            return AgentRunResult(output=WorkReport(summary="Updated value", changed_files=(self.target,)))
        if request.role == AgentRole.TASK_REVIEWER:
            self.reviewer_calls += 1
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
        raise AssertionError(f"unexpected role: {request.role}")


class DummyNodeExecutor:
    node_type = "bounded_task"
    release_ref = BOUNDED_TASK_EXECUTOR_RELEASE

    async def execute(self, request: NodeExecutionRequest) -> NodeExecutionResult:
        return NodeExecutionResult(
            node_run_id="NRUN-dummy",
            plan_id=request.plan.plan_id,
            node_id=request.node.node_id,
            node_type=request.node.node_type,
            executor_release=self.release_ref,
            status=NodeExecutionStatus.ACCEPTED,
        )


class NodeExecutorTests(unittest.TestCase):
    def test_registry_resolves_by_node_type_and_immutable_release(self) -> None:
        registry = NodeExecutorRegistry()
        executor = DummyNodeExecutor()
        registry.register(executor)
        self.assertIs(registry.get("bounded_task", BOUNDED_TASK_EXECUTOR_RELEASE), executor)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            registry.register(executor)
        with self.assertRaisesRegex(ValueError, "immutable"):
            registry.get("bounded_task", "bounded-task-executor@latest")

    def test_bounded_task_executes_native_plan_node_with_capability_grants(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = _init_repo(Path(temp))
            task = _task()
            plan, node = compatibility_plan_for_task(task=task, workspace=repo, run_id="RUN-node")
            request = NodeExecutionRequest(
                plan=plan,
                node=node,
                capability_grants=runtime_grants_for_node(plan, node),
                workspace_ref=str(repo),
                branch="test-branch",
                run_id="RUN-node",
                payload={"task": task},
            )

            task_result, node_result = asyncio.run(
                BoundedTaskExecutor(
                    NodeWritingDriver(),
                    store=FileRunStore(Path(temp) / "artifacts"),
                ).execute_task(request)
            )

            self.assertEqual(task_result.status, WorkflowOutcome.ACCEPTED)
            self.assertEqual(node_result.status, NodeExecutionStatus.ACCEPTED)
            self.assertFalse(node_result.task_completed_state_update_attempted)
            self.assertTrue(node_result.artifact_refs)
            self.assertTrue(node_result.evidence_refs)
            artifact_dir = Path(task_result.artifact_dir)
            node_run = json.loads((artifact_dir / "nodes" / node.node_id / "node-run.json").read_text(encoding="utf-8"))
            self.assertTrue(node_run["spec"]["artifactRefs"])
            self.assertTrue(node_run["spec"]["evidenceRefs"])
            self.assertEqual(node_run["spec"]["gateRefs"], list(node.gate_refs))
            self.assertFalse(node_run["spec"]["taskCompletedStateUpdateAttempted"])
            self.assertTrue((artifact_dir / "nodes" / node.node_id / "node-gates.json").exists())
            event_types = _event_types(artifact_dir)
            self.assertIn("dev.ahra.workflow.node_run_started.v1", event_types)
            self.assertIn("dev.ahra.workflow.node_run_finished.v1", event_types)

    def test_process_exec_without_grant_fails_before_check_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = _init_repo(Path(temp))
            task = _task()
            plan, node = compatibility_plan_for_task(task=task, workspace=repo, run_id="RUN-no-process-grant")
            grants = tuple(grant for grant in runtime_grants_for_node(plan, node) if grant.action != "process.exec")
            request = NodeExecutionRequest(
                plan=plan,
                node=node,
                capability_grants=grants,
                workspace_ref=str(repo),
                branch="test-branch",
                run_id="RUN-no-process-grant",
                payload={"task": task},
            )

            task_result, node_result = asyncio.run(
                BoundedTaskExecutor(
                    NodeWritingDriver(),
                    store=FileRunStore(Path(temp) / "artifacts"),
                ).execute_task(request)
            )

            self.assertEqual(task_result.status, WorkflowOutcome.REJECTED)
            self.assertEqual(node_result.status, NodeExecutionStatus.REJECTED)
            evidence = _latest_deterministic_evidence(Path(task_result.artifact_dir), task.id)
            self.assertTrue(
                any("capability grant missing for process.exec" in check["stderr"] for check in evidence["checks"])
            )

    def test_filesystem_write_outside_runtime_grant_fails_deterministic_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = _init_repo(Path(temp))
            task = replace(_task(), policy=ChangePolicy(allowed_globs=("**",), protected_globs=(), sensitive_globs=()))
            plan, node = compatibility_plan_for_task(task=task, workspace=repo, run_id="RUN-write-denied")
            grants = tuple(
                _grant_with_resources(grant, ("value.py",))
                if grant.action == "filesystem.write"
                else grant
                for grant in runtime_grants_for_node(plan, node)
            )
            request = NodeExecutionRequest(
                plan=plan,
                node=node,
                capability_grants=grants,
                workspace_ref=str(repo),
                branch="test-branch",
                run_id="RUN-write-denied",
                payload={"task": task},
            )

            task_result, _ = asyncio.run(
                BoundedTaskExecutor(
                    NodeWritingDriver(target="blocked.py"),
                    store=FileRunStore(Path(temp) / "artifacts"),
                ).execute_task(request)
            )

            self.assertEqual(task_result.status, WorkflowOutcome.REJECTED)
            evidence = _latest_deterministic_evidence(Path(task_result.artifact_dir), task.id)
            self.assertTrue(
                any("capability grant missing for filesystem.write:blocked.py" in item for item in evidence["policy"]["violations"])
            )

    def test_semantic_review_runs_only_when_declared_by_gate_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = _init_repo(Path(temp))
            task = _task()
            plan, node = compatibility_plan_for_task(task=task, workspace=repo, run_id="RUN-l0-only")
            l0_node = replace(
                node,
                gate_refs=("GATE-bounded-task-l0",),
                gate_digests=(canonical_fingerprint({"gateRef": "GATE-bounded-task-l0"}),),
            )
            l0_plan = replace(plan, nodes=(l0_node,))
            driver = NodeWritingDriver()
            request = NodeExecutionRequest(
                plan=l0_plan,
                node=l0_node,
                capability_grants=runtime_grants_for_node(l0_plan, l0_node),
                workspace_ref=str(repo),
                branch="test-branch",
                run_id="RUN-l0-only",
                payload={"task": task},
            )

            task_result, node_result = asyncio.run(
                BoundedTaskExecutor(
                    driver,
                    store=FileRunStore(Path(temp) / "artifacts"),
                ).execute_task(request)
            )

            self.assertEqual(task_result.status, WorkflowOutcome.ACCEPTED)
            self.assertEqual(node_result.status, NodeExecutionStatus.ACCEPTED)
            self.assertEqual(driver.reviewer_calls, 0)
            evidence_manifest = json.loads((Path(task_result.artifact_dir) / "evidence-manifest.json").read_text(encoding="utf-8"))
            kinds = {record["kind"] for record in evidence_manifest["evidence"]}
            self.assertIn("semantic_review_skipped", kinds)

    def test_standard_harness_compatibility_matches_native_node_observable_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            native_root = root / "native"
            compatibility_root = root / "compatibility"
            native_root.mkdir()
            compatibility_root.mkdir()
            native_repo = _init_repo(native_root)
            compatibility_repo = _init_repo(compatibility_root)
            task = _task()
            native_plan, native_node = compatibility_plan_for_task(
                task=task,
                workspace=native_repo,
                run_id="RUN-native",
            )
            native_request = NodeExecutionRequest(
                plan=native_plan,
                node=native_node,
                capability_grants=runtime_grants_for_node(native_plan, native_node),
                workspace_ref=str(native_repo),
                branch="test-branch",
                run_id="RUN-native",
                payload={"task": task},
            )
            compatibility_request = build_standard_harness_compatibility_request(
                task=task,
                workspace=compatibility_repo,
                workspace_ref=str(compatibility_repo),
                branch="test-branch",
                run_id="RUN-compatibility",
            )

            native_result, _ = asyncio.run(
                BoundedTaskExecutor(
                    NodeWritingDriver(),
                    store=FileRunStore(root / "native-artifacts"),
                ).execute_task(native_request)
            )
            compatibility_result, _ = asyncio.run(
                BoundedTaskExecutor(
                    NodeWritingDriver(),
                    store=FileRunStore(root / "compatibility-artifacts"),
                ).execute_task(compatibility_request)
            )

            self.assertEqual(native_result.status, WorkflowOutcome.ACCEPTED)
            self.assertEqual(compatibility_result.status, WorkflowOutcome.ACCEPTED)
            self.assertEqual(
                _observable_semantics(Path(native_result.artifact_dir), task.id, native_node.node_id),
                _observable_semantics(
                    Path(compatibility_result.artifact_dir),
                    task.id,
                    compatibility_request.node.node_id,
                ),
            )


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
    _git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-q", "-m", "initial")
    return repo


def _task() -> TaskSpec:
    return TaskSpec(
        id="set-value",
        title="Set value to 2",
        objective="Set VALUE to 2",
        acceptance_criteria=("VALUE equals 2",),
        checks=(CheckSpec(name="value check", argv=(sys.executable, "-c", "import value; assert value.VALUE == 2")),),
        policy=ChangePolicy(
            allowed_globs=("value.py",),
            protected_globs=(),
            sensitive_globs=(),
            max_changed_files=1,
            max_added_lines=5,
            max_deleted_lines=5,
        ),
    )


def _event_types(artifact_dir: Path) -> set[str]:
    return {
        json.loads(line)["type"]
        for line in (artifact_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def _latest_deterministic_evidence(artifact_dir: Path, task_id: str) -> dict:
    evidence_path = artifact_dir / "tasks" / task_id / "attempt-2" / "deterministic-evidence.json"
    if not evidence_path.exists():
        evidence_path = artifact_dir / "tasks" / task_id / "attempt-1" / "deterministic-evidence.json"
    return json.loads(evidence_path.read_text(encoding="utf-8"))


def _observable_semantics(artifact_dir: Path, task_id: str, node_id: str) -> dict:
    artifact_manifest = json.loads((artifact_dir / "artifact-manifest.json").read_text(encoding="utf-8"))
    evidence_manifest = json.loads((artifact_dir / "evidence-manifest.json").read_text(encoding="utf-8"))
    node_run = json.loads((artifact_dir / "nodes" / node_id / "node-run.json").read_text(encoding="utf-8"))
    node_spec = node_run["spec"]
    return {
        "artifactKinds": sorted(
            record["kind"] for record in artifact_manifest["artifacts"] if record["task_id"] == task_id
        ),
        "evidenceKinds": sorted(
            record["kind"] for record in evidence_manifest["evidence"] if record["task_id"] == task_id
        ),
        "nodeType": node_spec["nodeType"],
        "status": node_spec["status"],
        "gateRefs": node_spec["gateRefs"],
        "terminalFailureRefs": node_spec["terminalFailureRefs"],
        "taskCompletedStateUpdateAttempted": node_spec["taskCompletedStateUpdateAttempted"],
        "artifactRefCount": len(node_spec["artifactRefs"]),
        "evidenceRefCount": len(node_spec["evidenceRefs"]),
    }


def _grant_with_resources(
    grant: RuntimeCapabilityGrant,
    resources: tuple[str, ...],
) -> RuntimeCapabilityGrant:
    return replace(grant, resources=resources, scope=resources)


if __name__ == "__main__":
    unittest.main()
