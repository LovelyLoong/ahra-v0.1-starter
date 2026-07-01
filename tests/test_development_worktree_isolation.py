from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from ahra.goal_operations import GoalOperationService
from ahra.ports import AgentRunResult
from ahra.reference_runner.git_ops import IsolatedGitWorkspaceProvider
from ahra.reference_runner.models import WorkReport

from tests.test_goal_operations import (
    CapturingRuntimeProvider,
    _init_git_workspace,
    _write_development_request,
)


class HostileResetDriver:
    def __init__(self) -> None:
        self.workspace_refs: list[Path] = []

    async def run(self, request):
        workspace = Path(str(request.workspace_ref)).resolve()
        self.workspace_refs.append(workspace)
        subprocess.run(["git", "-C", str(workspace), "reset", "--hard"], check=True)
        subprocess.run(["git", "-C", str(workspace), "clean", "-fd"], check=True)
        target = workspace / "alignment_stub.py"
        target.write_text("VALUE = 'isolated'\n", encoding="utf-8")
        return AgentRunResult(
            output=WorkReport(
                summary="Wrote allowed artifact after hostile git cleanup.",
                changed_files=("alignment_stub.py",),
                verification_commands_run=(),
                known_risks=(),
            )
        )


class FailingDriver:
    def __init__(self) -> None:
        self.workspace_refs: list[Path] = []

    async def run(self, request):
        workspace = Path(str(request.workspace_ref)).resolve()
        self.workspace_refs.append(workspace)
        raise RuntimeError("simulated executor failure")


class DevelopmentWorktreeIsolationTests(unittest.TestCase):
    def test_development_agent_uses_isolated_worktree_and_preserves_main_dirty_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request = _write_development_request(root, target_path="alignment_stub.py")
            main_workspace = (root / "workspace").resolve()
            sentinel = main_workspace / "uncommitted.txt"
            sentinel.write_text("keep me\n", encoding="utf-8")
            driver = HostileResetDriver()

            result = GoalOperationService(
                real_executor_driver=driver,
                real_executor_runtime_provider=CapturingRuntimeProvider(),
            ).start(request)

            self.assertEqual(result["planStatus"], "succeeded")
            self.assertEqual(result["goalStatus"], "succeeded")
            self.assertTrue(driver.workspace_refs)
            self.assertNotEqual(driver.workspace_refs[0], main_workspace)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep me\n")
            self.assertEqual((main_workspace / "alignment_stub.py").read_text(encoding="utf-8"), "VALUE = 'isolated'\n")
            worktree_root = root / ".ahra" / "artifacts" / "development-worktrees"
            self.assertFalse(any(worktree_root.rglob(".git")) if worktree_root.exists() else False)

    def test_development_worktree_preserved_after_failed_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request = _write_development_request(root, target_path="alignment_stub.py")
            driver = FailingDriver()

            result = GoalOperationService(
                real_executor_driver=driver,
                real_executor_runtime_provider=CapturingRuntimeProvider(),
            ).start(request)

            self.assertEqual(result["planStatus"], "failed")
            self.assertTrue(result["executionWorkspacePreserved"])
            self.assertTrue(driver.workspace_refs)
            for workspace in driver.workspace_refs:
                self.assertTrue(workspace.exists())

    def test_isolated_provider_materializes_only_allowlisted_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "repo"
            _init_git_workspace(source)
            provider = IsolatedGitWorkspaceProvider(
                worktree_root=root / "worktrees",
                allowed_globs=("alignment_*.py", "src/ahra/alignment_*.py"),
                denied_globs=("src/ahra/evidence_gate.py",),
            )
            execution_ref = provider.prepare_execution_workspace(
                str(source),
                run_id="RUN-filter",
                node_id="NODE-filter",
            )
            execution = Path(execution_ref)
            (execution / "alignment_allowed.py").write_text("VALUE = 1\n", encoding="utf-8")
            (execution / "README.md").write_text("do not copy\n", encoding="utf-8")
            blocked = execution / "src" / "ahra" / "evidence_gate.py"
            blocked.parent.mkdir(parents=True, exist_ok=True)
            blocked.write_text("do not copy\n", encoding="utf-8")

            provider.commit_all(execution_ref, "materialize allowed files")
            provider.finalize_execution_workspace(execution_ref)

            self.assertEqual((source / "alignment_allowed.py").read_text(encoding="utf-8"), "VALUE = 1\n")
            self.assertFalse((source / "README.md").exists())
            self.assertFalse((source / "src" / "ahra" / "evidence_gate.py").exists())
            self.assertFalse(execution.exists())


if __name__ == "__main__":
    unittest.main()
