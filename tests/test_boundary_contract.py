from __future__ import annotations

import unittest
from pathlib import Path

from ahra.boundary_contract import BoundaryContract, BoundaryContractError
from ahra.validation import load_document, validate_document


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "records" / "boundary-contract.json"
SCHEMA = ROOT / "contracts" / "schemas" / "boundary-contract.schema.json"


class BoundaryContractTests(unittest.TestCase):
    def test_example_validates_against_schema(self) -> None:
        self.assertEqual(validate_document(EXAMPLE, SCHEMA), [])

    def test_freeze_accepts_typed_boundary_contract(self) -> None:
        contract = BoundaryContract.freeze(load_document(EXAMPLE))

        self.assertEqual(contract.name, "alignment-session-boundary")
        self.assertTrue(contract.digest().startswith("sha256:"))

    def test_freeze_rejects_open_questions(self) -> None:
        data = _contract(
            [
                _entry("BCE-MUST-OUTPUT", "must"),
                _entry("BCE-QUESTION-SCOPE", "open_question"),
            ]
        )

        with self.assertRaises(BoundaryContractError) as raised:
            BoundaryContract.freeze(data)

        self.assertEqual(raised.exception.code, "open_question_not_freezable")

    def test_freeze_rejects_duplicate_entry_ids(self) -> None:
        data = _contract(
            [
                _entry("BCE-MUST-OUTPUT", "must", "Write the artifact."),
                _entry("BCE-MUST-OUTPUT", "completion_signal", "Artifact exists."),
            ]
        )

        with self.assertRaises(BoundaryContractError) as raised:
            BoundaryContract.freeze(data)

        self.assertEqual(raised.exception.code, "duplicate_entry_id")
        self.assertEqual(raised.exception.refs, ("BCE-MUST-OUTPUT",))

    def test_freeze_rejects_unknown_kinds(self) -> None:
        data = _contract([_entry("BCE-MUST-OUTPUT", "maybe")])

        with self.assertRaises(BoundaryContractError) as raised:
            BoundaryContract.freeze(data)

        self.assertEqual(raised.exception.code, "unknown_entry_kind")


def _contract(entries: list[dict[str, object]]) -> dict[str, object]:
    return {
        "apiVersion": "ahra.dev/v1alpha1",
        "kind": "BoundaryContract",
        "metadata": {
            "name": "test-boundary",
            "version": 1,
        },
        "spec": {
            "entries": entries,
        },
    }


def _entry(entry_id: str, kind: str, statement: str = "A boundary statement.") -> dict[str, object]:
    return {
        "id": entry_id,
        "kind": kind,
        "statement": statement,
    }


if __name__ == "__main__":
    unittest.main()
