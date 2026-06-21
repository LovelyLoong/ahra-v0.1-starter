from __future__ import annotations

import unittest
from pathlib import Path

from ahra.validation import validate_document


ROOT = Path(__file__).resolve().parents[1]


class SchemaTests(unittest.TestCase):
    CASES = [
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

    def test_examples_validate(self) -> None:
        for document, schema in self.CASES:
            with self.subTest(document=document):
                self.assertEqual(validate_document(ROOT / document, ROOT / schema), [])


if __name__ == "__main__":
    unittest.main()
