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
INTERNAL_ARTIFACT_EXISTS_COMMAND = "ahra.internal.artifact_exists.v1"


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
    if check.argv[0] == INTERNAL_ARTIFACT_EXISTS_COMMAND:
        return _run_internal_artifact_exists(workspace, cwd, check)

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


def effective_check_argv(workspace: Path, argv: tuple[str, ...]) -> tuple[str, ...]:
    return _effective_check_argv(workspace, argv)


def _effective_check_argv(workspace: Path, argv: tuple[str, ...]) -> tuple[str, ...]:
    if not argv:
        return argv
    command = Path(argv[0]).name.lower()
    has_project_env = (workspace / "pyproject.toml").exists()
    if command in {"python", "python.exe"} and has_project_env and shutil.which("uv"):
        return ("uv", "run", "python", "-B", *argv[1:])
    return argv


def _run_internal_artifact_exists(workspace: Path, cwd: Path, check: CheckSpec) -> CheckEvidence:
    started = time.monotonic()
    if len(check.argv) != 2:
        return CheckEvidence(
            name=check.name,
            argv=check.argv,
            required=check.required,
            exit_code=2,
            duration_seconds=round(time.monotonic() - started, 3),
            stderr="internal artifact check requires exactly one relative path argument",
        )
    target = (cwd / check.argv[1]).resolve()
    try:
        target.relative_to(workspace.resolve())
    except ValueError:
        return CheckEvidence(
            name=check.name,
            argv=check.argv,
            required=check.required,
            exit_code=2,
            duration_seconds=round(time.monotonic() - started, 3),
            stderr=f"internal artifact check path escapes workspace: {check.argv[1]}",
        )
    if not target.is_file():
        return CheckEvidence(
            name=check.name,
            argv=check.argv,
            required=check.required,
            exit_code=1,
            duration_seconds=round(time.monotonic() - started, 3),
            stderr=f"missing artifact file: {target}",
        )
    if target.stat().st_size <= 0:
        return CheckEvidence(
            name=check.name,
            argv=check.argv,
            required=check.required,
            exit_code=1,
            duration_seconds=round(time.monotonic() - started, 3),
            stderr=f"empty artifact file: {target}",
        )
    return CheckEvidence(
        name=check.name,
        argv=check.argv,
        required=check.required,
        exit_code=0,
        duration_seconds=round(time.monotonic() - started, 3),
    )
