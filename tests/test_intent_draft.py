from __future__ import annotations

import copy
import unittest
from pathlib import Path

from ahra.intent_draft import IntentDraft
from ahra.validation import load_document, validate_document


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "intents" / "phase1-example-intent.yaml"
SCHEMA = ROOT / "contracts" / "schemas" / "intent-draft.schema.json"


class IntentDraftTests(unittest.TestCase):
    def test_example_validates_and_round_trips_without_loss(self) -> None:
        self.assertEqual(validate_document(EXAMPLE, SCHEMA), [])
        document = load_document(EXAMPLE)

        draft = IntentDraft.from_mapping(document)

        self.assertEqual(draft.to_mapping(), document)
        self.assertEqual(draft.abstract_goal, document["spec"]["abstractGoal"])
        self.assertEqual(draft.capability_needs[0].action, "filesystem.write")

    def test_schema_allows_additive_extension_fields(self) -> None:
        document = copy.deepcopy(load_document(EXAMPLE))
        document["spec"]["x-future-alignment-note"] = {"kept": True}

        from jsonschema import Draft202012Validator
        import json

        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        errors = list(Draft202012Validator(schema).iter_errors(document))
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
