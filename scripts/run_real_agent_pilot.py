#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ahra.ports import AgentDriverRegistry  # noqa: E402
from ahra.reference_runner.models import ExecutionPolicy  # noqa: E402
from ahra.real_agent_pilot import PilotMode, RealAgentPilotConfig, RealAgentPilotRunner  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a bounded real-Agent M1 pilot.")
    parser.add_argument("--mode", required=True, choices=[mode.value for mode in PilotMode])
    parser.add_argument("--request", default=str(ROOT / "examples" / "m1" / "goal-run-request.yaml"))
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--experiment-id", default="M1-REAL-AGENT-PILOT")
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--driver-ref", default="codex-python-sdk")
    parser.add_argument("--model-provider", default="codex-sdk")
    parser.add_argument("--model")
    parser.add_argument("--allow-model-cost", action="store_true")
    parser.add_argument("--allow-combined", action="store_true")
    parser.add_argument("--isolated-repetitions", action="store_true")
    parser.add_argument("--repetition-timeout-seconds", type=int, default=300)
    parser.add_argument("--executor-max-attempts", type=int, default=1)
    parser.add_argument("--executor-startup-timeout-seconds", type=int, default=60)
    parser.add_argument("--executor-idle-timeout-seconds", type=int, default=120)
    parser.add_argument("--executor-heartbeat-interval-seconds", type=int, default=15)
    parser.add_argument("--executor-attempt-wall-timeout-seconds", type=int, default=180)
    parser.add_argument("--executor-run-deadline-seconds", type=int, default=240)
    parser.add_argument("--single-repetition-index", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()

    config = RealAgentPilotConfig(
        experiment_id=args.experiment_id,
        mode=PilotMode(args.mode),
        request_template=Path(args.request),
        output_dir=Path(args.output_dir),
        repetitions=args.repetitions,
        planner_driver_ref=args.driver_ref,
        model_provider=args.model_provider,
        model_revision=args.model or "unspecified",
        allow_combined=args.allow_combined,
        executor_policy=ExecutionPolicy(
            max_attempts=args.executor_max_attempts,
            startup_timeout_seconds=args.executor_startup_timeout_seconds,
            idle_timeout_seconds=args.executor_idle_timeout_seconds,
            heartbeat_interval_seconds=args.executor_heartbeat_interval_seconds,
            attempt_wall_timeout_seconds=args.executor_attempt_wall_timeout_seconds,
            run_deadline_seconds=args.executor_run_deadline_seconds,
        ),
    )

    if args.single_repetition_index is not None:
        runner = _runner(args)
        run = runner.run_one(config, args.single_repetition_index)
        print(json.dumps({"ok": True, "run": run}, ensure_ascii=False, indent=2))
        return 0

    if args.isolated_repetitions:
        scorecard = _run_isolated_repetitions(args, config)
    else:
        scorecard = _runner(args).run(config)
    print(json.dumps({"ok": True, "scorecard": str(config.output_dir / "scorecard.json"), "result": scorecard}, ensure_ascii=False, indent=2))
    return 0


def _runner(args: argparse.Namespace) -> RealAgentPilotRunner:
    registry = AgentDriverRegistry()
    executor_driver = None
    if args.allow_model_cost:
        from ahra.adapters.codex_sdk import CodexDriverConfig, CodexSDKDriver

        driver = CodexSDKDriver(
            CodexDriverConfig(
                driver_ref=args.driver_ref,
                model=args.model,
            )
        )
        registry.register(args.driver_ref, driver)
        executor_driver = driver
    return RealAgentPilotRunner(
        planner_registry=registry,
        executor_driver=executor_driver,
    )


def _run_isolated_repetitions(args: argparse.Namespace, config: RealAgentPilotConfig) -> dict[str, object]:
    runner = RealAgentPilotRunner()
    runs = []
    for index in range(1, config.repetitions + 1):
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                _single_repetition_argv(args, index),
                cwd=str(ROOT),
                text=True,
                capture_output=True,
                timeout=args.repetition_timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            runs.append(
                runner.timeout_run(
                    config,
                    index,
                    elapsed_seconds=round(time.perf_counter() - started, 6),
                    message=f"single repetition exceeded process timeout ({args.repetition_timeout_seconds}s)",
                    details={
                        "stdoutTail": _tail(exc.stdout),
                        "stderrTail": _tail(exc.stderr),
                    },
                )
            )
            continue

        run_path = config.output_dir / f"run-{index:02d}" / "run-result.json"
        if completed.returncode == 0 and run_path.exists():
            runs.append(json.loads(run_path.read_text(encoding="utf-8")))
            continue

        runs.append(
            runner.process_failed_run(
                config,
                index,
                elapsed_seconds=round(time.perf_counter() - started, 6),
                message=f"single repetition process exited with code {completed.returncode}",
                details={
                    "stdoutTail": _tail(completed.stdout),
                    "stderrTail": _tail(completed.stderr),
                    "runResultPath": str(run_path),
                    "runResultExists": run_path.exists(),
                },
            )
        )
    return runner.write_scorecard(config, runs)


def _single_repetition_argv(args: argparse.Namespace, index: int) -> list[str]:
    argv = [
        sys.executable,
        "-B",
        str(Path(__file__).resolve()),
        "--mode",
        args.mode,
        "--request",
        str(args.request),
        "--output-dir",
        str(args.output_dir),
        "--experiment-id",
        args.experiment_id,
        "--repetitions",
        str(args.repetitions),
        "--driver-ref",
        args.driver_ref,
        "--model-provider",
        args.model_provider,
        "--repetition-timeout-seconds",
        str(args.repetition_timeout_seconds),
        "--executor-max-attempts",
        str(args.executor_max_attempts),
        "--executor-startup-timeout-seconds",
        str(args.executor_startup_timeout_seconds),
        "--executor-idle-timeout-seconds",
        str(args.executor_idle_timeout_seconds),
        "--executor-heartbeat-interval-seconds",
        str(args.executor_heartbeat_interval_seconds),
        "--executor-attempt-wall-timeout-seconds",
        str(args.executor_attempt_wall_timeout_seconds),
        "--executor-run-deadline-seconds",
        str(args.executor_run_deadline_seconds),
        "--single-repetition-index",
        str(index),
    ]
    if args.model:
        argv.extend(["--model", args.model])
    if args.allow_model_cost:
        argv.append("--allow-model-cost")
    if args.allow_combined:
        argv.append("--allow-combined")
    return argv


def _tail(value: object, *, limit: int = 4000) -> str:
    if value is None:
        return ""
    text = value.decode("utf-8", errors="replace") if isinstance(value, bytes) else str(value)
    return text[-limit:]


if __name__ == "__main__":
    raise SystemExit(main())
