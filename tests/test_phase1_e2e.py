from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.phase1_helpers import bridge_completed_goal, start_goal


class Phase1EndToEndTests(unittest.TestCase):
    def test_simple_objective_goal_flows_intent_to_awkp_completion(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            start_result = start_goal(root)
            bridge_result = bridge_completed_goal(root, start_result)

            self.assertEqual(start_result["goalStatus"], "succeeded")
            self.assertEqual(start_result["planStatus"], "succeeded")
            self.assertTrue(start_result["completion"]["complete"])
            self.assertGreaterEqual(start_result["inspect"]["metrics"]["capabilityGrantRefCount"], 1)
            self.assertEqual(bridge_result["terminal_state"], "completed")
            self.assertEqual(bridge_result["state"]["state"], "completed")
            self.assertIn(bridge_result["evidence_ref"], bridge_result["state"]["evidence_refs"])


if __name__ == "__main__":
    unittest.main()
