from __future__ import annotations

import os
import shutil
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import CheckEvidence, CheckSpec
from .runtime import LocalRuntimeProvider

MAX_CAPTURE_CHARS = 24_000


def _truncate(text: str) -> str:
    if len(text) <= MAX_CAPTURE_CHARS:
        return text
    half = MAX_CAPTURE_CHARS // 2
    return f"{text[:half]}\n\n... output truncated ...\n\n{text[-half:]}"


def run_check(workspace: Path, check: CheckSpec, runtime=None) -> CheckEvidence:
    runtime = runtime or LocalRuntimeProvider()
    cwd = (workspace / check.cwd).resolve()
    try:
        cwd.relative_to(workspace.resolve())
    except ValueError as exc:
        raise ValueError(f"check cwd escapes workspace: {check.cwd}") from exc
    if not cwd.exists():
        return CheckEvidence(
            name=check.name,
            argv=check.argv,
            required=check.required,
            exit_code=None,
            duration_seconds=0.0,
            stderr=f"check cwd does not exist: {cwd}",
        )

    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="ahra-check-") as scratch:
        scratch_path = Path(scratch)
        env = os.environ.copy()
        env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
        env.setdefault("PYTHONPYCACHEPREFIX", str(scratch_path / "pycache"))
        env.setdefault("COVERAGE_FILE", str(scratch_path / ".coverage"))
        env.setdefault("XDG_CACHE_HOME", str(scratch_path / "xdg-cache"))
        env.setdefault("RUFF_CACHE_DIR", str(scratch_path / "ruff-cache"))
        env.setdefault("MYPY_CACHE_DIR", str(scratch_path / "mypy-cache"))
        env.setdefault("PIP_CACHE_DIR", str(scratch_path / "pip-cache"))
        env.setdefault("npm_config_cache", str(scratch_path / "npm-cache"))
        argv = _effective_check_argv(workspace, check.argv)
        if any(part == "pytest" or part.endswith("/pytest") for part in argv):
            existing = env.get("PYTEST_ADDOPTS", "").strip()
            env["PYTEST_ADDOPTS"] = f"{existing} -p no:cacheprovider".strip()
        env.update(check.env)
        handle = runtime.provision(
            profile_ref="local-check",
            workspace_ref=str(cwd),
            identity="workflow-module:reference-runner",
        )
        try:
            result = runtime.exec(
                handle,
                list(argv),
                env,
                datetime.now(timezone.utc) + timedelta(seconds=check.timeout_seconds),
            )
            return CheckEvidence(
                name=check.name,
                argv=argv,
                required=check.required,
                exit_code=result.get("exit_code"),
                timed_out=bool(result.get("timed_out")),
                duration_seconds=round(time.monotonic() - started, 3),
                stdout=_truncate(str(result.get("stdout") or "")),
                stderr=_truncate(str(result.get("stderr") or "")),
            )
        finally:
            runtime.destroy(handle)


def run_checks(workspace: Path, checks: tuple[CheckSpec, ...], runtime=None) -> tuple[CheckEvidence, ...]:
    return tuple(run_check(workspace, check, runtime) for check in checks)


def _effective_check_argv(workspace: Path, argv: tuple[str, ...]) -> tuple[str, ...]:
    if not argv:
        return argv
    command = Path(argv[0]).name.lower()
    has_project_env = (workspace / "pyproject.toml").exists()
    if command in {"python", "python.exe"} and has_project_env and shutil.which("uv"):
        return ("uv", "run", "python", "-B", *argv[1:])
    return argv
