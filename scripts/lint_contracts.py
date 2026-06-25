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
    ("examples/runtimes/local-worktree.yaml", "contracts/schemas/runtime-profile.schema.json"),
    ("examples/workflows/repository-maintenance.yaml", "contracts/schemas/workflow.schema.json"),
    ("examples/workflow_modules/standard-harness.yaml", "contracts/schemas/workflow-module.schema.json"),
    ("examples/workflow_modules/loop-engineering.yaml", "contracts/schemas/workflow-module.schema.json"),
    ("examples/workflow_runs/fixtures/standard-task.yaml", "contracts/schemas/workflow-run-request.schema.json"),
    ("examples/workflow_runs/fixtures/loop-goal.yaml", "contracts/schemas/workflow-run-request.schema.json"),
    ("examples/workflow_runs/fixtures/loop-resume.yaml", "contracts/schemas/workflow-resume-request.schema.json"),
    ("examples/workflow_runs/runnable/standard-task-codex.yaml", "contracts/schemas/workflow-run-request.schema.json"),
    ("examples/records/run.json", "contracts/schemas/run.schema.json"),
    ("examples/records/memory.json", "contracts/schemas/memory-record.schema.json"),
    ("examples/records/context-manifest.json", "contracts/schemas/context-manifest.schema.json"),
    ("examples/records/policy-decision.json", "contracts/schemas/policy-decision.schema.json"),
    ("examples/records/capability-request.json", "contracts/schemas/capability-request.schema.json"),
    ("examples/records/capability-grant.json", "contracts/schemas/capability-grant.schema.json"),
    ("examples/records/capability-audit-record.json", "contracts/schemas/capability-audit-record.schema.json"),
    ("examples/records/approval.json", "contracts/schemas/approval.schema.json"),
    ("examples/records/event.json", "contracts/schemas/event.schema.json"),
    ("examples/records/goal-contract.json", "contracts/schemas/goal-contract.schema.json"),
    ("examples/records/claim-graph.json", "contracts/schemas/claim-graph.schema.json"),
    ("examples/records/gate-definition.json", "contracts/schemas/gate-definition.schema.json"),
    ("examples/records/gate-plan.json", "contracts/schemas/gate-plan.schema.json"),
    ("examples/records/evidence-v2.json", "contracts/schemas/evidence-v2.schema.json"),
    ("examples/records/gate-run-v2.json", "contracts/schemas/gate-run-v2.schema.json"),
    ("examples/records/evidence-status-event.json", "contracts/schemas/evidence-status-event.schema.json"),
    ("examples/records/verification-trigger.json", "contracts/schemas/verification-trigger.schema.json"),
    ("examples/records/verification-selection.json", "contracts/schemas/verification-selection.schema.json"),
    ("examples/records/verification-result.json", "contracts/schemas/verification-result.schema.json"),
    ("examples/records/defect-record.json", "contracts/schemas/defect-record.schema.json"),
    ("examples/records/node-run.json", "contracts/schemas/node-run.schema.json"),
    ("examples/records/plan-draft.json", "contracts/schemas/plan-draft.schema.json"),
    ("examples/records/plan-ir.json", "contracts/schemas/plan-ir.schema.json"),
    ("examples/records/plan-patch.json", "contracts/schemas/plan-patch.schema.json"),
    ("examples/records/plan-validation-report.json", "contracts/schemas/plan-validation-report.schema.json"),
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
    for path in [
        ROOT / "src/ahra/acceptance_contracts.py",
        ROOT / "src/ahra/capabilities.py",
        ROOT / "src/ahra/domain.py",
        ROOT / "src/ahra/evidence_v2.py",
        ROOT / "src/ahra/node_executor.py",
        ROOT / "src/ahra/plan_execution.py",
        ROOT / "src/ahra/plan_ir.py",
        ROOT / "src/ahra/planner_contracts.py",
        ROOT / "src/ahra/planning.py",
        ROOT / "src/ahra/ports.py",
        ROOT / "src/ahra/validation.py",
        ROOT / "src/ahra/verification.py",
        ROOT / "src/ahra/workflow_modules.py",
        *sorted((ROOT / "src/ahra/reference_runner").glob("*.py")),
    ]:
        text = path.read_text(encoding="utf-8")
        for name in forbidden:
            if f"import {name}" in text or f"from {name}" in text:
                failures += 1
                print(f"ERROR {path.relative_to(ROOT)} imports adapter dependency {name}")

    awkp_lint = ROOT / "scripts/lint_awkp.py"
    result = subprocess.run([sys.executable, str(awkp_lint)], cwd=ROOT, check=False)
    if result.returncode:
        failures += 1
        print("ERROR embedded AWKP profile lint failed")

    print(f"AHRA lint: {failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
