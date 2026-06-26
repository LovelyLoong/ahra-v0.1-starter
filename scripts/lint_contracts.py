#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
import tomllib
import json
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
    ("examples/m1/goal-run-request.yaml", "contracts/schemas/goal-execution-request.schema.json"),
    ("examples/records/claim-graph.json", "contracts/schemas/claim-graph.schema.json"),
    ("examples/records/gate-definition.json", "contracts/schemas/gate-definition.schema.json"),
    ("examples/records/gate-plan.json", "contracts/schemas/gate-plan.schema.json"),
    ("examples/records/evidence-v2.json", "contracts/schemas/evidence-v2.schema.json"),
    ("examples/records/gate-run-v2.json", "contracts/schemas/gate-run-v2.schema.json"),
    ("examples/records/evidence-status-event.json", "contracts/schemas/evidence-status-event.schema.json"),
    ("examples/records/verification-trigger.json", "contracts/schemas/verification-trigger.schema.json"),
    ("examples/records/verification-selection.json", "contracts/schemas/verification-selection.schema.json"),
    ("examples/records/verification-result.json", "contracts/schemas/verification-result.schema.json"),
    ("examples/records/gate-execution-request.json", "contracts/schemas/gate-execution-request.schema.json"),
    ("examples/records/gate-execution-result.json", "contracts/schemas/gate-execution-result.schema.json"),
    ("examples/records/verification-execution-report.json", "contracts/schemas/verification-execution-report.schema.json"),
    ("examples/records/defect-record.json", "contracts/schemas/defect-record.schema.json"),
    ("examples/records/node-run.json", "contracts/schemas/node-run.schema.json"),
    ("examples/records/plan-draft.json", "contracts/schemas/plan-draft.schema.json"),
    ("examples/records/plan-ir.json", "contracts/schemas/plan-ir.schema.json"),
    ("examples/records/plan-patch.json", "contracts/schemas/plan-patch.schema.json"),
    ("examples/records/plan-validation-report.json", "contracts/schemas/plan-validation-report.schema.json"),
]

INVENTORY_PATH = ROOT / "docs/architecture/component-inventory.json"
DEFAULT_DOC_PATHS = [
    ROOT / "README.md",
    ROOT / "AGENTS.md",
    ROOT / "docs/architecture/framework-entrypoints.md",
    ROOT / "skills/ahra-dynamic-kernel/SKILL.md",
]
FORBIDDEN_DEFAULT_DOC_SNIPPETS = [
    "uv run ahra workflow",
    "ahra workflow start",
    "ahra workflow resume",
    "standard-harness` is the default",
    "loop-engineering` is the default",
    "standard workflows the recommended path",
    "built-in modules are the recommended path",
    "python -m ahra.demo",
    "make demo",
]
FORBIDDEN_DEFAULT_SCRIPTS = {
    "ahra-mcp": "MCP is legacy and must not be installed as a default console script",
    "ahra-demo": "demo.py is experimental and must not be installed as a default console script",
}
VALID_COMPONENT_CLASSES = {"core", "adapter", "experimental", "legacy", "removal_candidate", "archived"}
CORE_REQUIRED_FIELDS = {
    "owner",
    "review_after",
    "paths",
    "serves",
    "entrypoints",
    "consumers",
    "tests",
    "security_class",
    "side_effects",
    "artifact_evidence",
}


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
        ROOT / "src/ahra/dynamic_fixture.py",
        ROOT / "src/ahra/evidence_v2.py",
        ROOT / "src/ahra/goal_operations.py",
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

    failures += _check_default_exposure()
    failures += _check_component_inventory()

    awkp_lint = ROOT / "scripts/lint_awkp.py"
    result = subprocess.run([sys.executable, str(awkp_lint)], cwd=ROOT, check=False)
    if result.returncode:
        failures += 1
        print("ERROR embedded AWKP profile lint failed")

    print(f"AHRA lint: {failures} failure(s)")
    return 1 if failures else 0


def _check_default_exposure() -> int:
    failures = 0
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = pyproject.get("project", {}).get("scripts", {})
    for name, reason in FORBIDDEN_DEFAULT_SCRIPTS.items():
        if name in scripts:
            failures += 1
            print(f"ERROR pyproject.toml exposes {name}: {reason}")
    for name, target in sorted(scripts.items()):
        if "mcp_server" in str(target) or "demo" in str(target):
            failures += 1
            print(f"ERROR pyproject.toml script {name} targets legacy/default-excluded module {target}")

    from ahra import cli  # noqa: WPS433 - local lint verifies CLI default exposure.

    help_text = cli._build_parser().format_help()
    for token in ["workflow", "mcp", "demo", "fake-reference", "standard-harness", "loop-engineering"]:
        if token in help_text:
            failures += 1
            print(f"ERROR default CLI help exposes default-excluded token: {token}")

    for path in DEFAULT_DOC_PATHS:
        text = path.read_text(encoding="utf-8")
        lowered = text.lower()
        for snippet in FORBIDDEN_DEFAULT_DOC_SNIPPETS:
            if snippet.lower() in lowered:
                failures += 1
                print(f"ERROR {path.relative_to(ROOT)} contains default-route legacy snippet: {snippet}")
    return failures


def _check_component_inventory() -> int:
    failures = 0
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    if inventory.get("schema_version") != "ahra/component-inventory/0.1":
        print("ERROR docs/architecture/component-inventory.json has invalid schema_version")
        failures += 1
    components = inventory.get("components")
    if not isinstance(components, list) or not components:
        print("ERROR docs/architecture/component-inventory.json has no components")
        return failures + 1

    seen: set[str] = set()
    for component in components:
        component_id = str(component.get("id") or "")
        if not component_id:
            failures += 1
            print("ERROR component inventory entry missing id")
            continue
        if component_id in seen:
            failures += 1
            print(f"ERROR duplicate component inventory id: {component_id}")
        seen.add(component_id)

        lifecycle_class = str(component.get("lifecycle_class") or "")
        if lifecycle_class not in VALID_COMPONENT_CLASSES:
            failures += 1
            print(f"ERROR {component_id} has invalid lifecycle_class: {lifecycle_class}")
        if "candidate" in lifecycle_class:
            failures += 1
            print(f"ERROR {component_id} remains a candidate lifecycle class")

        if component.get("default_visible") and lifecycle_class not in {"core", "adapter"}:
            failures += 1
            print(f"ERROR {component_id} is default-visible but not core/adapter")

        if lifecycle_class == "core":
            missing = sorted(field for field in CORE_REQUIRED_FIELDS if not component.get(field))
            if missing:
                failures += 1
                print(f"ERROR {component_id} core entry missing required fields: {', '.join(missing)}")
        if lifecycle_class in {"legacy", "removal_candidate"}:
            for field in ("compatibility_scope", "removal_trigger"):
                if not component.get(field):
                    failures += 1
                    print(f"ERROR {component_id} {lifecycle_class} entry missing {field}")
        if lifecycle_class == "archived" and not component.get("trace_location"):
            failures += 1
            print(f"ERROR {component_id} archived entry missing trace_location")

    return failures


if __name__ == "__main__":
    raise SystemExit(main())
