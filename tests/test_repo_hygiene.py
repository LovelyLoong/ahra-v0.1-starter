from __future__ import annotations

import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TASKS_ROOT = REPO_ROOT / "work" / "tasks"


def _is_completed_task(task_dir: Path) -> bool:
    state_path = task_dir / "state.json"
    if not state_path.is_file():
        return False
    state = json.loads(state_path.read_text(encoding="utf-8"))
    return state.get("state") == "completed"


class RepositoryHygieneTests(unittest.TestCase):
    def test_completed_tasks_do_not_contain_development_worktrees(self) -> None:
        offenders: list[str] = []
        for task_dir in sorted(TASKS_ROOT.iterdir()):
            if not task_dir.is_dir() or not _is_completed_task(task_dir):
                continue
            offenders.extend(
                str(path.relative_to(REPO_ROOT))
                for path in task_dir.rglob("development-worktrees")
                if path.is_dir()
            )

        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
