from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ahra.m1_experiment import run_m1_experiment


ROOT = Path(__file__).resolve().parents[1]
REQUEST = ROOT / "tests" / "fixtures" / "m1-minimal-project" / "goal-run-request.yaml"


class M1ExperimentTests(unittest.TestCase):
    def test_deterministic_experiment_writes_scorecard_and_raw_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            scorecard = run_m1_experiment(request_template=REQUEST, output_dir=Path(temp), run_count=2)

            self.assertEqual(scorecard["run_count"], 2)
            self.assertEqual(scorecard["success_count"], 2)
            self.assertEqual(scorecard["hard_metrics"]["false_completion_count"], 0)
            self.assertEqual(scorecard["hard_metrics"]["gate_execution_integrity"], 1.0)
            self.assertEqual(scorecard["hard_metrics"]["capability_admission_coverage"], 1.0)
            self.assertEqual(scorecard["hard_metrics"]["repair_boundary_compliance"], 1.0)
            self.assertEqual(scorecard["hard_metrics"]["resume_duplicate_effect_count"], 0)
            self.assertEqual(scorecard["hard_metrics"]["stale_fencing_accept_count"], 0)
            self.assertFalse(scorecard["hard_metrics"]["unauthorized_write_allowed"])
            self.assertGreater(scorecard["verification_efficiency"]["weightedVerificationSaving"], 0.0)
            self.assertEqual(len(scorecard["semanticDigestDistribution"]), 1)

            scorecard_path = Path(temp) / "m1-scorecard.json"
            p1_gate_runs = Path(temp) / "profiles" / "P1-defect-repair" / "p1-gate-runs.json"
            self.assertTrue(scorecard_path.exists())
            self.assertTrue(p1_gate_runs.exists())
            raw = json.loads(p1_gate_runs.read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(raw["gateRuns"]), 1)


if __name__ == "__main__":
    unittest.main()
