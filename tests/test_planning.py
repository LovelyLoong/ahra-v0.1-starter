from __future__ import annotations

import asyncio
import copy
import unittest
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ahra.plan_ir import PlanCompilerConfig, PlanDraft, PlanPatchDraft, compile_plan_draft
from ahra.agent_contracts import validate_agent_output
from ahra.planner_contracts import (
    ExecutionPlanningRequest,
    PlannerBudgetLimits,
    PlannerContextRequest,
    PlannerRiskPolicy,
    PlannerValidationStatus,
    RepairPlanningRequest,
    ReplanTriggerType,
)
from ahra.planning import (
    AgentDriverExecutionPlannerAdapter,
    FixtureExecutionPlanner,
    PlannerAdapterError,
    PlannerContextBuilder,
    PlannerOutputValidator,
    PlannerRuntimeBoundaryError,
    ensure_planner_runtime_profile,
    plan_draft_output_contract,
    planner_read_only_runtime_profile,
)
from ahra.ports import AgentDriverRegistry, AgentOutputContractError, AgentRunRequest, AgentRunResult, AgentRuntimeProfile
from ahra.validation import load_document
from ahra.verification import DefectRecord


ROOT = Path(__file__).resolve().parents[1]
RECORDS = ROOT / "examples" / "records"

D1 = "sha256:" + "1" * 64
D2 = "sha256:" + "2" * 64
D3 = "sha256:" + "3" * 64
D4 = "sha256:" + "4" * 64
D5 = "sha256:" + "5" * 64
D6 = "sha256:" + "6" * 64
D7 = "sha256:" + "7" * 64
RUNTIME_REF = "runtime/local-worktree@sha256:" + "c" * 64


class PlanningTests(unittest.TestCase):
    def test_context_manifest_and_planner_artifacts_are_deterministic(self) -> None:
        builder = PlannerContextBuilder()
        defect = _defect()
        first = builder.build(
            _context_request(
                claim_refs=("CLAIM-plan-validation-fail-closed", "CLAIM-plan-compiler-deterministic"),
                defects=(defect,),
            )
        )
        second = builder.build(
            _context_request(
                claim_refs=("CLAIM-plan-compiler-deterministic", "CLAIM-plan-validation-fail-closed"),
                defects=(defect,),
            )
        )

        self.assertEqual(first.context_manifest.sha256, second.context_manifest.sha256)
        self.assertEqual(first.input_artifact.sha256, second.input_artifact.sha256)
        self.assertEqual(first.input_artifact.release_digest, first.context_manifest.agent_release_digest)
        self.assertEqual(first.input_artifact.context_manifest_digest, first.context_manifest.sha256)

    def test_context_input_exposes_allowed_capabilities_to_planner(self) -> None:
        bundle = PlannerContextBuilder().build(_context_request())

        self.assertEqual(bundle.input_artifact.payload["allowedCapabilities"], ["filesystem.write", "process.exec"])
        self.assertTrue(
            any("payload.allowedCapabilities" in instruction for instruction in plan_draft_output_contract().instructions)
        )

    def test_planner_runtime_profile_is_read_only_without_project_write_grants(self) -> None:
        profile = planner_read_only_runtime_profile()

        ensure_planner_runtime_profile(profile)

        self.assertEqual(profile.sandbox, "read_only")
        self.assertEqual(profile.capabilities, ())
        with self.assertRaisesRegex(PlannerRuntimeBoundaryError, "read_only"):
            ensure_planner_runtime_profile(
                AgentRuntimeProfile(profile_ref="planner/bad", sandbox="workspace_write")
            )
        with self.assertRaisesRegex(PlannerRuntimeBoundaryError, "filesystem.write"):
            ensure_planner_runtime_profile(
                AgentRuntimeProfile(
                    profile_ref="planner/bad",
                    sandbox="read_only",
                    capabilities=("filesystem.write",),
                )
            )

    def test_fixture_planner_is_deterministic_and_needs_no_external_driver(self) -> None:
        bundle = _context_bundle()
        request = ExecutionPlanningRequest(
            goal_ref="GOAL-plan-ir",
            context_manifest=bundle.context_manifest,
            input_artifact=bundle.input_artifact,
        )
        planner = FixtureExecutionPlanner(_valid_draft_mapping())

        first = asyncio.run(planner.propose_plan(request))
        second = asyncio.run(planner.propose_plan(request))

        self.assertEqual(first.draft.to_dict(), second.draft.to_dict())
        self.assertEqual(first.output_artifact.sha256, second.output_artifact.sha256)
        self.assertEqual(first.output_artifact.context_manifest_digest, bundle.context_manifest.sha256)

    def test_planner_output_validation_fails_closed_before_execution(self) -> None:
        bundle = _context_bundle()
        validator = PlannerOutputValidator()

        valid = validator.validate_execution_draft(
            draft=PlanDraft.from_mapping(_valid_draft_mapping()),
            config=_config(),
            context_manifest=bundle.context_manifest,
            budget_limits=_limits(),
        )

        self.assertTrue(valid.accepted, _codes(valid.report.errors))
        self.assertIsNotNone(valid.plan)
        self.assertEqual(valid.report.subject_digest, valid.output_artifact.sha256)

        uncovered_mapping = _valid_draft_mapping()
        for node in uncovered_mapping["spec"]["nodes"]:
            node["claimRefs"] = [
                claim_ref
                for claim_ref in node["claimRefs"]
                if claim_ref != "CLAIM-plan-validation-fail-closed"
            ]
        uncovered = validator.validate_execution_draft(
            draft=PlanDraft.from_mapping(uncovered_mapping),
            config=_config(),
            context_manifest=bundle.context_manifest,
            budget_limits=_limits(),
        )
        self.assertIn("uncovered-claim", _codes(uncovered.report.errors))
        self.assertIsNone(uncovered.plan)

        cyclic_mapping = _valid_draft_mapping()
        cyclic_mapping["spec"]["nodes"][0]["dependsOn"] = ["NODE-terminal-goal-verification"]
        cyclic = validator.validate_execution_draft(
            draft=PlanDraft.from_mapping(cyclic_mapping),
            config=_config(),
            context_manifest=bundle.context_manifest,
            budget_limits=_limits(),
        )
        self.assertIn("cycle-detected", _codes(cyclic.report.errors))
        self.assertIsNone(cyclic.plan)

        over_budget = validator.validate_execution_draft(
            draft=PlanDraft.from_mapping(_valid_draft_mapping()),
            config=_config(),
            context_manifest=bundle.context_manifest,
            budget_limits=PlannerBudgetLimits(max_model_calls=1, max_tool_calls=200),
        )
        self.assertIn("planner-total-model-calls-exceeded", _codes(over_budget.report.errors))
        self.assertIsNone(over_budget.plan)

        negative_cost_mapping = _valid_draft_mapping()
        negative_cost_mapping["spec"]["nodes"][0]["budgetRequest"]["maxCostUsd"] = -100.0
        negative_cost = validator.validate_execution_draft(
            draft=PlanDraft.from_mapping(negative_cost_mapping),
            config=_config(),
            context_manifest=bundle.context_manifest,
            budget_limits=PlannerBudgetLimits(max_model_calls=100, max_tool_calls=200, max_cost_usd=1.0),
        )
        self.assertIn("invalid-budget", _codes(negative_cost.report.errors))
        self.assertIsNone(negative_cost.plan)

        over_privileged = validator.validate_execution_draft(
            draft=PlanDraft.from_mapping(_valid_draft_mapping()),
            config=_config(allowed_capabilities=frozenset({"process.exec"})),
            context_manifest=bundle.context_manifest,
            budget_limits=_limits(),
        )
        self.assertIn("capability-out-of-scope", _codes(over_privileged.report.errors))
        self.assertIsNone(over_privileged.plan)

    def test_risk_policy_requires_approval_or_review_for_configured_classes(self) -> None:
        bundle = _context_bundle()
        validator = PlannerOutputValidator(
            PlannerRiskPolicy(approval_required_risk_levels=("R1",), plan_review_required_risk_levels=())
        )

        blocked = validator.validate_execution_draft(
            draft=PlanDraft.from_mapping(_valid_draft_mapping()),
            config=_config(),
            context_manifest=bundle.context_manifest,
            budget_limits=_limits(),
            risk_level="R1",
        )
        allowed = validator.validate_execution_draft(
            draft=PlanDraft.from_mapping(_valid_draft_mapping()),
            config=_config(),
            context_manifest=bundle.context_manifest,
            budget_limits=_limits(),
            risk_level="R1",
            approval_refs=("APR-plan-review",),
        )

        self.assertEqual(blocked.status, PlannerValidationStatus.APPROVAL_REQUIRED)
        self.assertIn("planner-approval-required", _codes(blocked.report.errors))
        self.assertIsNotNone(blocked.approval_requirement)
        self.assertTrue(allowed.accepted, _codes(allowed.report.errors))

    def test_agent_driver_planner_adapter_failures_are_structured_without_fallback(self) -> None:
        bundle = _context_bundle()
        request = ExecutionPlanningRequest(
            goal_ref="GOAL-plan-ir",
            context_manifest=bundle.context_manifest,
            input_artifact=bundle.input_artifact,
        )
        fallback = CapturingDriver(_valid_draft_mapping())
        registry = AgentDriverRegistry()
        registry.register("fallback", fallback)

        with self.assertRaises(PlannerAdapterError) as missing:
            asyncio.run(AgentDriverExecutionPlannerAdapter(registry, "missing").propose_plan(request))

        self.assertEqual(missing.exception.failure.code, "planner-driver-unavailable")
        self.assertEqual(fallback.calls, 0)

        failing_registry = AgentDriverRegistry()
        failing_registry.register("bad", FailingDriver())
        with self.assertRaises(PlannerAdapterError) as failed:
            asyncio.run(AgentDriverExecutionPlannerAdapter(failing_registry, "bad").propose_plan(request))
        self.assertEqual(failed.exception.failure.code, "planner-driver-failed")

        malformed_registry = AgentDriverRegistry()
        malformed_registry.register("malformed", CapturingDriver({"kind": "PlanDraft"}))
        with self.assertRaises(PlannerAdapterError) as malformed:
            asyncio.run(AgentDriverExecutionPlannerAdapter(malformed_registry, "malformed").propose_plan(request))
        self.assertEqual(malformed.exception.failure.code, "planner-output-invalid")

        incomplete_mapping_registry = AgentDriverRegistry()
        incomplete_mapping_registry.register(
            "incomplete",
            CapturingDriver(
                {
                    "apiVersion": "ahra.dev/v1alpha1",
                    "kind": "PlanDraft",
                    "metadata": {},
                    "spec": {"nodes": []},
                }
            ),
        )
        with self.assertRaises(PlannerAdapterError) as incomplete:
            asyncio.run(AgentDriverExecutionPlannerAdapter(incomplete_mapping_registry, "incomplete").propose_plan(request))
        self.assertEqual(incomplete.exception.failure.code, "planner-output-invalid")
        self.assertIsNotNone(incomplete.exception.output_artifact)
        assert incomplete.exception.output_artifact is not None
        payload = incomplete.exception.output_artifact.payload
        self.assertEqual(payload["failure"]["code"], "planner-output-invalid")
        self.assertIn("driverOutput", payload)
        self.assertIn("driverOutputSha256", payload)

    def test_plan_draft_output_contract_rejects_task0040_alias_shape(self) -> None:
        task0040_like_output = {
            "apiVersion": "ahra.dev/v1alpha1",
            "kind": "PlanDraft",
            "metadata": {
                "runId": "TASK-0041-MODE-A-R01",
                "goalRef": "GOAL-M1-GENERIC-SMOKE",
            },
            "spec": {
                "nodes": [
                    {
                        "id": "node-1",
                        "type": "bounded_task",
                        "claims": ["CLM-WRITE-ARTIFACT"],
                        "gates": ["GATE-write-artifact"],
                        "bounds": {"maxModelCalls": 2, "maxToolCalls": 2},
                    }
                ]
            },
        }

        with self.assertRaises(AgentOutputContractError) as raised:
            validate_agent_output(plan_draft_output_contract(), task0040_like_output)

        details = "\n".join(raised.exception.details)
        self.assertIn("goalId", details)
        self.assertIn("proposedBy", details)
        self.assertIn("nodeType", details)
        self.assertIn("budgetRequest", details)

    def test_defect_repair_patch_is_bounded_and_reuses_unchanged_nodes_and_evidence(self) -> None:
        bundle = _context_bundle()
        validator = PlannerOutputValidator()
        parent_result = compile_plan_draft(PlanDraft.from_mapping(_valid_draft_mapping()), _config())
        self.assertTrue(parent_result.report.valid, _codes(parent_result.report.errors))
        parent = parent_result.plan
        assert parent is not None
        patch_mapping = _patch_mapping(parent.digest())
        patch = PlanPatchDraft.from_mapping(patch_mapping)
        defect = _defect()

        valid = validator.validate_repair_patch(
            parent=parent,
            patch=patch,
            config=_config(),
            context_manifest=bundle.context_manifest,
            budget_limits=_limits(),
            defects=(defect,),
            trigger_type=ReplanTriggerType.DEFECT,
            repair_cycle=0,
        )

        self.assertTrue(valid.accepted, _codes(valid.report.errors))
        self.assertIsNotNone(valid.plan)
        self.assertEqual(valid.plan.version, 2)  # type: ignore[union-attr]
        self.assertIn("EVD-plan-compiler-existing", valid.report.refs)
        self.assertIn("DEF-plan-validator", valid.report.refs)

        missing_evidence_mapping = copy.deepcopy(patch_mapping)
        missing_evidence_mapping["spec"].pop("reusedEvidenceRefs")
        missing_evidence = validator.validate_repair_patch(
            parent=parent,
            patch=PlanPatchDraft.from_mapping(missing_evidence_mapping),
            config=_config(),
            context_manifest=bundle.context_manifest,
            budget_limits=_limits(),
            defects=(defect,),
            trigger_type=ReplanTriggerType.DEFECT,
            repair_cycle=0,
        )
        self.assertIn("missing-reused-evidence-ref", _codes(missing_evidence.report.errors))

        invalid_trigger = validator.validate_repair_patch(
            parent=parent,
            patch=patch,
            config=_config(),
            context_manifest=bundle.context_manifest,
            budget_limits=_limits(),
            defects=(defect,),
            trigger_type="model_said_so",
            repair_cycle=0,
        )
        self.assertIn("invalid-replan-trigger", _codes(invalid_trigger.report.errors))

        exhausted = validator.validate_repair_patch(
            parent=parent,
            patch=patch,
            config=_config(),
            context_manifest=bundle.context_manifest,
            budget_limits=PlannerBudgetLimits(max_model_calls=100, max_tool_calls=200, max_repair_cycles=1),
            defects=(defect,),
            trigger_type=ReplanTriggerType.DEFECT,
            repair_cycle=1,
        )
        self.assertIn("repair-cycle-limit-exceeded", _codes(exhausted.report.errors))


class CapturingDriver:
    def __init__(self, output: dict[str, Any]) -> None:
        self.output = output
        self.calls = 0

    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        self.calls += 1
        return AgentRunResult(output=self.output)


class FailingDriver:
    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        raise RuntimeError("driver exploded")


def _context_bundle():
    return PlannerContextBuilder().build(_context_request())


def _context_request(
    *,
    claim_refs: tuple[str, ...] = (
        "CLAIM-plan-compiler-deterministic",
        "CLAIM-plan-validation-fail-closed",
    ),
    defects: tuple[DefectRecord, ...] = (),
) -> PlannerContextRequest:
    return PlannerContextRequest(
        run_id="RUN-planner-test",
        agent_release_digest="sha256:" + "a" * 64,
        goal_ref="GOAL-plan-ir",
        goal_digest=D1,
        policy_ref="policy/planner@sha256:" + "b" * 64,
        policy_digest="sha256:" + "b" * 64,
        allowed_capabilities=("filesystem.write", "process.exec"),
        claim_refs=claim_refs,
        registered_node_types={
            "goal_verification": D5,
            "bounded_task": D3,
            "gate_verification": D4,
            "repair": D6,
        },
        registered_gate_refs={
            "GATE-goal-plan-review": D5,
            "GATE-plan-tests": D4,
            "GATE-plan-unit": D3,
        },
        registered_runtime_refs={RUNTIME_REF: D7},
        budget_limits=_limits(),
        defects=defects,
    )


def _config(allowed_capabilities: frozenset[str] = frozenset({"filesystem.write", "process.exec"})) -> PlanCompilerConfig:
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
        allowed_capabilities=allowed_capabilities,
        default_runtime_ref=RUNTIME_REF,
    )


def _limits() -> PlannerBudgetLimits:
    return PlannerBudgetLimits(
        max_plan_nodes=10,
        max_plan_depth=5,
        max_model_calls=100,
        max_tool_calls=200,
        max_spawned_nodes=0,
        max_repair_cycles=2,
        max_fan_out=4,
        max_wall_seconds=3000,
    )


def _defect() -> DefectRecord:
    return DefectRecord(
        defect_id="DEF-plan-validator",
        claim_ref="CLAIM-plan-validation-fail-closed",
        gate_ref="GATE-plan-tests",
        expected="plan validation passes",
        actual="plan validation failed",
        refs=("EVD-plan-validation-fail",),
        repair_boundary="node:NODE-run-plan-validation-tests",
        created_at=datetime(2026, 6, 25, tzinfo=UTC),
    )


def _valid_draft_mapping() -> dict[str, Any]:
    return copy.deepcopy(load_document(RECORDS / "plan-draft.json"))


def _patch_mapping(parent_digest: str) -> dict[str, Any]:
    data = copy.deepcopy(load_document(RECORDS / "plan-patch.json"))
    data["metadata"]["parentPlanDigest"] = parent_digest
    data["spec"]["parentPlanDigest"] = parent_digest
    return data


def _codes(errors: tuple) -> set[str]:
    return {error.code for error in errors}


if __name__ == "__main__":
    unittest.main()
