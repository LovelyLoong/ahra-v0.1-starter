from __future__ import annotations

import asyncio
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from ahra.ports import AgentDriver, AgentRole, AgentRunRequest, AgentRunResult

from .codex_sdk import _load_json_object, _parse_expected_output, _prompt_for_request


class CodexCLIClient(Protocol):
    async def run(
        self,
        *,
        request: AgentRunRequest,
        prompt: str,
        sandbox: str,
        model: str | None,
        cwd: str | None,
    ) -> str: ...


@dataclass(frozen=True, slots=True)
class CodexCLIConfig:
    driver_ref: str = "codex-cli"
    model: str | None = None
    executor_sandbox: str = "workspace_write"
    reviewer_sandbox: str = "read_only"
    planner_sandbox: str = "read_only"
    codex_bin: str = "codex"
    timeout_seconds: int = 1200
    ephemeral: bool = True
    extra_args: tuple[str, ...] = field(default_factory=tuple)


class SubprocessCodexCLIClient:
    """Run the installed Codex CLI through `codex exec`."""

    def __init__(self, config: CodexCLIConfig | None = None) -> None:
        self.config = config or CodexCLIConfig()

    async def run(
        self,
        *,
        request: AgentRunRequest,
        prompt: str,
        sandbox: str,
        model: str | None,
        cwd: str | None,
    ) -> str:
        return await asyncio.to_thread(
            self._run_sync,
            prompt=prompt,
            sandbox=sandbox,
            model=model,
            cwd=cwd,
        )

    def _run_sync(
        self,
        *,
        prompt: str,
        sandbox: str,
        model: str | None,
        cwd: str | None,
    ) -> str:
        with tempfile.TemporaryDirectory(prefix="ahra-codex-cli-") as temp:
            output_path = Path(temp) / "last-message.txt"
            codex_bin = shutil.which(self.config.codex_bin) or self.config.codex_bin
            argv = [
                codex_bin,
                "exec",
                "--sandbox",
                _cli_sandbox(sandbox),
                "--color",
                "never",
                "--output-last-message",
                str(output_path),
            ]
            if self.config.ephemeral:
                argv.append("--ephemeral")
            if model:
                argv.extend(["--model", model])
            if cwd:
                argv.extend(["--cd", cwd])
            argv.extend(self.config.extra_args)
            argv.append("-")

            try:
                completed = subprocess.run(
                    argv,
                    input=prompt,
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=self.config.timeout_seconds,
                    encoding="utf-8",
                    errors="replace",
                )
            except FileNotFoundError as exc:
                raise RuntimeError(
                    f"CodexCLIDriver could not find Codex CLI binary: {self.config.codex_bin}"
                ) from exc
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(
                    f"CodexCLIDriver timed out after {self.config.timeout_seconds} seconds"
                ) from exc

            if completed.returncode != 0:
                stderr = completed.stderr.strip()
                stdout = completed.stdout.strip()
                detail = stderr or stdout or f"exit code {completed.returncode}"
                raise RuntimeError(f"Codex CLI execution failed: {detail}")
            if not output_path.exists():
                raise RuntimeError("Codex CLI did not write an output-last-message file")
            return output_path.read_text(encoding="utf-8")


class CodexCLIDriver(AgentDriver):
    """AgentDriver adapter for the locally installed Codex CLI."""

    def __init__(
        self,
        config: CodexCLIConfig | None = None,
        *,
        client: CodexCLIClient | None = None,
    ) -> None:
        self.config = config or CodexCLIConfig()
        self.client = client or SubprocessCodexCLIClient(self.config)

    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        sandbox = self._sandbox_for_role(request.role)
        raw = await self.client.run(
            request=request,
            prompt=_prompt_for_request(request),
            sandbox=sandbox,
            model=self.config.model,
            cwd=request.workspace_ref,
        )
        data = _load_json_object(raw)
        output = _parse_expected_output(request.expected_output, data)
        return AgentRunResult(output=output, raw_output=raw)

    def _sandbox_for_role(self, role: AgentRole) -> str:
        if role == AgentRole.EXECUTOR:
            return self.config.executor_sandbox
        if role in (AgentRole.TASK_REVIEWER, AgentRole.GOAL_REVIEWER):
            return self.config.reviewer_sandbox
        if role == AgentRole.PLANNER:
            return self.config.planner_sandbox
        raise ValueError(f"unsupported Codex CLI driver role: {role}")


def _cli_sandbox(name: str) -> str:
    normalized = name.replace("_", "-")
    if normalized == "danger-full-access":
        return normalized
    if normalized in {"read-only", "workspace-write"}:
        return normalized
    raise ValueError(f"unsupported Codex CLI sandbox: {name}")
