from __future__ import annotations

import unittest

from ahra.context import ContextBudgetError, ContextBuilder, ContextSource


class ContextBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.builder = ContextBuilder()
        self.sources = [
            ContextSource("policy", "POL-1", b"p" * 40, "system-authoritative"),
            ContextSource("agent_release", "REL-1", b"a" * 40, "system-authoritative"),
            ContextSource("task", "TASK-1", b"t" * 40, "project-authoritative"),
            ContextSource("run_state", "RUN-1", b"r" * 40, "system-authoritative"),
            ContextSource("memory", "MEM-1", b"m" * 1000, "retrieved-untrusted"),
            ContextSource("output_contract", "OUT-1", b"o" * 40, "system-authoritative"),
        ]

    def test_manifest_is_deterministic(self) -> None:
        first = self.builder.build(
            run_id="RUN-1", agent_release_digest="sha256:test", sources=self.sources, token_budget=200
        )
        second = self.builder.build(
            run_id="RUN-1", agent_release_digest="sha256:test", sources=reversed(self.sources), token_budget=200
        )
        self.assertEqual(first.sha256, second.sha256)
        self.assertNotIn("MEM-1", [item.ref for item in first.items])
        self.assertIn("OUT-1", [item.ref for item in first.items])

    def test_mandatory_context_over_budget_fails(self) -> None:
        with self.assertRaises(ContextBudgetError):
            self.builder.build(
                run_id="RUN-1", agent_release_digest="sha256:test", sources=self.sources, token_budget=10
            )


if __name__ == "__main__":
    unittest.main()
