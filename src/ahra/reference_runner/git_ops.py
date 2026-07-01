from __future__ import annotations

import fnmatch
import os
import re
import hashlib
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitError(RuntimeError):
    pass


def _git_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("GIT_AUTHOR_NAME", "AHRA Harness Agent")
    env.setdefault("GIT_AUTHOR_EMAIL", "ahra-harness-agent@local")
    env.setdefault("GIT_COMMITTER_NAME", "AHRA Harness Agent")
    env.setdefault("GIT_COMMITTER_EMAIL", "ahra-harness-agent@local")
    return env


def run_git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=_git_env(),
        check=False,
    )
    if check and result.returncode != 0:
        command = " ".join(["git", "-C", str(repo), *args])
        raise GitError(f"{command} failed ({result.returncode}): {result.stderr.strip()}")
    return result


def run_git_with_input(
    repo: Path,
    *args: str,
    input_text: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        input=input_text,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=_git_env(),
        check=False,
    )
    if check and result.returncode != 0:
        command = " ".join(["git", "-C", str(repo), *args])
        raise GitError(f"{command} failed ({result.returncode}): {result.stderr.strip()}")
    return result


def ensure_git_repo(repo: Path) -> None:
    result = run_git(repo, "rev-parse", "--is-inside-work-tree", check=False)
    if result.returncode != 0 or result.stdout.strip() != "true":
        raise GitError(f"not a Git work tree: {repo}")


def current_head(repo: Path) -> str:
    return run_git(repo, "rev-parse", "HEAD").stdout.strip()


def ensure_clean_worktree(repo: Path) -> None:
    output = run_git(repo, "status", "--porcelain", check=True).stdout.strip()
    if output:
        raise GitError(
            "source worktree has uncommitted changes; commit or stash them before "
            "integrating workflow results"
        )


def slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.")
    return cleaned[:48] or "run"


@dataclass(frozen=True, slots=True)
class Workspace:
    source_repo: Path
    path: Path
    branch: str
    base_ref: str
    base_commit: str


class WorktreeManager:
    def __init__(self, source_repo: Path) -> None:
        self.source_repo = source_repo.resolve()
        ensure_git_repo(self.source_repo)

    def create(
        self,
        *,
        run_id: str,
        label: str,
        base_ref: str,
        destination: Path,
        branch_name: str | None = None,
    ) -> Workspace:
        destination = destination.resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise GitError(f"worktree destination already exists: {destination}")
        base_commit = run_git(self.source_repo, "rev-parse", base_ref).stdout.strip()
        run_slug = slug(run_id)
        run_hash = hashlib.sha1(run_id.encode("utf-8")).hexdigest()[:8]
        branch = branch_name or f"ahra/{slug(label)}/{run_slug[:24]}-{run_hash}"
        run_git(
            self.source_repo,
            "worktree",
            "add",
            "-b",
            branch,
            str(destination),
            base_commit,
        )
        return Workspace(
            source_repo=self.source_repo,
            path=destination,
            branch=branch,
            base_ref=base_ref,
            base_commit=base_commit,
        )

    def remove(self, workspace: Workspace, *, force: bool = False) -> None:
        args = ["worktree", "remove"]
        if force:
            args.append("--force")
        args.append(str(workspace.path))
        run_git(self.source_repo, *args)


def add_intent_to_add(repo: Path) -> None:
    run_git(repo, "add", "-N", "--", ".", check=False)


def changed_files(repo: Path, checkpoint: str) -> tuple[str, ...]:
    add_intent_to_add(repo)
    output = run_git(repo, "diff", "--name-only", checkpoint, "--").stdout
    return tuple(sorted({line.strip() for line in output.splitlines() if line.strip()}))


def patch(repo: Path, checkpoint: str) -> str:
    add_intent_to_add(repo)
    return run_git(
        repo,
        "diff",
        "--no-ext-diff",
        "--binary",
        "--unified=3",
        checkpoint,
        "--",
    ).stdout


def numstat(repo: Path, checkpoint: str) -> tuple[int, int]:
    add_intent_to_add(repo)
    output = run_git(repo, "diff", "--numstat", checkpoint, "--").stdout
    added = 0
    deleted = 0
    for line in output.splitlines():
        parts = line.split("\t", 2)
        if len(parts) < 2:
            continue
        if parts[0].isdigit():
            added += int(parts[0])
        if parts[1].isdigit():
            deleted += int(parts[1])
    return added, deleted


def rollback(repo: Path, checkpoint: str) -> None:
    run_git(repo, "reset", "--hard", checkpoint)
    run_git(repo, "clean", "-fd")


def restore_patch(repo: Path, checkpoint: str, patch_text: str) -> None:
    rollback(repo, checkpoint)
    if patch_text.strip():
        run_git_with_input(repo, "apply", "--whitespace=nowarn", input_text=patch_text)


def commit_all(repo: Path, message: str) -> str:
    run_git(repo, "add", "-A")
    staged = run_git(repo, "diff", "--cached", "--quiet", check=False)
    if staged.returncode == 0:
        return current_head(repo)
    if staged.returncode != 1:
        raise GitError(f"unable to inspect staged changes: {staged.stderr.strip()}")
    run_git(
        repo,
        "-c",
        "user.name=AHRA Harness Agent",
        "-c",
        "user.email=ahra-harness-agent@local",
        "commit",
        "-m",
        message,
    )
    return current_head(repo)


def fast_forward(repo: Path, ref: str) -> str:
    ensure_clean_worktree(repo)
    run_git(repo, "merge", "--ff-only", ref)
    return current_head(repo)


class LocalGitWorkspaceProvider:
    """Reference WorkspaceProvider backed by a local Git worktree."""

    def resolve_path(self, workspace_ref: str) -> str:
        return str(Path(workspace_ref).resolve())

    def current_head(self, workspace_ref: str) -> str:
        return current_head(Path(workspace_ref))

    def changed_files(self, workspace_ref: str, checkpoint: str) -> list[str]:
        return list(changed_files(Path(workspace_ref), checkpoint))

    def numstat(self, workspace_ref: str, checkpoint: str) -> tuple[int, int]:
        return numstat(Path(workspace_ref), checkpoint)

    def patch(self, workspace_ref: str, checkpoint: str) -> str:
        return patch(Path(workspace_ref), checkpoint)

    def restore_patch(self, workspace_ref: str, checkpoint: str, patch_text: str) -> None:
        restore_patch(Path(workspace_ref), checkpoint, patch_text)

    def rollback(self, workspace_ref: str, checkpoint: str) -> None:
        rollback(Path(workspace_ref), checkpoint)

    def commit_all(self, workspace_ref: str, message: str) -> str:
        return commit_all(Path(workspace_ref), message)

    def fast_forward(self, workspace_ref: str, ref: str) -> str:
        return fast_forward(Path(workspace_ref), ref)


class IsolatedGitWorkspaceProvider:
    """WorkspaceProvider that runs an agent in a throwaway git worktree."""

    def __init__(
        self,
        *,
        source_provider: LocalGitWorkspaceProvider | None = None,
        worktree_root: Path,
        allowed_globs: tuple[str, ...],
        denied_globs: tuple[str, ...] = (),
    ) -> None:
        self.source_provider = source_provider or LocalGitWorkspaceProvider()
        self.worktree_root = Path(worktree_root)
        self.allowed_globs = tuple(allowed_globs)
        self.denied_globs = tuple(denied_globs)
        self._sessions: dict[str, tuple[str, Workspace]] = {}

    def prepare_execution_workspace(
        self,
        workspace_ref: str,
        *,
        run_id: str,
        node_id: str,
    ) -> str:
        source = Path(self.source_provider.resolve_path(workspace_ref)).resolve()
        ensure_git_repo(source)
        destination = (
            self.worktree_root
            / slug(run_id)
            / f"{slug(node_id)}-{hashlib.sha1(node_id.encode('utf-8')).hexdigest()[:8]}"
        )
        workspace = WorktreeManager(source).create(
            run_id=run_id,
            label=node_id,
            base_ref="HEAD",
            destination=destination,
        )
        execution_ref = str(workspace.path)
        self._sessions[execution_ref] = (str(source), workspace)
        return execution_ref

    def finalize_execution_workspace(self, workspace_ref: str) -> None:
        execution_ref = str(Path(workspace_ref).resolve())
        session = self._sessions.pop(execution_ref, None)
        if session is None:
            return
        source_ref, workspace = session
        source = Path(source_ref)
        manager = WorktreeManager(source)
        try:
            manager.remove(workspace, force=True)
        finally:
            run_git(source, "branch", "-D", workspace.branch, check=False)
            run_git(source, "worktree", "prune", check=False)

    def resolve_path(self, workspace_ref: str) -> str:
        return str(Path(workspace_ref).resolve())

    def current_head(self, workspace_ref: str) -> str:
        return current_head(Path(workspace_ref))

    def changed_files(self, workspace_ref: str, checkpoint: str) -> list[str]:
        return list(changed_files(Path(workspace_ref), checkpoint))

    def numstat(self, workspace_ref: str, checkpoint: str) -> tuple[int, int]:
        return numstat(Path(workspace_ref), checkpoint)

    def patch(self, workspace_ref: str, checkpoint: str) -> str:
        return patch(Path(workspace_ref), checkpoint)

    def restore_patch(self, workspace_ref: str, checkpoint: str, patch_text: str) -> None:
        restore_patch(Path(workspace_ref), checkpoint, patch_text)

    def rollback(self, workspace_ref: str, checkpoint: str) -> None:
        rollback(Path(workspace_ref), checkpoint)

    def commit_all(self, workspace_ref: str, message: str) -> str:
        execution_path = Path(workspace_ref).resolve()
        session = self._sessions.get(str(execution_path))
        if session is None:
            return commit_all(execution_path, message)

        source_ref, workspace = session
        source = Path(source_ref).resolve()
        for relative_path in changed_files(execution_path, workspace.base_commit):
            if not self._is_materializable(relative_path):
                continue
            source_file = (execution_path / relative_path).resolve()
            target_file = (source / relative_path).resolve()
            if not self._is_inside(target_file, source) or not source_file.is_file():
                continue
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, target_file)
        return current_head(source)

    def fast_forward(self, workspace_ref: str, ref: str) -> str:
        return fast_forward(Path(workspace_ref), ref)

    def _is_materializable(self, relative_path: str) -> bool:
        normalized = relative_path.replace("\\", "/")
        if any(fnmatch.fnmatch(normalized, pattern.replace("\\", "/")) for pattern in self.denied_globs):
            return False
        return any(fnmatch.fnmatch(normalized, pattern.replace("\\", "/")) for pattern in self.allowed_globs)

    @staticmethod
    def _is_inside(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False
