from __future__ import annotations

import unittest
from pathlib import Path

from ahra.validation import validate_document


ROOT = Path(__file__).resolve().parents[1]


class SchemaTests(unittest.TestCase):
    CASES = [
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

    def test_examples_validate(self) -> None:
        for document, schema in self.CASES:
            with self.subTest(document=document):
                self.assertEqual(validate_document(ROOT / document, ROOT / schema), [])


if __name__ == "__main__":
    unittest.main()
