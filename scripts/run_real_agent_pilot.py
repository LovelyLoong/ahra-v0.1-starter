#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ahra.ports import AgentDriverRegistry  # noqa: E402
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
    args = parser.parse_args()

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
    )
    scorecard = RealAgentPilotRunner(
        planner_registry=registry,
        executor_driver=executor_driver,
    ).run(config)
    print(json.dumps({"ok": True, "scorecard": str(config.output_dir / "scorecard.json"), "result": scorecard}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
