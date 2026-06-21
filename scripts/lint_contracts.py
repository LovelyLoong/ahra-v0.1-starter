#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ahra.validation import validate_document  # noqa: E402


MAPPINGS = [
    ("examples/agents/repository-maintainer.yaml", "contracts/schemas/agent.schema.json"),
    ("examples/tools/git-apply-patch.yaml", "contracts/schemas/tool.schema.json"),
    ("examples/runtimes/repo-container.yaml", "contracts/schemas/runtime-profile.schema.json"),
    ("examples/workflows/repository-maintenance.yaml", "contracts/schemas/workflow.schema.json"),
    ("examples/records/run.json", "contracts/schemas/run.schema.json"),
    ("examples/records/memory.json", "contracts/schemas/memory-record.schema.json"),
    ("examples/records/context-manifest.json", "contracts/schemas/context-manifest.schema.json"),
    ("examples/records/policy-decision.json", "contracts/schemas/policy-decision.schema.json"),
    ("examples/records/approval.json", "contracts/schemas/approval.schema.json"),
    ("examples/records/event.json", "contracts/schemas/event.schema.json"),
]


def main() -> int:
    failures = 0
    for document, schema in MAPPINGS:
        errors = validate_document(ROOT / document, ROOT / schema)
        if errors:
            failures += 1
            print(f"ERROR {document} against {schema}")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"OK    {document}")

    forbidden = ("openai", "anthropic", "langgraph", "temporalio", "boto3", "kubernetes")
    for path in [ROOT / "src/ahra/domain.py", ROOT / "src/ahra/ports.py"]:
        text = path.read_text(encoding="utf-8")
        for name in forbidden:
            if f"import {name}" in text or f"from {name}" in text:
                failures += 1
                print(f"ERROR {path.relative_to(ROOT)} imports adapter dependency {name}")

    awkp_lint = ROOT / "profiles/awkp/scripts/lint_awkp.py"
    result = subprocess.run([sys.executable, str(awkp_lint)], cwd=ROOT / "profiles/awkp", check=False)
    if result.returncode:
        failures += 1
        print("ERROR embedded AWKP profile lint failed")

    print(f"AHRA lint: {failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
