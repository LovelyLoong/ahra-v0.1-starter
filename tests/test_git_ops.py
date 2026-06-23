from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from ahra.reference_runner.git_ops import GitError, WorktreeManager


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


class WorktreeManagerTests(unittest.TestCase):
    def test_create_rejects_dirty_source_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = _init_repo(root)
            (repo / "value.txt").write_text("2\n", encoding="utf-8")
            manager = WorktreeManager(repo)
            base = _git(repo, "rev-parse", "HEAD")

            with self.assertRaisesRegex(GitError, "uncommitted changes"):
                manager.create(
                    run_id="RUN-dirty-source",
                    label="ahra/reference-runner",
                    base_ref=base,
                    destination=root / "worktree",
                )

    def test_generated_branch_names_do_not_collide_on_shared_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = _init_repo(root)
            manager = WorktreeManager(repo)
            base = _git(repo, "rev-parse", "HEAD")

            first = manager.create(
                run_id="RUN-codex-cli-probe-111111",
                label="ahra/reference-runner",
                base_ref=base,
                destination=root / "worktree-1",
            )
            second = manager.create(
                run_id="RUN-codex-cli-probe-222222",
                label="ahra/reference-runner",
                base_ref=base,
                destination=root / "worktree-2",
            )

            self.assertNotEqual(first.branch, second.branch)
            self.assertIn("RUN-codex-cli-probe", first.branch)


if __name__ == "__main__":
    unittest.main()
