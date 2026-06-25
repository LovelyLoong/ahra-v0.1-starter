from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from ahra.acceptance_contracts import (
    ClaimGraph,
    GateDefinition,
    GatePlan,
    GoalContract,
    validate_acceptance_contracts,
)
from ahra.validation import load_document


ROOT = Path(__file__).resolve().parents[1]
RECORDS = ROOT / "examples" / "records"


class AcceptanceContractTests(unittest.TestCase):
    def test_valid_examples_pass_contract_validation(self) -> None:
        self.assertEqual(self._violations("claim-graph.json"), [])

    def test_uncovered_criterion_fails_contract_validation(self) -> None:
        messages = self._violation_messages("invalid/claim-graph-uncovered.json")
        self.assertIn("uncovered-criterion", messages)

    def test_cyclic_claim_dependency_fails_contract_validation(self) -> None:
        messages = self._violation_messages("invalid/claim-graph-cyclic.json")
        self.assertIn("cyclic-claim-dependency", messages)

    def test_duplicate_claim_id_fails_contract_validation(self) -> None:
        messages = self._violation_messages("invalid/claim-graph-duplicate.json")
        self.assertIn("duplicate-claim-id", messages)

    def test_security_extension_downgrade_fails_contract_validation(self) -> None:
        messages = self._violation_messages("invalid/claim-graph-forbidden-downgrade.json")
        self.assertIn("forbidden-security-governance-downgrade", messages)

    def test_required_claim_needs_gate_or_approval(self) -> None:
        graph_data = self._load("claim-graph.json")
        graph_data["spec"]["claims"][0]["gateRefs"] = []
        graph_data["spec"]["claims"][0]["approvalRequired"] = False

        messages = self._violation_messages_from_graph(graph_data)

        self.assertIn("required-claim-without-gate", messages)

    def test_missing_claim_dependency_fails_contract_validation(self) -> None:
        graph_data = self._load("claim-graph.json")
        graph_data["spec"]["claims"][0]["dependsOn"] = ["CLAIM-does-not-exist"]

        messages = self._violation_messages_from_graph(graph_data)

        self.assertIn("missing-claim-dependency", messages)

    def test_unregistered_gate_fails_contract_validation(self) -> None:
        graph_data = self._load("claim-graph.json")
        graph_data["spec"]["claims"][0]["gateRefs"] = ["GATE-does-not-exist"]

        messages = self._violation_messages_from_graph(graph_data)

        self.assertIn("unregistered-gate", messages)

    def test_schema_rejects_unknown_major_version(self) -> None:
        document = self._load("goal-contract.json")
        document["apiVersion"] = "ahra.dev/v2alpha1"

        self.assertNotEqual(self._schema_errors(document, "goal-contract.schema.json"), [])

    def test_schema_rejects_malformed_ids(self) -> None:
        document = self._load("goal-contract.json")
        document["metadata"]["goalId"] = "goal-doc-staleness"

        self.assertNotEqual(self._schema_errors(document, "goal-contract.schema.json"), [])

    def test_schema_allows_compatible_extension_fields(self) -> None:
        document = self._load("goal-contract.json")
        document["spec"]["criteria"][0]["x-owner-note"] = {"note": "compatible metadata"}

        self.assertEqual(self._schema_errors(document, "goal-contract.schema.json"), [])

    def test_domain_validation_layer_does_not_import_provider_sdks(self) -> None:
        forbidden = ("openai", "anthropic", "langgraph", "temporalio", "boto3", "kubernetes")
        for rel in [
            "src/ahra/acceptance_contracts.py",
            "src/ahra/capabilities.py",
            "src/ahra/domain.py",
            "src/ahra/node_executor.py",
            "src/ahra/plan_ir.py",
            "src/ahra/validation.py",
        ]:
            text = (ROOT / rel).read_text(encoding="utf-8")
            for name in forbidden:
                with self.subTest(path=rel, dependency=name):
                    self.assertNotIn(f"import {name}", text)
                    self.assertNotIn(f"from {name}", text)

    def _violations(self, graph_name: str) -> list[str]:
        graph_data = self._load(graph_name)
        return [violation.code for violation in self._validate_graph_data(graph_data)]

    def _violation_messages(self, graph_name: str) -> str:
        return "\n".join(self._violations(graph_name))

    def _violation_messages_from_graph(self, graph_data: dict) -> str:
        return "\n".join(violation.code for violation in self._validate_graph_data(graph_data))

    def _validate_graph_data(self, graph_data: dict) -> list:
        goal = GoalContract.from_mapping(self._load("goal-contract.json"))
        graph = ClaimGraph.from_mapping(graph_data)
        gate = GateDefinition.from_mapping(self._load("gate-definition.json"))
        plan = GatePlan.from_mapping(self._load("gate-plan.json"))
        return validate_acceptance_contracts(goal, graph, (gate,), plan)

    def _schema_errors(self, document: dict, schema_name: str) -> list[str]:
        schema = json.loads((ROOT / "contracts" / "schemas" / schema_name).read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        return [error.message for error in sorted(validator.iter_errors(document), key=lambda error: list(error.path))]

    def _load(self, name: str) -> dict:
        return copy.deepcopy(load_document(RECORDS / name))


if __name__ == "__main__":
    unittest.main()
