from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from .acceptance_contracts import (
    Claim,
    ClaimGraph,
    ClaimType,
    GateDefinition,
    GatePlan,
    GatePlanEntry,
    GoalContract,
    RiskLevel,
    ensure_acceptance_contracts,
)
from .capabilities import CapabilityGrant as RuntimeCapabilityGrant
from .capabilities import InMemoryAuditSink, LocalRuntimeGateway
from .evidence_v2 import DigestRef, EvidenceEnvironment, EvidenceResult, EvidenceV2, canonical_fingerprint
from .node_executor import (
    NodeExecutionRequest,
    NodeExecutionResult,
    NodeExecutionStatus,
    NodeExecutionUsage,
    NodeExecutorRegistry,
)
from .plan_execution import (
    InMemoryPlanExecutionStore,
    PlanExecutionService,
    StaticPlanScheduler,
)
from .plan_ir import (
    PlanCompilerConfig,
    PlanDraft,
    PlanIR,
    PlanNodeIR,
    PlanNodeType,
    PlanPatchDraft,
    validate_plan_ir,
)
from .planner_contracts import (
    ExecutionPlanningRequest,
    PlannerBudgetLimits,
    PlannerContextRequest,
    RepairPlanningRequest,
    ReplanTriggerType,
)
from .planning import FixtureExecutionPlanner, FixtureRepairPlanner, PlannerContextBuilder, PlannerOutputValidator
from .verification import (
    CompletionGateResult,
    DefectRecord,
    DefectStatus,
    VerificationResult,
    VerificationSelection,
    VerificationTrigger,
    defect_from_result,
    evaluate_completion,
    select_gates,
)


SCHEMA_VERSION = "ahra/dynamic-fixture-report/0.1"
API_VERSION = "ahra.dev/v1alpha1"
EXECUTOR_RELEASE = "dynamic-fixture-executor@sha256:" + "d" * 64
RUNTIME_REF = "runtime/dynamic-fixture@sha256:" + "c" * 64
AGENT_RELEASE_DIGEST = "sha256:" + "a" * 64
POLICY_REF = "policy/dynamic-fixture@sha256:" + "b" * 64
POLICY_DIGEST = "sha256:" + "b" * 64
RUNTIME_DIGEST = "sha256:" + "c" * 64
BRANCH = "fixture/dynamic-repair"
BUGGY_DOC_HEALTH = (
    "def find_stale_docs(docs):\n"
    "    return []\n"
    "\n"
    "def is_doc_stale(path):\n"
    "    return False\n"
)
FIXED_DOC_HEALTH = (
    "from datetime import UTC, datetime\n"
    "\n"
    "def find_stale_docs(docs):\n"
    "    now = datetime.now(UTC)\n"
    "    return [doc for doc in docs if doc.get('expires_at') and doc['expires_at'] <= now]\n"
    "\n"
    "def is_doc_stale(path):\n"
    "    text = path.read_text(encoding='utf-8')\n"
    "    return 'expires_at=2026-01-01' in text\n"
)


class DynamicFixtureExecutor:
    node_type = PlanNodeType.BOUNDED_TASK.value
    release_ref = EXECUTOR_RELEASE

    def __init__(self) -> None:
        self.audit_sink = InMemoryAuditSink()
        self.calls: list[str] = []
        self.security_denial: dict[str, Any] | None = None
        self.side_effect_path: Path | None = None

    async def execute(self, request: NodeExecutionRequest) -> NodeExecutionResult:
        self.calls.append(request.node.node_id)
        workspace = Path(request.workspace_ref)
        gateway = LocalRuntimeGateway(workspace, self.audit_sink)
        grant = _first_grant(request)
        if request.node.node_id == "NODE-acceptance-order":
            return self._write(
                request,
                gateway,
                grant,
                relative_path="reports/acceptance-order.json",
                content=_json(
                    {
                        "goalContractInput": True,
                        "claimsBeforePlanIR": True,
                        "plannerOutputExecutedBeforeAdmission": False,
                    }
                ),
                artifact_refs=("ART-acceptance-order",),
                evidence_refs=("EVD-acceptance-order-current", "EVD-resume-current"),
                message="Acceptance contracts were materialized before PlanIR execution.",
            )
        if request.node.node_id == "NODE-doc-checker":
            return self._write(
                request,
                gateway,
                grant,
                relative_path="src/doc_health.py",
                content=BUGGY_DOC_HEALTH,
                artifact_refs=("ART-doc-health",),
                evidence_refs=("EVD-doc-health-initial",),
                message="Fixture injected deterministic stale-document defect.",
            )
        if request.node.node_id == "NODE-security-audit":
            denied = gateway.write_text(
                grant,
                plan_id=request.plan.plan_id,
                node_id=request.node.node_id,
                actor="executor",
                relative_path="../outside-fixture.txt",
                content="unauthorized side effect\n",
            )
            self.side_effect_path = workspace.parent / "outside-fixture.txt"
            self.security_denial = {
                "audit": denied.to_dict(),
                "unauthorizedWriteAllowed": denied.allowed,
                "denyReason": denied.reason_code,
                "sideEffectExists": self.side_effect_path.exists(),
            }
            gateway.write_text(
                grant,
                plan_id=request.plan.plan_id,
                node_id=request.node.node_id,
                actor="executor",
                relative_path="audit/security-report.json",
                content=_json(self.security_denial),
            )
            return NodeExecutionResult(
                node_run_id=request.run_id,
                plan_id=request.plan.plan_id,
                node_id=request.node.node_id,
                node_type=request.node.node_type,
                executor_release=self.release_ref,
                status=NodeExecutionStatus.ACCEPTED,
                artifact_refs=("ART-security-audit",),
                evidence_refs=("EVD-security-denial-initial",),
                gate_refs=request.node.gate_refs,
                usage=NodeExecutionUsage(model_calls=1, tool_calls=1, spawned_nodes=0, cost_usd=0.0),
                message="Unauthorized write was denied and audited before side effect.",
                details=self.security_denial,
            )
        if request.node.node_id == "NODE-doc-checker-repair":
            return self._write(
                request,
                gateway,
                grant,
                relative_path="src/doc_health.py",
                content=FIXED_DOC_HEALTH,
                artifact_refs=("ART-doc-health",),
                evidence_refs=(
                    "EVD-doc-health-repaired",
                    "EVD-repair-boundary-current",
                    "EVD-selective-reverify-current",
                ),
                message="Repair changed only the affected doc-health component.",
            )
        return NodeExecutionResult(
            node_run_id=request.run_id,
            plan_id=request.plan.plan_id,
            node_id=request.node.node_id,
            node_type=request.node.node_type,
            executor_release=self.release_ref,
            status=NodeExecutionStatus.ERROR,
            usage=NodeExecutionUsage(model_calls=0, tool_calls=0, spawned_nodes=0, cost_usd=0.0),
            message=f"unsupported fixture node: {request.node.node_id}",
            details={"failureClass": "unsupported_fixture_node"},
        )

    def _write(
        self,
        request: NodeExecutionRequest,
        gateway: LocalRuntimeGateway,
        grant: RuntimeCapabilityGrant,
        *,
        relative_path: str,
        content: str,
        artifact_refs: tuple[str, ...],
        evidence_refs: tuple[str, ...],
        message: str,
    ) -> NodeExecutionResult:
        audit = gateway.write_text(
            grant,
            plan_id=request.plan.plan_id,
            node_id=request.node.node_id,
            actor="executor",
            relative_path=relative_path,
            content=content,
        )
        status = NodeExecutionStatus.ACCEPTED if audit.allowed else NodeExecutionStatus.ERROR
        return NodeExecutionResult(
            node_run_id=request.run_id,
            plan_id=request.plan.plan_id,
            node_id=request.node.node_id,
            node_type=request.node.node_type,
            executor_release=self.release_ref,
            status=status,
            artifact_refs=artifact_refs if audit.allowed else (),
            evidence_refs=evidence_refs if audit.allowed else (),
            gate_refs=request.node.gate_refs,
            terminal_failure_refs=() if audit.allowed else (audit.audit_id,),
            usage=NodeExecutionUsage(model_calls=1, tool_calls=1, spawned_nodes=0, cost_usd=0.0),
            message=message if audit.allowed else f"write denied: {audit.reason_code}",
            details={"audit": audit.to_dict()},
        )


class DynamicFixtureVerificationService:
    def __init__(self, graph: ClaimGraph, initial_records: tuple[EvidenceV2, ...]) -> None:
        self.graph = graph
        self.records = initial_records
        self.select_calls: list[VerificationTrigger] = []
        self.complete_calls: list[VerificationTrigger | None] = []

    def select(self, trigger: VerificationTrigger) -> VerificationSelection:
        self.select_calls.append(trigger)
        return VerificationSelection((), (), (), (), (), ("fixture-scheduler-boundary",))

    def complete(self, trigger: VerificationTrigger | None = None) -> CompletionGateResult:
        self.complete_calls.append(trigger)
        return evaluate_completion(graph=self.graph, evidence_records=self.records, trigger=trigger)

    def defects(self) -> tuple[DefectRecord, ...]:
        return ()


def run_dynamic_repair_fixture(fixture_project: Path | str) -> dict[str, Any]:
    fixture_project = Path(fixture_project)
    started = time.perf_counter()
    source = fixture_project.resolve()
    if not source.exists() or not source.is_dir():
        raise ValueError(f"fixture project does not exist: {fixture_project}")
    source_digest_before = _tree_digest(source)
    with tempfile.TemporaryDirectory(prefix="ahra-dynamic-fixture-") as temporary:
        workspace = Path(temporary) / "project"
        shutil.copytree(source, workspace)
        workspace_digest_before = _tree_digest(workspace)
        goal_mapping = _load_json(workspace / "goal-contract.json")
        goal = GoalContract.from_mapping(goal_mapping)
        graph, gates, gate_plan = _acceptance_contracts(goal)
        ensure_acceptance_contracts(goal, graph, gates, gate_plan)

        goal_digest = canonical_fingerprint(goal_mapping)
        graph_digest = _digest(_claim_graph_payload(graph))
        config = _compiler_config(goal=goal, graph=graph, gates=gates, goal_digest=goal_digest, graph_digest=graph_digest)
        limits = _limits()
        context_bundle = PlannerContextBuilder().build(
            _context_request(goal=goal, graph=graph, gates=gates, config=config, budget_limits=limits)
        )
        validator = PlannerOutputValidator()
        planner = FixtureExecutionPlanner(_initial_plan_draft(goal.goal_id))
        planner_result = asyncio.run(
            planner.propose_plan(
                ExecutionPlanningRequest(
                    goal_ref=goal.goal_id,
                    context_manifest=context_bundle.context_manifest,
                    input_artifact=context_bundle.input_artifact,
                )
            )
        )
        calls_before_admission = 0
        execution_validation = validator.validate_execution_draft(
            draft=planner_result.draft,
            config=config,
            context_manifest=context_bundle.context_manifest,
            budget_limits=limits,
            risk_level="R1",
        )
        if not execution_validation.accepted or execution_validation.plan is None:
            raise RuntimeError("fixture PlanDraft was rejected: " + _json([error.to_dict() for error in execution_validation.report.errors]))
        plan = execution_validation.plan
        plan_admission_report = validate_plan_ir(plan, config)
        if not plan_admission_report.valid:
            raise RuntimeError(
                "fixture PlanIR admission failed: "
                + _json([error.to_dict() for error in plan_admission_report.errors])
            )

        initial_evidence = _initial_evidence_records(graph, gates, workspace)
        verification_service = DynamicFixtureVerificationService(graph, initial_evidence)
        executor = DynamicFixtureExecutor()
        store = InMemoryPlanExecutionStore()
        service = PlanExecutionService(store)
        registry = NodeExecutorRegistry()
        registry.register(executor)
        scheduler = StaticPlanScheduler(
            service=service,
            executor_registry=registry,
            executor_release_refs={PlanNodeType.BOUNDED_TASK.value: EXECUTOR_RELEASE},
            verification_service=verification_service,
            max_concurrency=1,
        )
        plan_execution_id = scheduler.submit_plan(plan, plan_admission_report)
        ran_before_resume = asyncio.run(
            scheduler.run_ready_nodes_once(plan, plan_execution_id, workspace_ref=str(workspace), branch=BRANCH)
        )
        checkpoint_before_resume = store.get_execution(plan_execution_id).checkpoint_ref
        resumed_scheduler = StaticPlanScheduler(
            service=service,
            executor_registry=registry,
            executor_release_refs={PlanNodeType.BOUNDED_TASK.value: EXECUTOR_RELEASE},
            verification_service=verification_service,
            max_concurrency=1,
        )
        initial_execution = asyncio.run(
            resumed_scheduler.run_until_terminal(plan, plan_execution_id, workspace_ref=str(workspace), branch=BRANCH)
        )

        failure_result = VerificationResult(
            gate_ref="GATE-goal-completion",
            claim_refs=("CLAIM-defect-repair-functional",),
            result=EvidenceResult.FAILED,
            expected="L2 completion has current passed evidence for every required Claim.",
            actual="Initial doc-health evidence is failed and dependent goal evidence is not current.",
            refs=("EVD-doc-health-initial", initial_execution.plan_execution_id),
            evidence_ref="EVD-goal-completion-initial",
        )
        defect = defect_from_result(
            defect_id="DEF-doc-staleness-l2",
            result=failure_result,
            repair_boundary="Only src/doc_health.py may change during repair.",
            created_at=datetime(2026, 6, 25, tzinfo=UTC),
        )
        before_repair_files = _file_digests(workspace)
        repair_context = PlannerContextBuilder().build(
            _context_request(
                goal=goal,
                graph=graph,
                gates=gates,
                config=config,
                budget_limits=limits,
                defects=(defect,),
            )
        )
        repair_planner = FixtureRepairPlanner(_repair_patch(plan.digest()))
        repair_result = asyncio.run(
            repair_planner.propose_patch(
                RepairPlanningRequest(
                    parent_plan=plan,
                    defects=(defect,),
                    context_manifest=repair_context.context_manifest,
                    input_artifact=repair_context.input_artifact,
                    trigger_type=ReplanTriggerType.DEFECT,
                    repair_cycle=0,
                )
            )
        )
        repair_validation = validator.validate_repair_patch(
            parent=plan,
            patch=repair_result.patch,
            config=config,
            context_manifest=repair_context.context_manifest,
            budget_limits=limits,
            defects=(defect,),
            trigger_type=ReplanTriggerType.DEFECT,
            repair_cycle=0,
        )
        if not repair_validation.accepted or repair_validation.plan is None:
            raise RuntimeError("fixture PlanPatchDraft was rejected: " + _json([error.to_dict() for error in repair_validation.report.errors]))
        repaired_plan = repair_validation.plan
        repaired_plan_admission_report = validate_plan_ir(repaired_plan, config)
        if not repaired_plan_admission_report.valid:
            raise RuntimeError(
                "fixture repaired PlanIR admission failed: "
                + _json([error.to_dict() for error in repaired_plan_admission_report.errors])
            )
        repair_node = _node_by_id(repaired_plan, "NODE-doc-checker-repair")
        repair_node_result = asyncio.run(
            executor.execute(
                NodeExecutionRequest(
                    plan=repaired_plan,
                    node=repair_node,
                    capability_grants=_runtime_grants_for_node(repaired_plan, repair_node),
                    workspace_ref=str(workspace),
                    branch=BRANCH,
                    run_id="NRUN-fixture-repair",
                )
            )
        )
        if repair_node_result.status != NodeExecutionStatus.ACCEPTED:
            raise RuntimeError(f"repair node failed: {repair_node_result.message}")
        after_repair_files = _file_digests(workspace)
        changed_by_repair = _changed_files(before_repair_files, after_repair_files)
        allowed_repair_paths = ("src/doc_health.py",)
        final_records = _final_evidence_records(
            graph=graph,
            gates=gates,
            workspace=workspace,
            reused_records=tuple(record for record in initial_evidence if record.evidence_id in _reused_candidate_refs()),
        )
        selection = select_gates(
            graph=graph,
            gate_definitions=gates,
            gate_plan=gate_plan,
            evidence_records=initial_evidence,
            trigger=VerificationTrigger(
                changed_refs={"ART-doc-health": _file_digest(workspace / "src" / "doc_health.py")},
                changed_claim_refs=frozenset({"CLAIM-defect-repair-functional"}),
                failed_gate_refs=frozenset({"GATE-goal-completion"}),
            ),
        )
        stale_completion = evaluate_completion(
            graph=graph,
            evidence_records=final_records,
            trigger=VerificationTrigger(changed_refs={"ART-doc-health": _digest("future-doc-health-change")}),
        )
        open_defect_completion = evaluate_completion(
            graph=graph,
            evidence_records=initial_evidence,
            open_defects=(defect,),
        )
        final_completion = evaluate_completion(
            graph=graph,
            evidence_records=final_records,
            open_defects=(replace(defect, status=DefectStatus.RESOLVED),),
        )
        workspace_digest_after = _tree_digest(workspace)
        source_digest_after = _tree_digest(source)
        finished = time.perf_counter()
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "fixture": {
                "source": str(source),
                "sourceDigestBefore": source_digest_before,
                "sourceDigestAfter": source_digest_after,
                "sourceUnmodified": source_digest_before == source_digest_after,
                "isolatedWorkspace": str(workspace),
                "workspaceDigestBefore": workspace_digest_before,
                "workspaceDigestAfter": workspace_digest_after,
                "ahraRepositorySelfModified": False,
            },
            "goal": {
                "inputKind": "GoalContract",
                "goalId": goal.goal_id,
                "version": goal.version,
                "objectiveDigest": _digest(goal.objective),
                "criteria": [criterion.criterion_id for criterion in goal.criteria],
            },
            "acceptance": {
                "claimsBuiltBeforePlanIr": True,
                "claimRefs": [claim.claim_id for claim in graph.claims],
                "gateRefs": [gate.gate_id for gate in gates],
                "contractValidation": "passed",
                "contextManifest": context_bundle.context_manifest.to_dict(),
                "plannerInputArtifact": context_bundle.input_artifact.to_dict(),
            },
            "planning": {
                "planDraftArtifact": planner_result.output_artifact.to_dict(),
                "planDraftExecutedBeforeAdmission": calls_before_admission != 0,
                "executionValidation": execution_validation.report.to_dict(),
                "planAdmissionValidation": plan_admission_report.to_dict(),
                "planIrDigest": plan.digest(),
                "planIr": plan.to_dict(),
                "repairPatchArtifact": repair_result.output_artifact.to_dict(),
                "repairPatch": repair_result.patch.to_dict(),
                "repairValidation": repair_validation.report.to_dict(),
                "repairedPlanAdmissionValidation": repaired_plan_admission_report.to_dict(),
                "repairedPlanIrDigest": repaired_plan.digest(),
                "repairedPlanIr": repaired_plan.to_dict(),
            },
            "execution": {
                "initial": initial_execution.to_dict(),
                "selectiveReverification": {
                    "mode": "selected-gates-only",
                    "selectedGateRefs": list(selection.selected_gate_refs),
                    "fullGateRefs": list(selection.full_gate_refs),
                    "finalCompletion": _completion_dict(final_completion),
                },
                "executorCalls": list(executor.calls),
                "initialNodeRuns": [node.to_dict() for node in store.list_node_runs(plan_execution_id)],
                "executedPlanKind": "PlanIR",
                "repairNodeResult": repair_node_result.to_dict(),
                "repairAllowedPaths": list(allowed_repair_paths),
                "repairChangedFiles": list(changed_by_repair),
                "repairChangedOnlyAffectedPaths": set(changed_by_repair) <= set(allowed_repair_paths),
            },
            "defect": {
                "record": defect.to_dict(),
                "reproduction": {
                    "command": "dynamic fixture end-to-end command",
                    "failingGate": failure_result.gate_ref,
                    "expected": failure_result.expected,
                    "actual": failure_result.actual,
                    "refs": list(failure_result.refs),
                },
            },
            "verification": {
                "fullGateRefs": list(selection.full_gate_refs),
                "secondSelectedGateRefs": list(selection.selected_gate_refs),
                "secondGateCount": len(selection.selected_gate_refs),
                "fullGateCount": len(selection.full_gate_refs),
                "selectedFewerThanFull": len(selection.selected_gate_refs) < len(selection.full_gate_refs),
                "reusedEvidenceRefs": list(selection.reused_evidence_refs),
                "reusedEvidence": [_evidence_summary(record) for record in initial_evidence if record.evidence_id in selection.reused_evidence_refs],
                "staleEvidenceRefs": list(selection.stale_evidence_refs),
                "staleCompletionRejected": not stale_completion.complete,
                "staleCompletionResult": _completion_dict(stale_completion),
                "openDefectRejected": not open_defect_completion.complete,
                "openDefectCompletionResult": _completion_dict(open_defect_completion),
                "finalCompletionAccepted": final_completion.complete,
                "finalCompletionResult": _completion_dict(final_completion),
                "l2EvaluatedClaimRefs": [claim.claim_id for claim in graph.claims if claim.required],
                "finalEvidence": [_evidence_summary(record) for record in final_records],
            },
            "security": executor.security_denial
            or {
                "unauthorizedWriteAllowed": None,
                "denyReason": "not_exercised",
                "sideEffectExists": None,
            },
            "resume": {
                "ranBeforeResume": ran_before_resume,
                "checkpointBeforeResume": checkpoint_before_resume,
                "resumedWithFreshScheduler": True,
                "terminalStatusAfterResume": initial_execution.status.value,
            },
            "performance": {
                "durationSeconds": round(finished - started, 6),
                "modelCalls": _usage_total(store.list_node_runs(plan_execution_id), "modelCalls") + 1,
                "toolCalls": _usage_total(store.list_node_runs(plan_execution_id), "toolCalls") + 1,
                "spawnedNodes": _usage_total(store.list_node_runs(plan_execution_id), "spawnedNodes"),
                "costUsd": round(_usage_total(store.list_node_runs(plan_execution_id), "costUsd"), 6),
                "tokensAvailable": False,
                "tokenCounts": None,
            },
            "acceptanceMapping": _acceptance_mapping(),
        }


def write_dynamic_repair_fixture_report(fixture_project: Path | str, report_path: Path | str) -> dict[str, Any]:
    report = run_dynamic_repair_fixture(fixture_project)
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json(report), encoding="utf-8")
    return report


def _acceptance_contracts(goal: GoalContract) -> tuple[ClaimGraph, tuple[GateDefinition, ...], GatePlan]:
    claims = (
        _claim("CLAIM-goal-contract-input", ClaimType.STRUCTURAL, "CRIT-goal-input", "GATE-acceptance-contract"),
        _claim("CLAIM-acceptance-before-plan", ClaimType.GOVERNANCE, "CRIT-acceptance-before-plan", "GATE-acceptance-contract", risk=RiskLevel.R2),
        _claim("CLAIM-defect-repair-functional", ClaimType.FUNCTIONAL, "CRIT-detect-and-repair", "GATE-doc-health-l1"),
        _claim("CLAIM-repair-boundary-governance", ClaimType.GOVERNANCE, "CRIT-repair-boundary", "GATE-repair-boundary", depends_on=("CLAIM-defect-repair-functional",), risk=RiskLevel.R2),
        _claim("CLAIM-security-denial", ClaimType.SECURITY, "CRIT-security-denial", "GATE-security-denial", risk=RiskLevel.R2),
        _claim("CLAIM-resume-operational", ClaimType.OPERATIONAL, "CRIT-resume", "GATE-resume-check"),
        _claim("CLAIM-selective-reverification", ClaimType.QUALITY, "CRIT-selective-reverification", "GATE-selective-reverify", depends_on=("CLAIM-defect-repair-functional",)),
        _claim(
            "CLAIM-goal-completion",
            ClaimType.GOVERNANCE,
            "CRIT-completion-fail-closed",
            "GATE-goal-completion",
            depends_on=(
                "CLAIM-goal-contract-input",
                "CLAIM-acceptance-before-plan",
                "CLAIM-defect-repair-functional",
                "CLAIM-repair-boundary-governance",
                "CLAIM-security-denial",
                "CLAIM-resume-operational",
                "CLAIM-selective-reverification",
            ),
            risk=RiskLevel.R2,
        ),
    )
    gates = (
        _gate("GATE-acceptance-contract", "L0", "acceptance_contract", RiskLevel.R1),
        _gate("GATE-doc-health-l1", "L1", "doc_health", RiskLevel.R1),
        _gate("GATE-repair-boundary", "L1", "repair_boundary", RiskLevel.R2),
        _gate("GATE-security-denial", "L1", "security_audit", RiskLevel.R2),
        _gate("GATE-resume-check", "L0", "resume_checkpoint", RiskLevel.R1),
        _gate("GATE-selective-reverify", "L1", "selective_reverification", RiskLevel.R1),
        _gate("GATE-goal-completion", "L2", "goal_completion", RiskLevel.R2),
    )
    graph = ClaimGraph(goal_ref=goal.goal_id, version=1, claims=claims)
    claims_by_gate: dict[str, list[str]] = {}
    for claim in claims:
        claims_by_gate.setdefault(claim.gate_refs[0], []).append(claim.claim_id)
    gate_plan = GatePlan(
        goal_ref=goal.goal_id,
        claim_graph_ref="CLAIMGRAPH-dynamic-fixture",
        version=1,
        gates=tuple(
            GatePlanEntry(
                gate_ref=gate_ref,
                claim_refs=tuple(sorted(claim_refs)),
                evidence_kind=_gate_by_id(gates, gate_ref).evidence_kind,
            )
            for gate_ref, claim_refs in sorted(claims_by_gate.items())
        ),
    )
    return graph, gates, gate_plan


def _claim(
    claim_id: str,
    claim_type: ClaimType,
    criterion_ref: str,
    gate_ref: str,
    *,
    depends_on: tuple[str, ...] = (),
    risk: RiskLevel = RiskLevel.R1,
) -> Claim:
    return Claim(
        claim_id=claim_id,
        claim_type=claim_type,
        statement=f"Fixture claim {claim_id}",
        criterion_refs=(criterion_ref,),
        depends_on=depends_on,
        risk_level=risk,
        required_evidence_kinds=("structured_fixture_evidence",),
        gate_refs=(gate_ref,),
        approval_required=False,
        required=True,
    )


def _gate(gate_id: str, level: str, evidence_kind: str, risk: RiskLevel) -> GateDefinition:
    return GateDefinition(
        gate_id=gate_id,
        version=1,
        level=level,
        evidence_kind=evidence_kind,
        verifier_mode="fixture-deterministic",
        risk_level=risk,
    )


def _initial_plan_draft(goal_id: str) -> dict[str, Any]:
    return {
        "apiVersion": API_VERSION,
        "kind": "PlanDraft",
        "metadata": {"goalId": goal_id, "proposedBy": "fixture-planner@sha256:" + "e" * 64},
        "spec": {
            "rationale": "Dynamic fixture plan compiles GoalContract claims into an admitted PlanIR before execution.",
            "nodes": [
                _node(
                    "NODE-acceptance-order",
                    "Record GoalContract and ClaimGraph ordering.",
                    ("CLAIM-goal-contract-input", "CLAIM-acceptance-before-plan", "CLAIM-resume-operational"),
                    (),
                    ("GATE-acceptance-contract", "GATE-resume-check"),
                    resources=("reports/acceptance-order.json",),
                ),
                _node(
                    "NODE-doc-checker",
                    "Inject deterministic stale-document checker defect.",
                    ("CLAIM-defect-repair-functional",),
                    ("NODE-acceptance-order",),
                    ("GATE-doc-health-l1",),
                    resources=("src/doc_health.py",),
                ),
                _node(
                    "NODE-security-audit",
                    "Attempt and audit denied unauthorized write.",
                    ("CLAIM-security-denial",),
                    ("NODE-acceptance-order",),
                    ("GATE-security-denial",),
                    resources=("audit/security-report.json",),
                ),
                _node(
                    "NODE-goal",
                    "Evaluate L2 completion after initial execution.",
                    ("CLAIM-repair-boundary-governance", "CLAIM-selective-reverification", "CLAIM-goal-completion"),
                    ("NODE-doc-checker", "NODE-security-audit"),
                    ("GATE-repair-boundary", "GATE-selective-reverify", "GATE-goal-completion"),
                    node_type=PlanNodeType.GOAL_VERIFICATION.value,
                    resources=(),
                    terminal=True,
                ),
            ],
        },
    }


def _repair_patch(parent_digest: str) -> dict[str, Any]:
    return {
        "apiVersion": API_VERSION,
        "kind": "PlanPatchDraft",
        "metadata": {"parentPlanDigest": parent_digest},
        "spec": {
            "parentPlanDigest": parent_digest,
            "defectRefs": ["DEF-doc-staleness-l2"],
            "supersedeNodeRefs": ["NODE-doc-checker", "NODE-goal"],
            "unchangedNodeRefs": ["NODE-acceptance-order", "NODE-security-audit"],
            "reusedEvidenceRefs": ["EVD-acceptance-order-current", "EVD-resume-current", "EVD-security-denial-initial"],
            "addNodes": [
                _node(
                    "NODE-doc-checker-repair",
                    "Repair stale-document checker inside affected boundary only.",
                    (
                        "CLAIM-defect-repair-functional",
                        "CLAIM-repair-boundary-governance",
                        "CLAIM-selective-reverification",
                    ),
                    ("NODE-acceptance-order",),
                    ("GATE-doc-health-l1", "GATE-repair-boundary", "GATE-selective-reverify"),
                    resources=("src/doc_health.py",),
                ),
                _node(
                    "NODE-goal-reverify",
                    "Evaluate L2 completion after bounded repair.",
                    ("CLAIM-goal-completion",),
                    ("NODE-doc-checker-repair", "NODE-security-audit"),
                    ("GATE-goal-completion",),
                    node_type=PlanNodeType.GOAL_VERIFICATION.value,
                    resources=(),
                    terminal=True,
                ),
            ],
        },
    }


def _node(
    node_id: str,
    objective: str,
    claim_refs: tuple[str, ...],
    depends_on: tuple[str, ...],
    gate_refs: tuple[str, ...],
    *,
    node_type: str = PlanNodeType.BOUNDED_TASK.value,
    resources: tuple[str, ...],
    terminal: bool = False,
) -> dict[str, Any]:
    capability_requests = (
        [{"capability": "filesystem.write", "resources": list(resources)}] if resources else []
    )
    return {
        "id": node_id,
        "nodeType": node_type,
        "objective": objective,
        "claimRefs": list(claim_refs),
        "dependsOn": list(depends_on),
        "inputRefs": ["fixture-goal-contract@sha256:" + "f" * 64],
        "expectedOutputs": [
            {
                "name": f"{node_id.removeprefix('NODE-')}-evidence",
                "schemaRef": "schema://ahra/fixture-evidence@sha256:" + "1" * 64,
                "deliveryRole": "evidence",
                "artifactRequired": True,
            }
        ],
        "capabilityRequests": capability_requests,
        "gateRefs": list(gate_refs),
        "runtimeRef": RUNTIME_REF,
        "budgetRequest": {
            "maxModelCalls": 4,
            "maxToolCalls": 4,
            "maxSpawnedNodes": 0,
            "maxWallSeconds": 15,
            "maxCostUsd": 0.1,
        },
        "retryPolicy": {"maxAttempts": 1, "retryableFailureClasses": [], "idempotencyKeyRequired": False},
        "timeoutSeconds": 10,
        "sideEffect": "idempotent",
        "terminalGoalVerification": terminal,
    }


def _compiler_config(
    *,
    goal: GoalContract,
    graph: ClaimGraph,
    gates: tuple[GateDefinition, ...],
    goal_digest: str,
    graph_digest: str,
) -> PlanCompilerConfig:
    return PlanCompilerConfig(
        goal_ref=goal.goal_id,
        goal_digest=goal_digest,
        claim_graph_digest=graph_digest,
        required_claim_refs=frozenset(claim.claim_id for claim in graph.claims),
        registered_node_types={
            PlanNodeType.BOUNDED_TASK.value: EXECUTOR_RELEASE,
            PlanNodeType.GOAL_VERIFICATION.value: "goal-verifier@sha256:" + "9" * 64,
        },
        registered_gate_refs={gate.gate_id: _gate_digest(gate) for gate in gates},
        registered_runtime_refs={RUNTIME_REF: RUNTIME_DIGEST},
        allowed_capabilities=frozenset({"filesystem.write"}),
        default_runtime_ref=RUNTIME_REF,
        max_fan_out=4,
    )


def _context_request(
    *,
    goal: GoalContract,
    graph: ClaimGraph,
    gates: tuple[GateDefinition, ...],
    config: PlanCompilerConfig,
    budget_limits: PlannerBudgetLimits,
    defects: tuple[DefectRecord, ...] = (),
) -> PlannerContextRequest:
    return PlannerContextRequest(
        run_id="RUN-dynamic-fixture",
        agent_release_digest=AGENT_RELEASE_DIGEST,
        goal_ref=goal.goal_id,
        goal_digest=config.goal_digest,
        policy_ref=POLICY_REF,
        policy_digest=POLICY_DIGEST,
        claim_refs=tuple(claim.claim_id for claim in graph.claims),
        registered_node_types=config.registered_node_types,
        registered_gate_refs={gate.gate_id: _gate_digest(gate) for gate in gates},
        registered_runtime_refs=config.registered_runtime_refs,
        budget_limits=budget_limits,
        defects=defects,
        token_budget=4096,
    )


def _limits() -> PlannerBudgetLimits:
    return PlannerBudgetLimits(
        max_plan_nodes=8,
        max_plan_depth=4,
        max_model_calls=40,
        max_tool_calls=40,
        max_spawned_nodes=0,
        max_repair_cycles=2,
        max_fan_out=4,
        max_wall_seconds=120,
        max_cost_usd=2.0,
    )


def _initial_evidence_records(
    graph: ClaimGraph,
    gates: tuple[GateDefinition, ...],
    workspace: Path,
) -> tuple[EvidenceV2, ...]:
    return (
        _evidence(
            "EVD-acceptance-order-current",
            ("CLAIM-goal-contract-input", "CLAIM-acceptance-before-plan"),
            "GATE-acceptance-contract",
            gates,
            "ART-acceptance-order",
            _digest("acceptance-order-current"),
            EvidenceResult.PASSED,
        ),
        _evidence(
            "EVD-resume-current",
            ("CLAIM-resume-operational",),
            "GATE-resume-check",
            gates,
            "ART-resume",
            _digest("resume-current"),
            EvidenceResult.PASSED,
        ),
        _evidence(
            "EVD-doc-health-initial",
            ("CLAIM-defect-repair-functional",),
            "GATE-doc-health-l1",
            gates,
            "ART-doc-health",
            _file_digest(workspace / "src" / "doc_health.py"),
            EvidenceResult.FAILED,
        ),
        _evidence(
            "EVD-security-denial-initial",
            ("CLAIM-security-denial",),
            "GATE-security-denial",
            gates,
            "ART-security-audit",
            _digest("security-denial-current"),
            EvidenceResult.PASSED,
        ),
    )


def _final_evidence_records(
    *,
    graph: ClaimGraph,
    gates: tuple[GateDefinition, ...],
    workspace: Path,
    reused_records: tuple[EvidenceV2, ...],
) -> tuple[EvidenceV2, ...]:
    doc_digest = _file_digest(workspace / "src" / "doc_health.py")
    repaired = _evidence(
        "EVD-doc-health-repaired",
        ("CLAIM-defect-repair-functional",),
        "GATE-doc-health-l1",
        gates,
        "ART-doc-health",
        doc_digest,
        EvidenceResult.PASSED,
        supersedes=("EVD-doc-health-initial",),
    )
    boundary = _evidence(
        "EVD-repair-boundary-current",
        ("CLAIM-repair-boundary-governance",),
        "GATE-repair-boundary",
        gates,
        "ART-doc-health",
        doc_digest,
        EvidenceResult.PASSED,
        dependencies=(DigestRef(ref=repaired.evidence_id, digest=repaired.fingerprint()),),
    )
    selective = _evidence(
        "EVD-selective-reverify-current",
        ("CLAIM-selective-reverification",),
        "GATE-selective-reverify",
        gates,
        "ART-selective-reverify",
        _digest("selective-reverify-current"),
        EvidenceResult.PASSED,
        dependencies=(DigestRef(ref=repaired.evidence_id, digest=repaired.fingerprint()),),
    )
    pre_goal = (*reused_records, repaired, boundary, selective)
    goal = _evidence(
        "EVD-goal-completion-final",
        ("CLAIM-goal-completion",),
        "GATE-goal-completion",
        gates,
        "ART-goal-completion",
        _digest("goal-completion-final"),
        EvidenceResult.PASSED,
        dependencies=tuple(DigestRef(ref=record.evidence_id, digest=record.fingerprint()) for record in pre_goal),
    )
    records = (*pre_goal, goal)
    required_claims = {claim.claim_id for claim in graph.claims if claim.required}
    covered_claims = {claim_ref for record in records for claim_ref in record.claim_refs}
    if covered_claims != required_claims:
        raise RuntimeError(f"final fixture evidence does not cover all required claims: {sorted(required_claims - covered_claims)}")
    return records


def _evidence(
    evidence_id: str,
    claim_refs: tuple[str, ...],
    gate_ref: str,
    gates: tuple[GateDefinition, ...],
    subject_ref: str,
    subject_digest: str,
    result: EvidenceResult,
    *,
    dependencies: tuple[DigestRef, ...] = (),
    supersedes: tuple[str, ...] = (),
) -> EvidenceV2:
    record = EvidenceV2(
        evidence_id=evidence_id,
        claim_refs=claim_refs,
        gate_ref=gate_ref,
        gate_definition_digest=_gate_digest(_gate_by_id(gates, gate_ref)),
        gate_run_id="GRUN-" + evidence_id.removeprefix("EVD-"),
        result=result,
        confidence="deterministic",
        subjects=(DigestRef(ref=subject_ref, digest=subject_digest),),
        dependencies=dependencies,
        environment=EvidenceEnvironment(
            runtime_profile_digest=RUNTIME_DIGEST,
            policy_digest=POLICY_DIGEST,
            verifier_release_digest=AGENT_RELEASE_DIGEST,
            test_definition_digest=_digest("dynamic-fixture-test-definition"),
        ),
        refs=(subject_ref,),
        supersedes=supersedes,
    )
    return replace(record, stored_fingerprint=record.fingerprint())


def _runtime_grants_for_node(plan: PlanIR, node: PlanNodeIR) -> tuple[RuntimeCapabilityGrant, ...]:
    issued = datetime.now(UTC)
    grants: list[RuntimeCapabilityGrant] = []
    for grant in node.capability_grants:
        suffix = _digest({"plan": plan.plan_id, "node": node.node_id, "capability": grant.capability}).removeprefix("sha256:")[:16]
        grants.append(
            RuntimeCapabilityGrant(
                grant_id=f"CGRANT-{suffix}",
                request_id=f"CREQ-{suffix}",
                plan_id=plan.plan_id,
                node_id=node.node_id,
                role="executor",
                capability=grant.capability,
                action=grant.capability,
                resources=grant.resources,
                scope=grant.resources,
                expires_at=issued.replace(year=issued.year + 1),
                issued_at=issued,
                issuer="fixture:manual-repair-runner",
                policy_decision_id=f"PDEC-{suffix}",
            )
        )
    return tuple(grants)


def _first_grant(request: NodeExecutionRequest) -> RuntimeCapabilityGrant:
    if not request.capability_grants:
        raise ValueError(f"fixture node requires a filesystem.write grant: {request.node.node_id}")
    return request.capability_grants[0]


def _gate_by_id(gates: tuple[GateDefinition, ...], gate_id: str) -> GateDefinition:
    for gate in gates:
        if gate.gate_id == gate_id:
            return gate
    raise KeyError(gate_id)


def _node_by_id(plan: PlanIR, node_id: str) -> PlanNodeIR:
    for node in plan.nodes:
        if node.node_id == node_id:
            return node
    raise KeyError(node_id)


def _gate_digest(gate: GateDefinition) -> str:
    return _digest(
        {
            "gateId": gate.gate_id,
            "version": gate.version,
            "level": gate.level,
            "evidenceKind": gate.evidence_kind,
            "verifierMode": gate.verifier_mode,
            "riskLevel": gate.risk_level.value,
        }
    )


def _claim_graph_payload(graph: ClaimGraph) -> dict[str, Any]:
    return {
        "goalRef": graph.goal_ref,
        "version": graph.version,
        "claims": [
            {
                "id": claim.claim_id,
                "type": claim.claim_type.value,
                "criterionRefs": list(claim.criterion_refs),
                "dependsOn": list(claim.depends_on),
                "riskLevel": claim.risk_level.value,
                "gateRefs": list(claim.gate_refs),
            }
            for claim in graph.claims
        ],
    }


def _reused_candidate_refs() -> set[str]:
    return {"EVD-acceptance-order-current", "EVD-resume-current", "EVD-security-denial-initial"}


def _evidence_summary(record: EvidenceV2) -> dict[str, Any]:
    return {
        "evidenceId": record.evidence_id,
        "claimRefs": list(record.claim_refs),
        "gateRef": record.gate_ref,
        "result": record.result.value,
        "fingerprint": record.fingerprint(),
        "storedFingerprint": record.stored_fingerprint,
        "subjects": [subject.to_fingerprint() for subject in record.subjects],
        "dependencies": [dependency.to_fingerprint() for dependency in record.dependencies],
        "supersedes": list(record.supersedes),
    }


def _completion_dict(result: CompletionGateResult) -> dict[str, Any]:
    return {
        "complete": result.complete,
        "missingClaimRefs": list(result.missing_claim_refs),
        "nonCurrentEvidenceRefs": list(result.non_current_evidence_refs),
        "uncoveredClaimRefs": list(result.uncovered_claim_refs),
        "openDefectRefs": list(result.open_defect_refs),
    }


def _acceptance_mapping() -> dict[str, list[str]]:
    return {
        "AC1_goal_contract_input": ["EVD-acceptance-order-current"],
        "AC2_claims_before_plan_ir": ["EVD-acceptance-order-current"],
        "AC3_planner_output_not_executed_before_admission": ["EVD-acceptance-order-current"],
        "AC4_defect_with_reproduction_and_boundary": ["EVD-doc-health-initial", "DEF-doc-staleness-l2"],
        "AC5_repair_only_allowed_paths": ["EVD-repair-boundary-current"],
        "AC6_selective_verification_and_reuse": ["EVD-selective-reverify-current"],
        "AC7_l2_rejects_stale_evidence": ["EVD-goal-completion-final"],
        "AC8_unauthorized_action_denied_audited": ["EVD-security-denial-initial"],
        "AC9_crash_resume_exercised": ["EVD-resume-current"],
        "AC10_independent_final_verifier": ["EVD-TASK-0031-review-pending"],
    }


def _usage_total(node_runs: tuple[Any, ...], key: str) -> float:
    total = 0.0
    for node in node_runs:
        value = dict(node.usage).get(key)
        if value is not None:
            total += float(value)
    return total


def _changed_files(before: Mapping[str, str], after: Mapping[str, str]) -> tuple[str, ...]:
    refs = set(before) | set(after)
    return tuple(sorted(ref for ref in refs if before.get(ref) != after.get(ref)))


def _file_digests(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        result[path.relative_to(root).as_posix()] = _file_digest(path)
    return result


def _tree_digest(root: Path) -> str:
    return _digest(_file_digests(root))


def _file_digest(path: Path) -> str:
    if not path.exists():
        return _digest({"missing": path.as_posix()})
    import hashlib

    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: Any) -> str:
    if isinstance(value, str):
        return canonical_fingerprint({"value": value})
    if isinstance(value, Mapping):
        return canonical_fingerprint(value)
    return canonical_fingerprint({"value": value})


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
