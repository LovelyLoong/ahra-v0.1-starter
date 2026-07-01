from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ahra.adapters import (
    HOSTILE_AGENT_DRIVER_REF,
    HostileAgentDriver,
    HostileScenario,
)
from ahra.goal_operations import (
    DEVELOPMENT_BOUNDED_PROFILE_REF,
    GoalOperationProfileRegistry,
    GoalOperationService,
    REAL_BOUNDED_EXECUTOR_REF,
)
from ahra.ports import AgentDriver, AgentDriverRegistry
from ahra.reference_runner.runtime import LocalRuntimeProvider
from ahra.verification import VerificationExecutionReport, VerificationSelection

from tests.test_goal_operations import (
    CapturingRuntimeProvider,
    _write_development_request,
)


class HostileAgentDriverContractTests(unittest.TestCase):
    def test_driver_satisfies_agent_driver_port(self) -> None:
        driver = HostileAgentDriver(scenario=HostileScenario.FAIL)
        self.assertIsInstance(driver, AgentDriver)

    def test_driver_registers_under_immutable_version_ref(self) -> None:
        registry = AgentDriverRegistry()
        driver = HostileAgentDriver(scenario=HostileScenario.FAIL)
        registry.register(HOSTILE_AGENT_DRIVER_REF, driver)
        self.assertIs(registry.get(HOSTILE_AGENT_DRIVER_REF), driver)
        self.assertIn(HOSTILE_AGENT_DRIVER_REF, registry.refs())

    def test_hostile_driver_is_not_on_default_path(self) -> None:
        # The default development executor is the real bounded executor, not the
        # hostile replay adapter. The hostile driver is opt-in only.
        profiles = GoalOperationProfileRegistry()
        development = profiles.get(DEVELOPMENT_BOUNDED_PROFILE_REF)
        self.assertEqual(development.executor_adapter_ref, REAL_BOUNDED_EXECUTOR_REF)
        self.assertNotEqual(HOSTILE_AGENT_DRIVER_REF, REAL_BOUNDED_EXECUTOR_REF)
        registry = AgentDriverRegistry()
        self.assertNotIn(HOSTILE_AGENT_DRIVER_REF, registry.refs())


class D1DestructiveGitIsolationTests(unittest.TestCase):
    """Re-proves TASK-0074 worktree isolation for free via the HostileAgentDriver."""

    def test_destructive_git_preserves_main_tree_and_materializes_allowlisted_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request = _write_development_request(root, target_path="alignment_stub.py")
            main_workspace = (root / "workspace").resolve()
            sentinel = main_workspace / "uncommitted.txt"
            sentinel.write_text("keep me\n", encoding="utf-8")
            driver = HostileAgentDriver(scenario=HostileScenario.DESTRUCTIVE_GIT)

            result = GoalOperationService(
                real_executor_driver=driver,
                real_executor_runtime_provider=CapturingRuntimeProvider(),
            ).start(request)

            self.assertEqual(result["planStatus"], "succeeded")
            self.assertEqual(result["goalStatus"], "succeeded")
            # The destructive git ran inside the throwaway worktree, not the main tree.
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep me\n")
            self.assertEqual(
                (main_workspace / "alignment_stub.py").read_text(encoding="utf-8"),
                "VALUE = 'isolated'\n",
            )
            # The throwaway worktree was removed after the run.
            worktree_root = root / ".ahra" / "artifacts" / "development-worktrees"
            self.assertFalse(worktree_root.exists() and any(worktree_root.rglob(".git")))


class D2OutOfAllowlistWriteTests(unittest.TestCase):
    """Re-proves the TASK-0071 write allowlist: a blacklisted write never reaches
    the governed workspace, whether caught by the capability policy gate or the
    IsolatedGitWorkspaceProvider materialization filter."""

    def test_blacklisted_write_is_not_propagated_into_main_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request = _write_development_request(root, target_path="alignment_stub.py")
            main_workspace = (root / "workspace").resolve()
            sentinel = main_workspace / "uncommitted.txt"
            sentinel.write_text("keep me\n", encoding="utf-8")
            driver = HostileAgentDriver(
                scenario=HostileScenario.OUT_OF_ALLOWLIST_WRITE,
                blacklisted_path="src/ahra/evidence_gate.py",
            )

            result = GoalOperationService(
                real_executor_driver=driver,
                real_executor_runtime_provider=CapturingRuntimeProvider(),
            ).start(request)

            # The blacklisted write violates the capability grant; the run must
            # not succeed and the blacklisted path must never land in the main tree.
            self.assertEqual(result["planStatus"], "failed")
            self.assertFalse((main_workspace / "src" / "ahra" / "evidence_gate.py").exists())
            # The main tree's uncommitted sentinel survives the hostile run.
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep me\n")
            self.assertTrue(result["executionWorkspacePreserved"])
            self.assertTrue(Path(result["executionWorkspaceRef"]).exists())


class D4MaxAttemptsTests(unittest.TestCase):
    """Re-proves the TASK-0075 P3 invariant: a node with retryPolicy.maxAttempts=1
    executes exactly one attempt even when the executor always fails."""

    def test_max_attempts_one_runs_exactly_one_attempt_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request = _write_development_request(root, target_path="alignment_stub.py")
            driver = HostileAgentDriver(scenario=HostileScenario.FAIL)

            result = GoalOperationService(
                real_executor_driver=driver,
                real_executor_runtime_provider=CapturingRuntimeProvider(),
            ).start(request)

            self.assertEqual(result["planStatus"], "failed")
            # The development bounded_task node declares retryPolicy.maxAttempts: 1.
            # The always-failing executor must be invoked exactly once.
            self.assertEqual(len(driver.invocations), 1)


class D3NonGbkSubprocessTests(unittest.TestCase):
    """Re-proves the TASK-0075 P4 invariant: subprocess output containing bytes
    that cannot decode as the Windows default (GBK) does not raise
    UnicodeDecodeError because the subprocess calls pin encoding='utf-8'."""

    def test_local_runtime_exec_decodes_non_gbk_bytes_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            provider = LocalRuntimeProvider()
            script = (
                "import sys\n"
                "sys.stdout.buffer.write(b'pre\\xff\\xfe\\x80post')\n"
                "sys.stdout.flush()\n"
                "sys.stderr.buffer.write(b'err\\xff\\x80')\n"
                "sys.stderr.flush()\n"
            )
            deadline = datetime.now(timezone.utc) + timedelta(seconds=15)
            result = provider.exec(
                handle=str(Path(temp)),
                command=[sys.executable, "-c", script],
                env={},
                deadline=deadline,
            )
            self.assertNotIn("UnicodeDecodeError", result["stdout"])
            self.assertNotIn("UnicodeDecodeError", result["stderr"])
            self.assertIn("pre", result["stdout"])
            self.assertIn("post", result["stdout"])
            self.assertEqual(result["exit_code"], 0)


class D5NoneGateSelectionTests(unittest.TestCase):
    """Re-proves the TASK-0075 P2 invariant: a None gate-selection at the wall is
    treated as an empty selection and does not raise 'NoneType has no len()'."""

    def test_none_selected_gate_refs_treated_as_empty(self) -> None:
        selection = VerificationSelection(
            selected_gate_refs=None,  # type: ignore[arg-type]
            full_gate_refs=None,  # type: ignore[arg-type]
            affected_claim_refs=None,  # type: ignore[arg-type]
            reused_evidence_refs=None,  # type: ignore[arg-type]
            stale_evidence_refs=None,  # type: ignore[arg-type]
            rationale=None,  # type: ignore[arg-type]
        )
        report = VerificationExecutionReport(
            selection=selection,
            attempts=(),
            reused_evidence_refs=(),
        )
        # Must not raise TypeError on len(None).
        self.assertTrue(report.passed)
        self.assertEqual(report.gate_execution_integrity, 1.0)
        self.assertEqual(report.to_dict()["selection"]["selectedGateRefs"], [])


if __name__ == "__main__":
    unittest.main()
