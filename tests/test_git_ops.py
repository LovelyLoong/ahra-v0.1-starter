from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from ahra.reference_runner.git_ops import (
    GitError,
    IsolatedGitWorkspaceProvider,
    WorktreeManager,
    changed_files,
    cleanup_transient_tool_artifacts,
    fast_forward,
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
    (repo / "value.txt").write_text("1\n", encoding="utf-8")
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


def _worktree_list_contains(repo: Path, path: Path) -> bool:
    output = _git(repo, "worktree", "list", "--porcelain").replace("\\", "/")
    return str(path).replace("\\", "/") in output


class WorktreeManagerTests(unittest.TestCase):
    def test_create_allows_dirty_source_worktree_but_integration_rejects_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = _init_repo(root)
            (repo / "value.txt").write_text("2\n", encoding="utf-8")
            manager = WorktreeManager(repo)
            base = _git(repo, "rev-parse", "HEAD")

            workspace = manager.create(
                run_id="RUN-dirty-source",
                label="ahra/reference-runner",
                base_ref=base,
                destination=root / "worktree",
            )

            self.assertEqual((workspace.path / "value.txt").read_text(encoding="utf-8"), "1\n")
            self.assertEqual((repo / "value.txt").read_text(encoding="utf-8"), "2\n")
            with self.assertRaisesRegex(GitError, "uncommitted changes"):
                fast_forward(repo, workspace.branch)

    def test_cleanup_removes_untracked_numeric_backup_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = _init_repo(root)
            (repo / "value.txt").write_text("2\n", encoding="utf-8")
            (repo / "value.txt~1234").write_text("2\n", encoding="utf-8")

            removed = cleanup_transient_tool_artifacts(repo)

            self.assertEqual(removed, ("value.txt~1234",))
            self.assertFalse((repo / "value.txt~1234").exists())
            self.assertEqual(changed_files(repo, _git(repo, "rev-parse", "HEAD")), ("value.txt",))

    def test_cleanup_keeps_numeric_backup_with_distinct_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = _init_repo(root)
            (repo / "value.txt").write_text("2\n", encoding="utf-8")
            (repo / "value.txt~1234").write_text("backup\n", encoding="utf-8")

            removed = cleanup_transient_tool_artifacts(repo)

            self.assertEqual(removed, ())
            self.assertTrue((repo / "value.txt~1234").exists())
            files = changed_files(repo, _git(repo, "rev-parse", "HEAD"))
            self.assertEqual(files, ("value.txt", "value.txt~1234"))

    def test_generated_branch_names_do_not_collide_on_shared_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = _init_repo(root)
            manager = WorktreeManager(repo)
            base = _git(repo, "rev-parse", "HEAD")

            first = manager.create(
                run_id="RUN-shared-prefix-probe-111111",
                label="ahra/reference-runner",
                base_ref=base,
                destination=root / "worktree-1",
            )
            second = manager.create(
                run_id="RUN-shared-prefix-probe-222222",
                label="ahra/reference-runner",
                base_ref=base,
                destination=root / "worktree-2",
            )

            self.assertNotEqual(first.branch, second.branch)
            self.assertIn("RUN-shared-prefix-probe", first.branch)


class IsolatedGitWorkspaceProviderTests(unittest.TestCase):
    def test_finalize_removes_worktree_after_successful_propagation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = _init_repo(root)
            provider = IsolatedGitWorkspaceProvider(
                worktree_root=root / "development-worktrees",
                allowed_globs=("*.txt",),
                denied_globs=(),
            )
            execution_ref = provider.prepare_execution_workspace(
                str(repo),
                run_id="RUN-success",
                node_id="NODE-success",
            )
            execution_path = Path(execution_ref)

            (execution_path / "value.txt").write_text("2\n", encoding="utf-8")
            provider.commit_all(execution_ref, "materialize execution result")
            provider.finalize_execution_workspace(execution_ref)

            self.assertEqual((repo / "value.txt").read_text(encoding="utf-8"), "2\n")
            self.assertFalse(execution_path.exists())
            self.assertFalse((root / "development-worktrees").exists())
            self.assertFalse(_worktree_list_contains(repo, execution_path))

    def test_finalize_retains_worktree_when_propagation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = _init_repo(root)
            provider = IsolatedGitWorkspaceProvider(
                worktree_root=root / "development-worktrees",
                allowed_globs=("nested/*",),
                denied_globs=(),
            )
            execution_ref = provider.prepare_execution_workspace(
                str(repo),
                run_id="RUN-failure",
                node_id="NODE-failure",
            )
            execution_path = Path(execution_ref)

            (execution_path / "nested").mkdir()
            (execution_path / "nested" / "value.txt").write_text("2\n", encoding="utf-8")
            (repo / "nested").write_text("source conflict\n", encoding="utf-8")

            with self.assertRaises(OSError):
                provider.commit_all(execution_ref, "materialize execution result")

            provider.finalize_execution_workspace(execution_ref)

            self.assertTrue(execution_path.exists())
            self.assertTrue(_worktree_list_contains(repo, execution_path))


if __name__ == "__main__":
    unittest.main()
