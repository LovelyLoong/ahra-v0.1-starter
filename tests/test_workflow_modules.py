from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

import yaml

from ahra.validation import validate_document
from ahra.workflow_modules import (
    WorkflowModuleContract,
    WorkflowModuleError,
    load_workflow_module_registry,
)


ROOT = Path(__file__).resolve().parents[1]


class WorkflowModuleContractTests(unittest.TestCase):
    def test_examples_validate_against_schema(self) -> None:
        schema = ROOT / "contracts/schemas/workflow-module.schema.json"
        for document in [
            ROOT / "examples/workflow_modules/standard-harness.yaml",
            ROOT / "examples/workflow_modules/loop-engineering.yaml",
        ]:
            with self.subTest(document=document.name):
                self.assertEqual(validate_document(document, schema), [])

    def test_registry_loads_modules_and_dependencies(self) -> None:
        registry = load_workflow_module_registry(
            [
                ROOT / "examples/workflow_modules/loop-engineering.yaml",
                ROOT / "examples/workflow_modules/standard-harness.yaml",
            ]
        )
        modules = {module.module_id: module for module in registry.list()}
        self.assertEqual(set(modules), {"standard-harness", "loop-engineering"})
        self.assertEqual(modules["loop-engineering"].extends, "standard-harness")
        self.assertIn("AgentDriver", modules["standard-harness"].required_ports)
        self.assertIn("AgentDriver", modules["loop-engineering"].required_ports)
        self.assertIn("ArtifactStore", modules["standard-harness"].required_ports)
        self.assertIn("ApprovalService", modules["loop-engineering"].required_ports)
        self.assertNotIn("ProjectAdapter", modules["standard-harness"].required_ports)
        self.assertNotIn("ProjectAdapter", modules["loop-engineering"].required_ports)
        self.assertNotIn("ModelGateway", modules["standard-harness"].required_ports)
        self.assertNotIn("ModelGateway", modules["loop-engineering"].required_ports)

    def test_schema_rejects_unknown_port_and_invalid_run_status(self) -> None:
        schema = ROOT / "contracts/schemas/workflow-module.schema.json"
        source = yaml.safe_load(
            (ROOT / "examples/workflow_modules/standard-harness.yaml").read_text(encoding="utf-8")
        )
        cases = [
            ("unknown-port", ("spec", "requiredPorts", 0), "DefinitelyMissingPort"),
            ("invalid-run-status", ("spec", "stateMapping", "run", "accepted"), "not_a_run_status"),
        ]
        with tempfile.TemporaryDirectory() as temp:
            for name, path, value in cases:
                document = copy.deepcopy(source)
                target = document
                for segment in path[:-1]:
                    target = target[segment]
                target[path[-1]] = value
                probe = Path(temp) / f"{name}.yaml"
                probe.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
                with self.subTest(name=name):
                    self.assertNotEqual(validate_document(probe, schema), [])

    def test_registry_rejects_missing_required_boundary_ports(self) -> None:
        document = yaml.safe_load(
            (ROOT / "examples/workflow_modules/standard-harness.yaml").read_text(encoding="utf-8")
        )
        document["spec"]["requiredPorts"].remove("EvidenceStore")
        with self.assertRaisesRegex(WorkflowModuleError, "EvidenceStore"):
            WorkflowModuleContract.from_document(document)

    def test_registry_rejects_missing_agent_driver_port(self) -> None:
        document = yaml.safe_load(
            (ROOT / "examples/workflow_modules/standard-harness.yaml").read_text(encoding="utf-8")
        )
        document["spec"]["requiredPorts"].remove("AgentDriver")
        with self.assertRaisesRegex(WorkflowModuleError, "AgentDriver"):
            WorkflowModuleContract.from_document(document)


if __name__ == "__main__":
    unittest.main()
