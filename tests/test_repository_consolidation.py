from __future__ import annotations

import json
import tomllib
import unittest
from pathlib import Path

from ahra import cli


ROOT = Path(__file__).resolve().parents[1]


class RepositoryConsolidationTests(unittest.TestCase):
    def test_component_inventory_has_no_unowned_or_untested_core(self) -> None:
        inventory = json.loads(
            (ROOT / "docs/architecture/component-inventory.json").read_text(encoding="utf-8")
        )

        core_entries = [
            component
            for component in inventory["components"]
            if component["lifecycle_class"] == "core"
        ]

        self.assertGreater(len(core_entries), 0)
        for component in core_entries:
            with self.subTest(component=component["id"]):
                self.assertTrue(component.get("owner"))
                self.assertTrue(component.get("tests"))
                self.assertTrue(component.get("consumers"))
                self.assertTrue(component.get("serves"))
                self.assertTrue(component.get("security_class"))
                self.assertTrue(component.get("artifact_evidence"))

    def test_default_scripts_do_not_expose_legacy_or_demo_entrypoints(self) -> None:
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        scripts = pyproject["project"]["scripts"]

        self.assertNotIn("ahra-mcp", scripts)
        self.assertNotIn("ahra-demo", scripts)
        self.assertEqual(scripts["ahra"], "ahra.cli:main")

    def test_removed_mcp_and_demo_implementations_are_absent(self) -> None:
        self.assertFalse((ROOT / "src/ahra/mcp_server.py").exists())
        self.assertFalse((ROOT / "src/ahra/demo.py").exists())
        self.assertFalse((ROOT / "tests/test_mcp_server.py").exists())

    def test_default_cli_help_excludes_legacy_workflow_surface(self) -> None:
        help_text = cli._build_parser().format_help()

        for hidden in ("workflow", "mcp", "demo", "fake-reference", "standard-harness", "loop-engineering"):
            with self.subTest(hidden=hidden):
                self.assertNotIn(hidden, help_text)
        self.assertIn("fixture", help_text)
        self.assertIn("evidence-gate", help_text)


if __name__ == "__main__":
    unittest.main()
