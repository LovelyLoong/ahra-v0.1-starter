from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ahra.acceptance_contracts import Claim, ClaimGraph, ClaimType, GateDefinition, GatePlan, GatePlanEntry, RiskLevel
from ahra.evidence_gate import EvidenceGateError, evaluate_task_gate
from ahra.evidence_v2 import DigestRef, EvidenceEnvironment, EvidenceResult, EvidenceV2, EvidenceValidityState
from ahra.verification import (
    DefectStatus,
    DeterministicGateRunner,
    GateExecutionRequest,
    GateExecutionStatus,
    GateRunnerRegistry,
    VerificationExecutionContext,
    VerificationExecutor,
    VerificationResult,
    VerificationSelection,
    VerificationTrigger,
    defect_from_result,
    evaluate_completion,
    select_gates,
    validate_gate_run_lineage,
)


D1 = "sha256:" + "1" * 64
D2 = "sha256:" + "2" * 64
D3 = "sha256:" + "3" * 64
D4 = "sha256:" + "4" * 64
D5 = "sha256:" + "5" * 64
D6 = "sha256:" + "6" * 64
D7 = "sha256:" + "7" * 64
D8 = "sha256:" + "8" * 64
D9 = "sha256:" + "9" * 64


class VerificationSelectionTests(unittest.TestCase):
    def test_selection_is_deterministic_for_same_inputs(self) -> None:
        graph, gates, plan = _fixture_contracts()
        evidence = (_evidence("EVD-cli-stale", "CLAIM-cli-detects-stale-docs", "ART-doc-cli", D2),)
        trigger = VerificationTrigger(changed_refs={"ART-doc-cli": D9})

        first = select_gates(graph=graph, gate_definitions=gates, gate_plan=plan, evidence_records=evidence, trigger=trigger)
        second = select_gates(graph=graph, gate_definitions=gates, gate_plan=plan, evidence_records=evidence, trigger=trigger)

        self.assertEqual(first, second)

    def test_selects_failed_affected_integration_and_mandatory_safety_gates(self) -> None:
        graph, gates, plan = _fixture_contracts()
        evidence = (
            _evidence("EVD-frontmatter-current", "CLAIM-frontmatter-parses", "ART-frontmatter", D3, stored=True),
            _evidence("EVD-cli-stale", "CLAIM-cli-detects-stale-docs", "ART-doc-cli", D2, stored=True),
        )
        trigger = VerificationTrigger(
            changed_refs={"ART-doc-cli": D9},
            failed_gate_refs=frozenset({"GATE-node-cli-unit"}),
        )

        selection = select_gates(graph=graph, gate_definitions=gates, gate_plan=plan, evidence_records=evidence, trigger=trigger)

        self.assertEqual(
            selection.selected_gate_refs,
            ("GATE-cli-integration", "GATE-node-cli-unit", "GATE-security-baseline"),
        )
        self.assertEqual(
            selection.full_gate_refs,
            ("GATE-cli-integration", "GATE-goal-completion", "GATE-node-cli-unit", "GATE-security-baseline"),
        )
        self.assertLess(len(selection.selected_gate_refs), len(selection.full_gate_refs))
        self.assertIn("CLAIM-evidence-recorded", selection.affected_claim_refs)
        self.assertIn("EVD-frontmatter-current", selection.reused_evidence_refs)
        self.assertIn("EVD-cli-stale", selection.stale_evidence_refs)
        self.assertEqual(selection.historical_evidence_refs, ())
        self.assertEqual(selection.resolution_failure_refs, ())
        self.assertIn("failed_gate:GATE-node-cli-unit", selection.rationale)
        self.assertIn("integration_boundary:GATE-cli-integration", selection.rationale)
        self.assertIn("mandatory_safety_claim:CLAIM-secret-safe->GATE-security-baseline", selection.rationale)

    def test_reuse_requires_current_evidence_and_matching_fingerprint(self) -> None:
        graph, gates, plan = _fixture_contracts()
        good = _evidence("EVD-frontmatter-current", "CLAIM-frontmatter-parses", "ART-frontmatter", D3, stored=True)
        bad = _evidence("EVD-bad-fingerprint", "CLAIM-secret-safe", "ART-security", D4, stored=False)
        missing = _evidence(
            "EVD-no-stored-fingerprint",
            "CLAIM-evidence-recorded",
            "ART-report",
            D8,
            stored_fingerprint=None,
        )

        selection = select_gates(
            graph=graph,
            gate_definitions=gates,
            gate_plan=plan,
            evidence_records=(good, bad, missing),
            trigger=VerificationTrigger(),
        )

        self.assertIn("EVD-frontmatter-current", selection.reused_evidence_refs)
        self.assertIn("EVD-bad-fingerprint", selection.stale_evidence_refs)
        self.assertIn("EVD-no-stored-fingerprint", selection.stale_evidence_refs)
        self.assertNotIn("EVD-bad-fingerprint", selection.reused_evidence_refs)
        self.assertNotIn("EVD-no-stored-fingerprint", selection.reused_evidence_refs)
        self.assertIn("fingerprint_not_matched:EVD-no-stored-fingerprint", selection.rationale)

    def test_completion_fails_for_missing_stale_expired_revoked_or_contradicted_evidence(self) -> None:
        graph = ClaimGraph(goal_ref="GOAL-one", version=1, claims=(_claim("CLAIM-one"),))
        now = datetime(2026, 6, 25, tzinfo=UTC)
        cases = [
            ("missing", (), VerificationTrigger(), ("CLAIM-one",)),
            (
                "stale",
                (_evidence("EVD-one", "CLAIM-one", "ART-one", D2, stored=True),),
                VerificationTrigger(changed_refs={"ART-one": D9}),
                (),
            ),
            (
                "expired",
                (_evidence("EVD-one", "CLAIM-one", "ART-one", D2, valid_until=now - timedelta(seconds=1)),),
                VerificationTrigger(now=now),
                (),
            ),
            (
                "revoked",
                (_evidence("EVD-one", "CLAIM-one", "ART-one", D2),),
                VerificationTrigger(revoked_evidence_refs=frozenset({"EVD-one"})),
                (),
            ),
            (
                "contradicted",
                (_evidence("EVD-one", "CLAIM-one", "ART-one", D2),),
                VerificationTrigger(contradicted_evidence_refs=frozenset({"EVD-one"})),
                (),
            ),
        ]

        for label, records, trigger, missing in cases:
            with self.subTest(label=label):
                result = evaluate_completion(graph=graph, evidence_records=records, trigger=trigger)
                self.assertFalse(result.complete)
                self.assertEqual(result.missing_claim_refs, missing)

        complete = evaluate_completion(
            graph=graph,
            evidence_records=(_evidence("EVD-one", "CLAIM-one", "ART-one", D2, stored=True),),
        )
        self.assertTrue(complete.complete)

    def test_completion_uses_current_set_instead_of_caller_curated_final_records(self) -> None:
        graph = ClaimGraph(goal_ref="GOAL-one", version=1, claims=(_claim("CLAIM-one"),))
        failed_old = _evidence(
            "EVD-one-failed",
            "CLAIM-one",
            "ART-one",
            D2,
            result=EvidenceResult.FAILED,
            stored=True,
        )
        passed_new = _evidence(
            "EVD-one-passed",
            "CLAIM-one",
            "ART-one",
            D2,
            supersedes=("EVD-one-failed",),
            stored=True,
        )

        result = evaluate_completion(graph=graph, evidence_records=(failed_old, passed_new))

        self.assertTrue(result.complete)
        self.assertEqual(result.historical_evidence_refs, ("EVD-one-failed",))
        self.assertEqual(result.current_claim_coverage, 1.0)

    def test_completion_blocks_stale_replacement_and_omitted_history(self) -> None:
        graph = ClaimGraph(goal_ref="GOAL-one", version=1, claims=(_claim("CLAIM-one"),))
        old = _evidence("EVD-one-old", "CLAIM-one", "ART-one", D2, stored=True)
        stale_new = _evidence(
            "EVD-one-new",
            "CLAIM-one",
            "ART-one",
            D2,
            validity_state=EvidenceValidityState.STALE,
            supersedes=("EVD-one-old",),
            stored=True,
        )

        stale_result = evaluate_completion(graph=graph, evidence_records=(old, stale_new))
        omitted_history_result = evaluate_completion(graph=graph, evidence_records=(stale_new,))

        self.assertFalse(stale_result.complete)
        self.assertEqual(stale_result.uncovered_claim_refs, ("CLAIM-one",))
        self.assertEqual(stale_result.historical_evidence_refs, ("EVD-one-old",))
        self.assertFalse(omitted_history_result.complete)
        self.assertEqual(omitted_history_result.resolution_failure_refs, ("EVD-one-new",))

    def test_failed_gate_creates_structured_multi_claim_defect_record(self) -> None:
        graph, _, _ = _fixture_contracts()
        result = VerificationResult(
            gate_ref="GATE-node-cli-unit",
            claim_refs=("CLAIM-cli-detects-stale-docs", "CLAIM-frontmatter-parses"),
            result=EvidenceResult.FAILED,
            expected="CLI exits non-zero for expired active documents.",
            actual="CLI returned zero.",
            refs=("ART-test-log",),
        )

        defect = defect_from_result(
            defect_id="DEF-doc-staleness-cli",
            result=result,
            repair_boundary="Repair CLI staleness detection only.",
            graph=graph,
            created_at=datetime(2026, 6, 25, tzinfo=UTC),
        )

        self.assertEqual(defect.status, DefectStatus.OPEN)
        self.assertEqual(defect.claim_ref, "CLAIM-cli-detects-stale-docs")
        self.assertEqual(
            defect.direct_claim_refs,
            ("CLAIM-cli-detects-stale-docs", "CLAIM-frontmatter-parses"),
        )
        self.assertEqual(
            defect.affected_claim_refs,
            (
                "CLAIM-cli-detects-stale-docs",
                "CLAIM-evidence-recorded",
                "CLAIM-frontmatter-parses",
            ),
        )
        self.assertEqual(defect.gate_ref, "GATE-node-cli-unit")
        self.assertEqual(defect.expected, result.expected)
        self.assertEqual(defect.actual, result.actual)
        self.assertEqual(defect.refs, ("ART-test-log",))
        self.assertEqual(defect.repair_boundary, "Repair CLI staleness detection only.")
        self.assertEqual(defect.to_dict()["kind"], "DefectRecord")
        self.assertEqual(
            defect.to_dict()["spec"]["affectedClaimRefs"],
            [
                "CLAIM-cli-detects-stale-docs",
                "CLAIM-evidence-recorded",
                "CLAIM-frontmatter-parses",
            ],
        )

    def test_selective_fixture_keeps_final_logical_coverage_complete(self) -> None:
        graph, gates, plan = _fixture_contracts()
        stale_records = (
            _evidence("EVD-frontmatter-current", "CLAIM-frontmatter-parses", "ART-frontmatter", D3, stored=True),
            _evidence("EVD-cli-stale", "CLAIM-cli-detects-stale-docs", "ART-doc-cli", D2, stored=True),
            _evidence("EVD-security-current", "CLAIM-secret-safe", "ART-security", D4, stored=True),
        )
        selection = select_gates(
            graph=graph,
            gate_definitions=gates,
            gate_plan=plan,
            evidence_records=stale_records,
            trigger=VerificationTrigger(changed_refs={"ART-doc-cli": D9}),
        )
        old_failed = _evidence(
            "EVD-cli-stale",
            "CLAIM-cli-detects-stale-docs",
            "ART-doc-cli",
            D2,
            result=EvidenceResult.FAILED,
            stored=True,
        )
        final_records = (
            _evidence("EVD-frontmatter-current", "CLAIM-frontmatter-parses", "ART-frontmatter", D3, stored=True),
            old_failed,
            _evidence(
                "EVD-cli-rerun",
                "CLAIM-cli-detects-stale-docs",
                "ART-doc-cli",
                D9,
                supersedes=("EVD-cli-stale",),
                stored=True,
            ),
            _evidence("EVD-security-current", "CLAIM-secret-safe", "ART-security", D4, stored=True),
            _evidence("EVD-evidence-rerun", "CLAIM-evidence-recorded", "ART-report", D8, stored=True),
        )

        self.assertLess(len(selection.selected_gate_refs), len(selection.full_gate_refs))
        self.assertTrue(selection.rationale)
        completion = evaluate_completion(graph=graph, evidence_records=final_records)
        self.assertTrue(completion.complete)
        self.assertEqual(completion.historical_evidence_refs, ("EVD-cli-stale",))

    def test_existing_task_evidence_gate_path_remains_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            task_dir = Path(temporary) / "work" / "tasks" / "TASK-X"
            task_dir.mkdir(parents=True)
            (task_dir / "task.md").write_text("# Acceptance criteria\n\n- [ ] Must have evidence.\n", encoding="utf-8")
            (task_dir / "state.json").write_text(
                json.dumps(
                    {
                        "schema_version": "awkp/0.1",
                        "task_id": "TASK-X",
                        "context_id": "CTX-X",
                        "state": "review",
                        "state_version": 1,
                        "owner": None,
                        "attempt": 1,
                        "lease": None,
                        "next_action": "review",
                        "pause_reason": None,
                        "blockers": [],
                        "artifact_refs": [],
                        "evidence_refs": [],
                        "updated_at": "2026-06-25T00:00:00Z",
                    }
                ),
                encoding="utf-8",
            )
            (task_dir / "artifact-manifest.json").write_text(
                json.dumps({"schema_version": "awkp/0.1", "task_id": "TASK-X", "artifacts": []}),
                encoding="utf-8",
            )
            (task_dir / "evidence-manifest.json").write_text(
                json.dumps({"schema_version": "awkp/0.1", "task_id": "TASK-X", "evidence": []}),
                encoding="utf-8",
            )
            (task_dir / "events.jsonl").write_text("", encoding="utf-8")
            report = Path(temporary) / "report.json"
            report.write_text(
                json.dumps(
                    {
                        "task_id": "TASK-X",
                        "verifier": "agent:independent-verifier",
                        "decision": "approve",
                        "criteria": [{"criterion_index": 1, "status": "passed", "evidence_refs": []}],
                        "commands": [],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(EvidenceGateError, "has no evidence_refs"):
                evaluate_task_gate(
                    "TASK-X",
                    work_root=Path(temporary) / "work",
                    expected_version=1,
                    report_path=report,
                    actor="agent:independent-verifier",
                    dry_run=True,
                )


class VerificationExecutorTests(unittest.TestCase):
    def test_executes_selected_gates_and_records_gate_run_backed_evidence(self) -> None:
        selection = _execution_selection("GATE-node-cli-unit", "GATE-cli-integration", "GATE-security-baseline")
        runner = DeterministicGateRunner()
        executor = _verification_executor(runner)

        report = asyncio.run(executor.execute_selection(selection, _execution_context()))

        self.assertTrue(report.passed)
        self.assertEqual(len(report.gate_runs), 3)
        self.assertEqual(len(report.evidence_records), 3)
        self.assertEqual(report.reused_evidence_refs, ("EVD-frontmatter-current",))
        self.assertEqual(report.gate_execution_integrity, 1.0)
        self.assertEqual(report.unrun_gate_pass_count, 0)
        self.assertEqual(validate_gate_run_lineage(report.evidence_records, report.gate_runs), ())
        self.assertEqual(tuple(call.gate_ref for call in runner.calls), selection.selected_gate_refs)
        for evidence in report.evidence_records:
            self.assertIn(evidence.gate_run_id, {gate_run.gate_run_id for gate_run in report.gate_runs})
            self.assertEqual(evidence.confidence, "verified")

    def test_missing_runner_fails_closed_without_synthetic_pass(self) -> None:
        report = asyncio.run(
            VerificationExecutor(GateRunnerRegistry()).execute_selection(
                _execution_selection("GATE-node-cli-unit"),
                _execution_context(),
            )
        )

        self.assertFalse(report.passed)
        self.assertEqual(report.missing_runner_gate_refs, ("GATE-node-cli-unit",))
        self.assertEqual(report.executed_gate_run_refs, ())
        self.assertEqual(report.evidence_records, ())
        self.assertEqual(report.gate_execution_integrity, 0.0)

    def test_runner_exception_records_blocking_gate_run_and_evidence(self) -> None:
        report = asyncio.run(
            _verification_executor(_ExplodingGateRunner()).execute_selection(
                _execution_selection("GATE-node-cli-unit"),
                _execution_context(),
            )
        )

        self.assertFalse(report.passed)
        self.assertEqual(report.attempts[0].failure_class, "runner_exception")
        self.assertEqual(report.attempts[0].status, GateExecutionStatus.ERROR)
        self.assertEqual(report.evidence_records[0].result, EvidenceResult.BLOCKED)
        self.assertEqual(validate_gate_run_lineage(report.evidence_records, report.gate_runs), ())

    def test_runner_timeout_records_timed_out_gate_run_and_evidence(self) -> None:
        report = asyncio.run(
            _verification_executor(DeterministicGateRunner(delay_seconds=0.05)).execute_selection(
                _execution_selection("GATE-node-cli-unit"),
                _execution_context(timeout_seconds=0.001),
            )
        )

        self.assertFalse(report.passed)
        self.assertEqual(report.attempts[0].failure_class, "runner_timeout")
        self.assertEqual(report.attempts[0].status, GateExecutionStatus.TIMED_OUT)
        self.assertEqual(report.evidence_records[0].result, EvidenceResult.BLOCKED)

    def test_malformed_runner_result_records_structured_failure(self) -> None:
        report = asyncio.run(
            _verification_executor(_MalformedGateRunner()).execute_selection(
                _execution_selection("GATE-node-cli-unit"),
                _execution_context(),
            )
        )

        self.assertFalse(report.passed)
        self.assertEqual(report.attempts[0].failure_class, "malformed_gate_result")
        self.assertEqual(report.evidence_records[0].result, EvidenceResult.BLOCKED)

    def test_duplicate_idempotency_key_blocks_second_gate_attempt(self) -> None:
        report = asyncio.run(
            _verification_executor(DeterministicGateRunner()).execute_selection(
                _execution_selection("GATE-node-cli-unit", "GATE-node-cli-unit"),
                _execution_context(),
            )
        )

        self.assertFalse(report.passed)
        self.assertEqual(len(report.gate_runs), 1)
        self.assertEqual(len(report.duplicate_idempotency_keys), 1)
        self.assertEqual(report.attempts[1].failure_class, "duplicate_idempotency_key")
        self.assertLess(report.gate_execution_integrity, 1.0)

    def test_unexpected_workspace_mutation_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            Path(temporary, "source.txt").write_text("stable\n", encoding="utf-8")
            report = asyncio.run(
                _verification_executor(DeterministicGateRunner(mutate_workspace=True)).execute_selection(
                    _execution_selection("GATE-node-cli-unit"),
                    _execution_context(workspace_ref=temporary),
                )
            )

        self.assertFalse(report.passed)
        self.assertEqual(report.attempts[0].failure_class, "unexpected_workspace_mutation")
        self.assertEqual(report.evidence_records[0].result, EvidenceResult.BLOCKED)

    def test_lineage_validator_reports_evidence_without_gate_run(self) -> None:
        report = asyncio.run(
            _verification_executor(DeterministicGateRunner()).execute_selection(
                _execution_selection("GATE-node-cli-unit"),
                _execution_context(),
            )
        )
        bad = replace(report.evidence_records[0], gate_run_id="GATERUN-missing")

        self.assertEqual(validate_gate_run_lineage((bad,), report.gate_runs), (bad.evidence_id,))


class _ExplodingGateRunner:
    gate_kind = "*"
    release_ref = "*"

    async def run(self, request: GateExecutionRequest) -> object:
        raise RuntimeError(f"boom: {request.gate_ref}")


class _MalformedGateRunner:
    gate_kind = "*"
    release_ref = "*"

    async def run(self, request: GateExecutionRequest) -> object:
        return {"gateRef": request.gate_ref, "status": "passed"}


def _verification_executor(runner: object) -> VerificationExecutor:
    registry = GateRunnerRegistry()
    registry.register(runner)
    return VerificationExecutor(registry)


def _execution_selection(*gate_refs: str) -> VerificationSelection:
    return VerificationSelection(
        selected_gate_refs=tuple(gate_refs),
        full_gate_refs=tuple(sorted(set(gate_refs))),
        affected_claim_refs=(
            "CLAIM-frontmatter-parses",
            "CLAIM-cli-detects-stale-docs",
            "CLAIM-secret-safe",
            "CLAIM-evidence-recorded",
        ),
        reused_evidence_refs=("EVD-frontmatter-current",),
        stale_evidence_refs=(),
        rationale=("test-execution",),
    )


def _execution_context(
    *,
    workspace_ref: str | None = None,
    timeout_seconds: float | None = None,
) -> VerificationExecutionContext:
    graph, gates, plan = _fixture_contracts()
    return VerificationExecutionContext(
        goal_execution_id=graph.goal_ref,
        plan_execution_id="PEX-verification-executor",
        node_run_id="NRUN-verification-executor",
        gate_definitions={gate.gate_id: gate for gate in gates},
        gate_definition_digests={gate.gate_id: D1 for gate in gates},
        gate_claim_refs={entry.gate_ref: entry.claim_refs for entry in plan.gates},
        subjects=(DigestRef("ART-doc-staleness-cli", D2),),
        dependency_evidence=(),
        environment=EvidenceEnvironment(
            runtime_profile_digest=D4,
            policy_digest=D5,
            verifier_release_digest=D6,
            test_definition_digest=D7,
        ),
        workspace_ref=workspace_ref,
        timeout_seconds=timeout_seconds,
    )


def _fixture_contracts() -> tuple[ClaimGraph, tuple[GateDefinition, ...], GatePlan]:
    graph = ClaimGraph(
        goal_ref="GOAL-doc-staleness",
        version=1,
        claims=(
            _claim("CLAIM-frontmatter-parses", gate_refs=("GATE-cli-integration",), claim_type=ClaimType.STRUCTURAL),
            _claim("CLAIM-cli-detects-stale-docs", gate_refs=("GATE-node-cli-unit",), depends_on=("CLAIM-frontmatter-parses",)),
            _claim("CLAIM-secret-safe", gate_refs=("GATE-security-baseline",), claim_type=ClaimType.SECURITY),
            _claim("CLAIM-evidence-recorded", gate_refs=("GATE-cli-integration",), claim_type=ClaimType.GOVERNANCE, depends_on=("CLAIM-cli-detects-stale-docs",)),
        ),
    )
    gates = (
        _gate("GATE-node-cli-unit", "L0"),
        _gate("GATE-cli-integration", "L1"),
        _gate("GATE-security-baseline", "L1"),
        _gate("GATE-goal-completion", "L2"),
    )
    plan = GatePlan(
        goal_ref="GOAL-doc-staleness",
        claim_graph_ref="ClaimGraph/doc-staleness-claims@v1",
        version=1,
        gates=(
            GatePlanEntry("GATE-node-cli-unit", ("CLAIM-cli-detects-stale-docs",), "contract_test"),
            GatePlanEntry("GATE-cli-integration", ("CLAIM-frontmatter-parses", "CLAIM-evidence-recorded"), "contract_test"),
            GatePlanEntry("GATE-security-baseline", ("CLAIM-secret-safe",), "contract_test"),
            GatePlanEntry("GATE-goal-completion", ("CLAIM-frontmatter-parses", "CLAIM-cli-detects-stale-docs", "CLAIM-secret-safe", "CLAIM-evidence-recorded"), "semantic_review"),
        ),
    )
    return graph, gates, plan


def _claim(
    claim_id: str,
    *,
    claim_type: ClaimType = ClaimType.FUNCTIONAL,
    gate_refs: tuple[str, ...] = ("GATE-node-cli-unit",),
    depends_on: tuple[str, ...] = (),
) -> Claim:
    return Claim(
        claim_id=claim_id,
        claim_type=claim_type,
        statement=f"{claim_id} statement",
        criterion_refs=("CRIT-functional",),
        depends_on=depends_on,
        risk_level=RiskLevel.R1,
        required_evidence_kinds=("contract_test",),
        gate_refs=gate_refs,
        required=True,
    )


def _gate(gate_id: str, level: str) -> GateDefinition:
    return GateDefinition(
        gate_id=gate_id,
        version=1,
        level=level,
        evidence_kind="semantic_review" if level == "L2" else "contract_test",
        verifier_mode="deterministic",
        risk_level=RiskLevel.R1,
    )


def _evidence(
    evidence_id: str,
    claim_ref: str,
    subject_ref: str,
    digest: str,
    *,
    stored: bool = False,
    valid_until: datetime | None = None,
    stored_fingerprint: str | None | object = ...,
    result: EvidenceResult = EvidenceResult.PASSED,
    validity_state: EvidenceValidityState = EvidenceValidityState.CURRENT,
    supersedes: tuple[str, ...] = (),
) -> EvidenceV2:
    evidence = EvidenceV2(
        evidence_id=evidence_id,
        claim_refs=(claim_ref,),
        gate_ref="GATE-node-cli-unit",
        gate_definition_digest=D1,
        gate_run_id=f"GATERUN-{evidence_id.removeprefix('EVD-')}",
        result=result,
        confidence="verified",
        subjects=(DigestRef(subject_ref, digest),),
        dependencies=(),
        environment=EvidenceEnvironment(
            runtime_profile_digest=D4,
            policy_digest=D5,
            verifier_release_digest=D6,
            test_definition_digest=D7,
        ),
        validity_state=validity_state,
        valid_until=valid_until,
        supersedes=supersedes,
    )
    if stored:
        fingerprint = evidence.fingerprint()
    elif stored_fingerprint is ...:
        fingerprint = "sha256:" + "0" * 64
    else:
        fingerprint = stored_fingerprint
    if stored or stored_fingerprint is not ...:
        return EvidenceV2(
            evidence_id=evidence.evidence_id,
            claim_refs=evidence.claim_refs,
            gate_ref=evidence.gate_ref,
            gate_definition_digest=evidence.gate_definition_digest,
            gate_run_id=evidence.gate_run_id,
            result=evidence.result,
            confidence=evidence.confidence,
            subjects=evidence.subjects,
            dependencies=evidence.dependencies,
            environment=evidence.environment,
            validity_state=evidence.validity_state,
            valid_until=evidence.valid_until,
            stored_fingerprint=fingerprint,  # type: ignore[arg-type]
            supersedes=evidence.supersedes,
        )
    return EvidenceV2(
        evidence_id=evidence.evidence_id,
        claim_refs=evidence.claim_refs,
        gate_ref=evidence.gate_ref,
        gate_definition_digest=evidence.gate_definition_digest,
        gate_run_id=evidence.gate_run_id,
        result=evidence.result,
        confidence=evidence.confidence,
        subjects=evidence.subjects,
        dependencies=evidence.dependencies,
        environment=evidence.environment,
        validity_state=evidence.validity_state,
        valid_until=evidence.valid_until,
        stored_fingerprint="sha256:" + "0" * 64,
        supersedes=evidence.supersedes,
    )


if __name__ == "__main__":
    unittest.main()
