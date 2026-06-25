from __future__ import annotations

import copy
import inspect
import unittest
from pathlib import Path
from typing import get_type_hints

from ahra.plan_ir import (
    PlanCompilerConfig,
    PlanDraft,
    PlanPatchDraft,
    compile_plan_draft,
    compile_plan_patch,
    validate_plan_ir,
)
from ahra.ports import SchedulerPort
from ahra.validation import load_document


ROOT = Path(__file__).resolve().parents[1]
RECORDS = ROOT / "examples" / "records"

D1 = "sha256:" + "1" * 64
D2 = "sha256:" + "2" * 64
D3 = "sha256:" + "3" * 64
D4 = "sha256:" + "4" * 64
D5 = "sha256:" + "5" * 64
D6 = "sha256:" + "6" * 64
D7 = "sha256:" + "7" * 64


class PlanIRTests(unittest.TestCase):
    def test_canonical_equivalent_drafts_compile_to_same_digest(self) -> None:
        first = PlanDraft.from_mapping(_valid_draft_mapping())
        second_mapping = _valid_draft_mapping()
        second_mapping["spec"]["nodes"] = list(reversed(second_mapping["spec"]["nodes"]))
        second_mapping["spec"]["nodes"][0]["claimRefs"] = list(reversed(second_mapping["spec"]["nodes"][0]["claimRefs"]))
        second = PlanDraft.from_mapping(second_mapping)

        first_result = compile_plan_draft(first, _config())
        second_result = compile_plan_draft(second, _config())

        self.assertTrue(first_result.report.valid, _codes(first_result.report.errors))
        self.assertTrue(second_result.report.valid, _codes(second_result.report.errors))
        self.assertIsNotNone(first_result.plan)
        self.assertIsNotNone(second_result.plan)
        self.assertEqual(first_result.plan.digest(), second_result.plan.digest())  # type: ignore[union-attr]
        self.assertEqual(
            [node.node_id for node in first_result.plan.nodes],  # type: ignore[union-attr]
            ["NODE-implement-plan-compiler", "NODE-run-plan-validation-tests", "NODE-terminal-goal-verification"],
        )

    def test_adversarial_draft_fails_closed_with_all_error_classes(self) -> None:
        draft = PlanDraft.from_mapping(
            {
                "apiVersion": "ahra.dev/v1alpha1",
                "kind": "PlanDraft",
                "metadata": {
                    "goalId": "GOAL-plan-ir",
                    "proposedBy": "REL-planner@sha256:" + "a" * 64,
                },
                "spec": {
                    "nodes": [
                        {
                            "id": "NODE-bad",
                            "nodeType": "unknown_type",
                            "objective": "Show all validation errors.",
                            "claimRefs": ["CLAIM-plan-compiler-deterministic"],
                            "dependsOn": ["NODE-missing"],
                            "inputRefs": ["artifact://mutable/latest"],
                            "expectedOutputs": [
                                {
                                    "name": "unconsumed",
                                    "schemaRef": "ahra/artifact/code-change/0.1",
                                    "consumerNodeRefs": [],
                                    "artifactRequired": True,
                                }
                            ],
                            "capabilityRequests": [
                                {
                                    "capability": "production.deploy",
                                    "resources": ["prod://billing"],
                                }
                            ],
                            "gateRefs": [],
                            "runtimeRef": "runtime/unknown@sha256:" + "f" * 64,
                            "budgetRequest": {
                                "maxModelCalls": 0,
                                "maxToolCalls": -1,
                                "maxSpawnedNodes": -1,
                                "maxWallSeconds": -5,
                            },
                            "retryPolicy": {
                                "maxAttempts": 2,
                                "retryableFailureClasses": [],
                                "idempotencyKeyRequired": False,
                            },
                            "timeoutSeconds": 10,
                            "sideEffect": "non_idempotent",
                        }
                    ]
                },
            }
        )

        result = compile_plan_draft(draft, _config())

        self.assertIsNone(result.plan)
        codes = _codes(result.report.errors)
        for expected in {
            "unregistered-node-type",
            "missing-node-ref",
            "missing-gate-responsibility",
            "unregistered-runtime-ref",
            "mutable-latest-ref",
            "capability-out-of-scope",
            "invalid-budget",
            "inconsistent-timeout",
            "unconsumed-output",
            "invalid-retry-policy",
            "unsafe-non-idempotent-retry",
            "uncovered-claim",
            "missing-terminal-goal-verification",
        }:
            self.assertIn(expected, codes)
        self.assertEqual(result.report.to_dict()["kind"], "PlanValidationReport")
        self.assertEqual(result.report.to_dict()["spec"]["result"], "failed")

    def test_cycles_and_unbounded_fan_out_fail_closed(self) -> None:
        cycle_mapping = _valid_draft_mapping()
        cycle_mapping["spec"]["nodes"][0]["dependsOn"] = ["NODE-terminal-goal-verification"]
        cycle_result = compile_plan_draft(PlanDraft.from_mapping(cycle_mapping), _config())
        self.assertIn("cycle-detected", _codes(cycle_result.report.errors))

        fanout_mapping = _valid_draft_mapping()
        fanout_mapping["spec"]["nodes"].append(
            {
                "id": "NODE-extra-consumer",
                "nodeType": "gate_verification",
                "objective": "Create a second downstream consumer.",
                "claimRefs": ["CLAIM-plan-validation-fail-closed"],
                "dependsOn": ["NODE-implement-plan-compiler"],
                "inputRefs": ["src/ahra/plan_ir.py@sha256:" + "d" * 64],
                "expectedOutputs": [
                    {
                        "name": "extra-report",
                        "schemaRef": "ahra/plan-validation-report/0.1",
                        "consumerNodeRefs": ["NODE-terminal-goal-verification"],
                        "artifactRequired": True,
                    }
                ],
                "capabilityRequests": [],
                "gateRefs": ["GATE-plan-tests"],
                "runtimeRef": RUNTIME_REF,
                "budgetRequest": {"maxModelCalls": 1, "maxToolCalls": 1, "maxSpawnedNodes": 0},
                "timeoutSeconds": 30,
                "sideEffect": "idempotent",
            }
        )
        fanout_result = compile_plan_draft(PlanDraft.from_mapping(fanout_mapping), _config(max_fan_out=1))
        self.assertIn("unbounded-fan-out", _codes(fanout_result.report.errors))

    def test_plan_patch_creates_new_version_without_mutating_parent(self) -> None:
        parent_result = compile_plan_draft(PlanDraft.from_mapping(_valid_draft_mapping()), _config())
        self.assertTrue(parent_result.report.valid, _codes(parent_result.report.errors))
        parent = parent_result.plan
        assert parent is not None
        parent_digest = parent.digest()
        patch = PlanPatchDraft.from_mapping(_patch_mapping(parent_digest))

        patched = compile_plan_patch(parent, patch, _config())

        self.assertTrue(patched.report.valid, _codes(patched.report.errors))
        self.assertIsNotNone(patched.plan)
        self.assertEqual(parent.version, 1)
        self.assertEqual(parent.digest(), parent_digest)
        self.assertEqual(patched.plan.version, 2)  # type: ignore[union-attr]
        self.assertEqual(patched.plan.parent_plan_digest, parent_digest)  # type: ignore[union-attr]
        self.assertNotEqual(patched.plan.digest(), parent_digest)  # type: ignore[union-attr]
        replacement = {node.node_id: node for node in patched.plan.nodes}["NODE-run-plan-validation-tests"]  # type: ignore[union-attr]
        self.assertEqual(replacement.objective, "Rerun expanded adversarial plan validation tests.")

    def test_scheduler_port_accepts_plan_ir_not_plan_draft(self) -> None:
        hints = get_type_hints(SchedulerPort.submit_plan)
        self.assertEqual(hints["plan"].__name__, "PlanIR")
        self.assertNotIn("PlanDraft", inspect.signature(SchedulerPort.submit_plan).parameters)
        self.assertNotIn("PlanDraft", (ROOT / "src" / "ahra" / "ports.py").read_text(encoding="utf-8"))

    def test_validation_report_passes_for_compiled_plan(self) -> None:
        result = compile_plan_draft(PlanDraft.from_mapping(_valid_draft_mapping()), _config())
        self.assertTrue(result.report.valid, _codes(result.report.errors))
        assert result.plan is not None

        report = validate_plan_ir(result.plan, _config())

        self.assertTrue(report.valid, _codes(report.errors))
        self.assertEqual(report.to_dict()["spec"]["result"], "passed")
        self.assertEqual(report.to_dict()["spec"]["subjectDigest"], result.plan.digest())

    def test_example_plan_draft_round_trips_through_compiler(self) -> None:
        draft = PlanDraft.from_mapping(load_document(RECORDS / "plan-draft.json"))

        result = compile_plan_draft(draft, _config())

        self.assertTrue(result.report.valid, _codes(result.report.errors))
        self.assertIsNotNone(result.plan)


RUNTIME_REF = "runtime/local-worktree@sha256:" + "c" * 64


def _config(max_fan_out: int = 4) -> PlanCompilerConfig:
    return PlanCompilerConfig(
        goal_ref="GOAL-plan-ir",
        goal_digest=D1,
        claim_graph_digest=D2,
        required_claim_refs=frozenset(
            {
                "CLAIM-plan-compiler-deterministic",
                "CLAIM-plan-validation-fail-closed",
            }
        ),
        registered_node_types={
            "bounded_task": D3,
            "gate_verification": D4,
            "goal_verification": D5,
            "repair": D6,
        },
        registered_gate_refs={
            "GATE-plan-unit": D3,
            "GATE-plan-tests": D4,
            "GATE-goal-plan-review": D5,
        },
        registered_runtime_refs={RUNTIME_REF: D7},
        allowed_capabilities=frozenset({"filesystem.write", "process.exec"}),
        default_runtime_ref=RUNTIME_REF,
        max_fan_out=max_fan_out,
    )


def _valid_draft_mapping() -> dict:
    return copy.deepcopy(load_document(RECORDS / "plan-draft.json"))


def _patch_mapping(parent_digest: str) -> dict:
    data = copy.deepcopy(load_document(RECORDS / "plan-patch.json"))
    data["metadata"]["parentPlanDigest"] = parent_digest
    data["spec"]["parentPlanDigest"] = parent_digest
    return data


def _codes(errors: tuple) -> set[str]:
    return {error.code for error in errors}


if __name__ == "__main__":
    unittest.main()
