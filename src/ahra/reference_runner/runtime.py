from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class LocalRuntimeProvider:
    """Reference RuntimeProvider for trusted local development."""

    def provision(self, profile_ref: str, workspace_ref: str, identity: str) -> str:
        return str(Path(workspace_ref).resolve())

    def exec(
        self,
        handle: str,
        command: list[str],
        env: dict[str, str],
        deadline: datetime,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        timeout = max(1.0, (deadline - now).total_seconds())
        try:
            result = subprocess.run(
                command,
                cwd=handle,
                env=env,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
            return {
                "exit_code": result.returncode,
                "timed_out": False,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            return {
                "exit_code": None,
                "timed_out": True,
                "stdout": stdout,
                "stderr": stderr,
            }
        except FileNotFoundError as exc:
            return {
                "exit_code": None,
                "timed_out": False,
                "stdout": "",
                "stderr": str(exc),
            }

    def snapshot(self, handle: str) -> str:
        return f"local-snapshot://{handle}"

    def cancel(self, handle: str, execution_id: str) -> None:
        return None

    def destroy(self, handle: str) -> None:
        return None
