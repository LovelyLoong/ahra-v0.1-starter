#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def _env() -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(SRC) if not existing else str(SRC) + os.pathsep + existing
    return env


def _run(argv: list[str]) -> int:
    print("+ " + " ".join(argv), flush=True)
    return subprocess.run(argv, cwd=ROOT, env=_env(), check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Run AHRA starter checks.")
    parser.add_argument("--lint", action="store_true", help="Run contract/AWKP lint only.")
    parser.add_argument("--test", action="store_true", help="Run unit tests only.")
    args = parser.parse_args()

    run_lint = args.lint or not args.test
    run_tests = args.test or not args.lint
    failures = 0

    if run_lint:
        failures += _run([sys.executable, "scripts/lint_contracts.py"]) != 0
    if run_tests:
        failures += _run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]) != 0

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
