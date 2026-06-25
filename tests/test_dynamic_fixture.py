import json
import tempfile
import unittest
from pathlib import Path

from ahra.dynamic_fixture import run_dynamic_repair_fixture, write_dynamic_repair_fixture_report


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "dynamic-goal-project"


class DynamicFixtureTests(unittest.TestCase):
    def test_end_to_end_dynamic_repair_fixture_satisfies_acceptance_invariants(self) -> None:
        report = run_dynamic_repair_fixture(FIXTURE)

        self.assertEqual(report["goal"]["inputKind"], "GoalContract")
        self.assertTrue(report["acceptance"]["claimsBuiltBeforePlanIr"])
        self.assertFalse(report["planning"]["planDraftExecutedBeforeAdmission"])
        self.assertEqual(report["planning"]["executionValidation"]["spec"]["result"], "passed")
        self.assertEqual(report["planning"]["repairValidation"]["spec"]["result"], "passed")
        self.assertEqual(report["execution"]["executedPlanKind"], "PlanIR")
        self.assertEqual(report["defect"]["record"]["metadata"]["defectId"], "DEF-doc-staleness-l2")
        self.assertIn("src/doc_health.py", report["defect"]["record"]["spec"]["repairBoundary"])
        self.assertEqual(report["execution"]["repairChangedFiles"], ["src/doc_health.py"])
        self.assertTrue(report["execution"]["repairChangedOnlyAffectedPaths"])
        self.assertTrue(report["verification"]["selectedFewerThanFull"])
        self.assertLess(report["verification"]["secondGateCount"], report["verification"]["fullGateCount"])
        self.assertTrue(report["verification"]["reusedEvidenceRefs"])
        self.assertTrue(report["verification"]["staleCompletionRejected"])
        self.assertTrue(report["verification"]["openDefectRejected"])
        self.assertTrue(report["verification"]["finalCompletionAccepted"])
        self.assertFalse(report["security"]["unauthorizedWriteAllowed"])
        self.assertFalse(report["security"]["sideEffectExists"])
        self.assertIn(report["security"]["denyReason"], {"path_escape", "path_not_granted"})
        self.assertTrue(report["resume"]["ranBeforeResume"])
        self.assertTrue(report["resume"]["resumedWithFreshScheduler"])
        self.assertEqual(report["resume"]["terminalStatusAfterResume"], "failed")
        self.assertTrue(report["fixture"]["sourceUnmodified"])
        self.assertFalse(report["fixture"]["ahraRepositorySelfModified"])

    def test_cli_report_writer_persists_structured_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report_path = Path(temporary) / "dynamic-fixture-report.json"

            report = write_dynamic_repair_fixture_report(FIXTURE, report_path)
            stored = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(stored["schema_version"], "ahra/dynamic-fixture-report/0.1")
        self.assertEqual(stored["goal"], report["goal"])
        self.assertTrue(stored["verification"]["finalCompletionAccepted"])
        self.assertFalse(stored["security"]["unauthorizedWriteAllowed"])


if __name__ == "__main__":
    unittest.main()
