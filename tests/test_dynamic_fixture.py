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
        self.assertEqual(report["goalExecution"]["status"], "succeeded")
        self.assertEqual(report["goalExecution"]["repairCycles"], 1)
        self.assertEqual(len(report["goalExecution"]["planExecutionRefs"]), 2)
        self.assertEqual(report["goalExecution"]["openDefectRefs"], [])
        self.assertEqual(
            report["execution"]["initial"]["goal_execution_ref"],
            report["execution"]["repaired"]["goal_execution_ref"],
        )
        self.assertEqual(
            report["execution"]["repaired"]["parent_plan_execution_ref"],
            report["execution"]["initial"]["plan_execution_id"],
        )
        self.assertEqual(
            report["execution"]["repaired"]["parent_plan_digest"],
            report["planning"]["planIrDigest"],
        )
        self.assertEqual(
            report["planning"]["repairedPlanIr"]["metadata"]["version"],
            report["planning"]["planIr"]["metadata"]["version"] + 1,
        )
        self.assertEqual(report["defect"]["record"]["metadata"]["defectId"], "DEF-doc-staleness-l2")
        self.assertEqual(report["defect"]["record"]["spec"]["status"], "resolved")
        self.assertEqual(report["defect"]["record"]["spec"]["directClaimRefs"], ["CLAIM-defect-repair-functional"])
        self.assertIn("CLAIM-goal-completion", report["defect"]["record"]["spec"]["affectedClaimRefs"])
        self.assertIn("CLAIM-repair-boundary-governance", report["defect"]["record"]["spec"]["affectedClaimRefs"])
        self.assertEqual(report["defect"]["reproduction"]["failingGate"], "GATE-doc-health-l1")
        self.assertIn("src/doc_health.py", report["defect"]["record"]["spec"]["repairBoundary"])
        self.assertEqual(report["execution"]["repairChangedFiles"], ["src/doc_health.py"])
        self.assertTrue(report["execution"]["repairChangedOnlyAffectedPaths"])
        self.assertTrue(report["verification"]["selectedFewerThanFull"])
        self.assertLess(report["verification"]["secondGateCount"], report["verification"]["fullGateCount"])
        self.assertEqual(
            report["verification"]["secondGateCount"],
            report["verification"]["secondGateRunCount"],
        )
        self.assertEqual(
            report["verification"]["secondSelectedGateRefs"],
            report["execution"]["selectiveReverification"]["selectedGateRefs"],
        )
        self.assertEqual(
            report["verification"]["secondExecutedGateRunRefs"],
            report["execution"]["selectiveReverification"]["executedGateRunRefs"],
        )
        self.assertEqual(report["verification"]["gateExecutionIntegrity"], 1.0)
        self.assertEqual(report["verification"]["unrunGatePassCount"], 0)
        self.assertTrue(report["verification"]["lineageValid"])
        self.assertTrue(report["verification"]["initialGateRuns"])
        self.assertTrue(report["verification"]["finalGateRuns"])
        self.assertEqual(report["verification"]["gateRunCountByStatus"], {"passed": 7, "failed": 1})
        self.assertEqual(report["verification"]["gateRunCountByLevel"], {"L0": 2, "L1": 5, "L2": 1})
        self.assertTrue(all(item["gateRunId"] for item in report["verification"]["finalEvidence"]))
        self.assertTrue(report["verification"]["reusedEvidenceRefs"])
        self.assertTrue(report["verification"]["historicalExcludedEvidenceRefs"])
        self.assertEqual(report["verification"]["supersessionResolutionFailures"], [])
        self.assertEqual(report["verification"]["currentSetMetrics"]["supersessionResolutionFailures"], 0)
        self.assertGreater(report["verification"]["currentSetMetrics"]["historicalEvidenceCount"], 0)
        self.assertEqual(report["verification"]["currentClaimCoverage"], 1.0)
        self.assertTrue(report["verification"]["evidenceStatusEvents"])
        self.assertTrue(report["verification"]["staleCompletionRejected"])
        self.assertTrue(report["verification"]["openDefectRejected"])
        self.assertTrue(report["verification"]["finalCompletionAccepted"])
        self.assertEqual(report["capabilityAdmission"]["coverage"], 1.0)
        self.assertEqual(report["capabilityAdmission"]["unadmittedNodeExecutionCount"], 0)
        self.assertEqual(report["capabilityAdmission"]["syntheticGrantCount"], 0)
        self.assertEqual(report["capabilityAdmission"]["sideEffectNodeCount"], 4)
        self.assertEqual(report["capabilityAdmission"]["admittedNodeCount"], 4)
        self.assertTrue(report["capabilityAdmission"]["decisionRefs"])
        self.assertTrue(all(ref.startswith("PDEC-") for ref in report["capabilityAdmission"]["decisionRefs"]))
        self.assertTrue(report["capabilityAdmission"]["grantRefs"])
        self.assertTrue(all(ref.startswith("CGRANT-") for ref in report["capabilityAdmission"]["grantRefs"]))
        self.assertGreaterEqual(report["capabilityAdmission"]["denyCountByReason"].get("path_escape", 0), 1)
        self.assertEqual(report["capabilityAdmission"]["preSideEffectDenialRate"], 1.0)
        self.assertEqual(
            report["capabilityAdmission"]["runtimeAuditRecordsWithDecisionLineage"],
            report["capabilityAdmission"]["runtimeAuditRecordCount"],
        )
        self.assertFalse(report["security"]["unauthorizedWriteAllowed"])
        self.assertFalse(report["security"]["sideEffectExists"])
        self.assertIn(report["security"]["denyReason"], {"path_escape", "path_not_granted"})
        self.assertTrue(report["resume"]["ranBeforeResume"])
        self.assertTrue(report["resume"]["resumedWithFreshScheduler"])
        self.assertEqual(report["resume"]["terminalStatusAfterResume"], "failed")
        self.assertEqual(report["execution"]["executorCalls"].count("NODE-acceptance-order"), 1)
        self.assertEqual(report["execution"]["executorCalls"].count("NODE-security-audit"), 1)
        self.assertEqual(report["execution"]["executorCalls"].count("NODE-doc-checker-repair"), 1)
        self.assertTrue(report["execution"]["schedulerCreatedRepairNodeRun"])
        self.assertFalse(report["execution"]["directExecutorBypass"])
        self.assertEqual(
            sorted(report["execution"]["reusedNodeRefs"]),
            ["NODE-acceptance-order", "NODE-security-audit"],
        )
        reused_nodes = {
            node["node_id"]: node
            for node in report["execution"]["repairedNodeRuns"]
            if node["node_id"] in report["execution"]["reusedNodeRefs"]
        }
        self.assertEqual(set(reused_nodes), {"NODE-acceptance-order", "NODE-security-audit"})
        self.assertTrue(all(node["status"] == "succeeded" for node in reused_nodes.values()))
        self.assertTrue(report["fixture"]["sourceUnmodified"])
        self.assertFalse(report["fixture"]["ahraRepositorySelfModified"])

    def test_dynamic_fixture_has_no_direct_repair_executor_bypass(self) -> None:
        source = (ROOT / "src" / "ahra" / "dynamic_fixture.py").read_text(encoding="utf-8")

        for forbidden in (
            "executor.execute(",
            "_admit_node_capabilities",
            "NRUN-fixture-repair",
            "fixture:repair-runner",
        ):
            self.assertNotIn(forbidden, source)

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
