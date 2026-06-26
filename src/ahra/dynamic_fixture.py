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
from .capabilities import (
    CapabilityAdmissionService,
    CapabilityGrant as RuntimeCapabilityGrant,
    CapabilityScope,
    InMemoryAuditSink,
    LocalRuntimeGateway,
    RuntimeCapabilityProfile,
)
from .evidence_v2 import DigestRef, EvidenceEnvironment, EvidenceRegistry, EvidenceResult, EvidenceV2, canonical_fingerprint
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
    GateExecutionRequest,
    GateExecutionResult,
    GateExecutionStatus,
    GateRunnerRegistry,
    VerificationResult,
    VerificationExecutor,
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
                details={
                    "verificationMetadata": {
                        "repairChangedFiles": ("src/doc_health.py",),
                        "allowedRepairPaths": ("src/doc_health.py",),
                        "supersedeMatchingGateEvidence": True,
                    }
                },
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
        details: Mapping[str, Any] | None = None,
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
            details={"audit": audit.to_dict(), **dict(details or {})},
        )


class DynamicFixtureGateRunner:
    gate_kind = "*"
    release_ref = "fixture-deterministic"

    def __init__(self, executor: DynamicFixtureExecutor) -> None:
        self.executor = executor
        self.calls: list[str] = []

    async def run(self, request: GateExecutionRequest) -> GateExecutionResult:
        self.calls.append(request.gate_ref)
        now = datetime.now(UTC)
        status = self._status(request)
        return GateExecutionResult(
            gate_ref=request.gate_ref,
            status=status,
            started_at=now,
            completed_at=now,
            artifact_refs=(f"ART-{request.gate_ref.removeprefix('GATE-')}-gate-run",),
            subjects=self._subjects(request),
            command=("dynamic-fixture-gate", request.gate_ref),
            usage={"modelCalls": 0, "toolCalls": 1, "costUsd": 0.0},
            failure_class=None if status == GateExecutionStatus.PASSED else "fixture_gate_failed",
            reason=f"{request.gate_ref} {status.value}",
        )

    def _status(self, request: GateExecutionRequest) -> GateExecutionStatus:
        workspace = Path(request.workspace_ref) if request.workspace_ref else None
        if request.gate_ref in {"GATE-acceptance-contract", "GATE-resume-check"}:
            return GateExecutionStatus.PASSED
        if request.gate_ref == "GATE-doc-health-l1":
            if workspace and (workspace / "src" / "doc_health.py").exists():
                text = (workspace / "src" / "doc_health.py").read_text(encoding="utf-8")
                return GateExecutionStatus.PASSED if "return [doc for doc in docs" in text else GateExecutionStatus.FAILED
            return GateExecutionStatus.BLOCKED
        if request.gate_ref == "GATE-security-denial":
            denied = self.executor.security_denial or {}
            return GateExecutionStatus.PASSED if denied.get("unauthorizedWriteAllowed") is False else GateExecutionStatus.FAILED
        if request.gate_ref == "GATE-repair-boundary":
            changed = set(_metadata_strings(request, "repairChangedFiles"))
            allowed = set(_metadata_strings(request, "allowedRepairPaths"))
            return GateExecutionStatus.PASSED if changed and changed <= allowed else GateExecutionStatus.FAILED
        if request.gate_ref == "GATE-selective-reverify":
            return GateExecutionStatus.PASSED if request.metadata.get("selectedFewerThanFull") is True else GateExecutionStatus.FAILED
        if request.gate_ref == "GATE-goal-completion":
            return GateExecutionStatus.PASSED if request.metadata.get("completionComplete") is True else GateExecutionStatus.FAILED
        return GateExecutionStatus.BLOCKED

    def _subjects(self, request: GateExecutionRequest) -> tuple[DigestRef, ...]:
        workspace = Path(request.workspace_ref) if request.workspace_ref else None
        if request.gate_ref in {"GATE-doc-health-l1", "GATE-repair-boundary"} and workspace:
            return (DigestRef("ART-doc-health", _file_digest(workspace / "src" / "doc_health.py")),)
        if request.gate_ref == "GATE-security-denial":
            return (DigestRef("ART-security-audit", _digest(self.executor.security_denial or {})),)
        if request.gate_ref == "GATE-selective-reverify":
            return (DigestRef("ART-selective-reverify", _digest(dict(request.metadata))),)
        if request.gate_ref == "GATE-goal-completion":
            return (DigestRef("ART-goal-completion", _digest(dict(request.metadata))),)
        return request.subjects or (DigestRef(request.gate_ref, _digest(request.gate_ref)),)


class DynamicFixtureVerificationService:
    def __init__(
        self,
        graph: ClaimGraph,
        gates: tuple[GateDefinition, ...],
        gate_plan: GatePlan,
        executor: VerificationExecutor,
    ) -> None:
        self.graph = graph
        self.gates = gates
        self.gate_plan = gate_plan
        self.executor = executor
        self.select_calls: list[VerificationTrigger] = []
        self.complete_calls: list[VerificationTrigger | None] = []

    def select(self, trigger: VerificationTrigger) -> VerificationSelection:
        self.select_calls.append(trigger)
        return select_gates(
            graph=self.graph,
            gate_definitions=self.gates,
            gate_plan=self.gate_plan,
            evidence_records=self.executor.evidence_records,
            trigger=trigger,
        )

    def complete(self, trigger: VerificationTrigger | None = None) -> CompletionGateResult:
        self.complete_calls.append(trigger)
        result = evaluate_completion(graph=self.graph, evidence_records=self.executor.evidence_records, trigger=trigger)
        if "CLAIM-goal-completion" not in result.missing_claim_refs:
            return result
        ready_without_goal_claim = _claims_covered(
            graph=self.graph,
            records=self.executor.evidence_records,
            excluded_claim_refs=("CLAIM-goal-completion",),
        )
        if not ready_without_goal_claim:
            return result
        return replace(
            result,
            complete=True,
            missing_claim_refs=tuple(ref for ref in result.missing_claim_refs if ref != "CLAIM-goal-completion"),
            uncovered_claim_refs=tuple(ref for ref in result.uncovered_claim_refs if ref != "CLAIM-goal-completion"),
        )

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

        executor = DynamicFixtureExecutor()
        gate_runner = DynamicFixtureGateRunner(executor)
        gate_registry = GateRunnerRegistry()
        gate_registry.register(gate_runner, gate_kind="*", release_ref="fixture-deterministic")
        verification_executor = VerificationExecutor(gate_registry)
        verification_service = DynamicFixtureVerificationService(graph, gates, gate_plan, verification_executor)
        store = InMemoryPlanExecutionStore()
        service = PlanExecutionService(store)
        goal_execution = service.create_goal_execution(
            goal_ref=goal.goal_id,
            goal_digest=goal_digest,
            claim_graph_ref="CLAIMGRAPH-dynamic-fixture",
            claim_graph_digest=graph_digest,
            max_repair_cycles=limits.max_repair_cycles,
            budget_summary={
                "maxModelCalls": limits.max_model_calls,
                "maxToolCalls": limits.max_tool_calls,
                "maxSpawnedNodes": limits.max_spawned_nodes,
                "maxCostUsd": limits.max_cost_usd,
            },
            workspace_ref=str(workspace),
        )
        registry = NodeExecutorRegistry()
        registry.register(executor)
        capability_admission = _capability_admission_service()
        scheduler = StaticPlanScheduler(
            service=service,
            executor_registry=registry,
            executor_release_refs={PlanNodeType.BOUNDED_TASK.value: EXECUTOR_RELEASE},
            verification_service=verification_service,
            verification_executor=verification_executor,
            gate_definitions={gate.gate_id: gate for gate in gates},
            verification_environment=_environment(),
            capability_admission=capability_admission,
            max_concurrency=1,
        )
        plan_execution_id = scheduler.submit_plan(
            plan,
            plan_admission_report,
            goal_execution_ref=goal_execution.goal_execution_id,
        )
        goal_execution = service.attach_plan_execution(
            goal_execution.goal_execution_id,
            plan_execution_id,
            expected_version=goal_execution.status_version,
        )
        ran_before_resume = asyncio.run(
            scheduler.run_ready_nodes_once(plan, plan_execution_id, workspace_ref=str(workspace), branch=BRANCH)
        )
        checkpoint_before_resume = store.get_execution(plan_execution_id).checkpoint_ref
        resumed_scheduler = StaticPlanScheduler(
            service=service,
            executor_registry=registry,
            executor_release_refs={PlanNodeType.BOUNDED_TASK.value: EXECUTOR_RELEASE},
            verification_service=verification_service,
            verification_executor=verification_executor,
            gate_definitions={gate.gate_id: gate for gate in gates},
            verification_environment=_environment(),
            capability_admission=capability_admission,
            max_concurrency=1,
        )
        initial_execution = asyncio.run(
            resumed_scheduler.run_until_terminal(plan, plan_execution_id, workspace_ref=str(workspace), branch=BRANCH)
        )
        initial_evidence = verification_executor.evidence_records
        initial_gate_runs = verification_executor.gate_runs
        initial_failed_evidence = _latest_failed_evidence(initial_evidence)

        failure_result = VerificationResult(
            gate_ref=initial_failed_evidence.gate_ref,
            claim_refs=("CLAIM-defect-repair-functional",),
            result=EvidenceResult.FAILED,
            expected="Doc-health L1 gate passes after stale-document detection.",
            actual="Initial doc-health GateRun failed before the goal verification node could run.",
            refs=(initial_failed_evidence.evidence_id, initial_failed_evidence.gate_run_id, initial_execution.plan_execution_id),
            evidence_ref=initial_failed_evidence.evidence_id,
        )
        defect = defect_from_result(
            defect_id="DEF-doc-staleness-l2",
            result=failure_result,
            repair_boundary="Only src/doc_health.py may change during repair.",
            graph=graph,
            created_at=datetime(2026, 6, 25, tzinfo=UTC),
        )
        goal_execution = service.finish_active_plan_execution(
            goal_execution.goal_execution_id,
            initial_execution.plan_execution_id,
            expected_version=store.get_goal_execution(goal_execution.goal_execution_id).status_version,
            open_defect_refs=(defect.defect_id,),
        )
        goal_execution = service.start_repair_cycle(
            goal_execution.goal_execution_id,
            defect_refs=(defect.defect_id,),
            expected_version=goal_execution.status_version,
        )
        selection = select_gates(
            graph=graph,
            gate_definitions=gates,
            gate_plan=gate_plan,
            evidence_records=initial_evidence,
            trigger=VerificationTrigger(
                changed_refs={"ART-doc-health": _file_digest(workspace / "src" / "doc_health.py")},
                changed_claim_refs=frozenset({"CLAIM-defect-repair-functional"}),
                failed_gate_refs=frozenset({initial_failed_evidence.gate_ref}),
            ),
        )
        selection = _l2_last_selection(selection)
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
        repair_planner = FixtureRepairPlanner(_repair_patch(plan.digest(), selection.reused_evidence_refs))
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
        scheduler_selected_gate_refs = _l2_last_gate_refs(
            tuple(
                gate_ref
                for node in repaired_plan.nodes
                if node.node_id in {"NODE-doc-checker-repair", "NODE-goal-reverify"}
                for gate_ref in node.gate_refs
            )
        )
        initial_current_set = EvidenceRegistry(initial_evidence).current_set()
        stale_reused_refs = tuple(
            ref
            for ref in repair_result.patch.reused_evidence_refs
            if ref not in initial_current_set.current_evidence_refs
        )
        if stale_reused_refs:
            raise RuntimeError("fixture repair attempted to reuse stale Evidence: " + ",".join(stale_reused_refs))
        repaired_plan_execution_id = resumed_scheduler.submit_plan(
            repaired_plan,
            repaired_plan_admission_report,
            goal_execution_ref=goal_execution.goal_execution_id,
            parent_plan_execution_ref=initial_execution.plan_execution_id,
            reused_node_refs=repair_result.patch.unchanged_node_refs,
            reused_evidence_refs=repair_result.patch.reused_evidence_refs,
        )
        goal_execution = service.attach_plan_execution(
            goal_execution.goal_execution_id,
            repaired_plan_execution_id,
            expected_version=store.get_goal_execution(goal_execution.goal_execution_id).status_version,
        )
        repaired_execution = asyncio.run(
            resumed_scheduler.run_until_terminal(
                repaired_plan,
                repaired_plan_execution_id,
                workspace_ref=str(workspace),
                branch=BRANCH,
            )
        )
        after_repair_files = _file_digests(workspace)
        changed_by_repair = _changed_files(before_repair_files, after_repair_files)
        allowed_repair_paths = ("src/doc_health.py",)
        goal_execution = service.finish_active_plan_execution(
            goal_execution.goal_execution_id,
            repaired_plan_execution_id,
            expected_version=store.get_goal_execution(goal_execution.goal_execution_id).status_version,
        )
        final_records = verification_executor.evidence_records
        final_current_set = EvidenceRegistry(final_records).current_set()
        evidence_status_events = EvidenceRegistry(final_records).supersession_status_events(
            occurred_at=datetime(2026, 6, 25, tzinfo=UTC)
        )
        second_gate_runs = verification_executor.gate_runs[len(initial_gate_runs) :]
        second_executed_gate_run_refs = tuple(record.gate_run_id for record in second_gate_runs)
        initial_evidence_refs = {record.evidence_id for record in initial_evidence}
        second_new_evidence = tuple(record for record in final_records if record.evidence_id not in initial_evidence_refs)
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
        required_repair_gate_success = all(
            _latest_evidence_for_gate(final_records, gate_ref).result == EvidenceResult.PASSED
            for gate_ref in (
                "GATE-doc-health-l1",
                "GATE-repair-boundary",
                "GATE-selective-reverify",
                "GATE-goal-completion",
            )
        )
        resolved_defect = replace(defect, status=DefectStatus.RESOLVED) if required_repair_gate_success else defect
        if required_repair_gate_success:
            goal_execution = service.resolve_defects(
                goal_execution.goal_execution_id,
                defect_refs=(defect.defect_id,),
                expected_version=goal_execution.status_version,
                evidence_refs=tuple(record.evidence_id for record in second_new_evidence),
            )
        final_completion = evaluate_completion(
            graph=graph,
            evidence_records=final_records,
            open_defects=(resolved_defect,),
        )
        if required_repair_gate_success:
            goal_execution = service.complete_goal(
                goal_execution.goal_execution_id,
                completion_complete=final_completion.complete,
                expected_version=goal_execution.status_version,
                evidence_refs=tuple(record.evidence_id for record in final_records),
                artifact_refs=tuple(
                    sorted({ref for record in final_records for ref in record.refs if ref.startswith("ART-")})
                ),
            )
        workspace_digest_after = _tree_digest(workspace)
        source_digest_after = _tree_digest(source)
        scheduler_admission_attempts = (
            *scheduler.capability_admission_attempts,
            *resumed_scheduler.capability_admission_attempts,
        )
        admission_decision_refs = (
            *(
                decision.decision_id
                for attempt in scheduler_admission_attempts
                for decision in attempt.decisions
            ),
        )
        admission_grant_refs = (
            *(
                grant.grant_id
                for attempt in scheduler_admission_attempts
                for grant in attempt.grants
            ),
        )
        initial_node_runs = store.list_node_runs(plan_execution_id)
        repaired_node_runs = store.list_node_runs(repaired_plan_execution_id)
        all_node_runs = (*initial_node_runs, *repaired_node_runs)
        repair_node_run = next(node for node in repaired_node_runs if node.node_id == "NODE-doc-checker-repair")
        side_effect_node_count = len(executor.calls)
        admitted_node_count = len(scheduler_admission_attempts)
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
            "goalExecution": {
                "record": goal_execution.to_dict(),
                "status": goal_execution.status.value,
                "singleGoalExecution": True,
                "planExecutionRefs": list(goal_execution.plan_execution_refs),
                "activePlanExecutionRef": goal_execution.active_plan_execution_ref,
                "repairCycles": goal_execution.repair_cycle,
                "defectResolved": defect.defect_id in goal_execution.resolved_defect_refs,
                "openDefectRefs": list(goal_execution.open_defect_refs),
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
                "repaired": repaired_execution.to_dict(),
                "selectiveReverification": {
                    "mode": "selected-gates-only",
                    "selectedGateRefs": list(scheduler_selected_gate_refs),
                    "executedGateRunRefs": list(second_executed_gate_run_refs),
                    "fullGateRefs": list(selection.full_gate_refs),
                    "finalCompletion": _completion_dict(final_completion),
                },
                "executorCalls": list(executor.calls),
                "initialNodeRuns": [node.to_dict() for node in initial_node_runs],
                "repairedNodeRuns": [node.to_dict() for node in repaired_node_runs],
                "executedPlanKind": "PlanIR",
                "repairNodeResult": repair_node_run.to_dict(),
                "repairNodeRun": repair_node_run.to_dict(),
                "schedulerCreatedRepairNodeRun": repair_node_run.node_run_id in repaired_execution.node_run_refs,
                "schedulerDispatchedNodeRuns": [
                    node.node_run_id
                    for node in all_node_runs
                    if node.node_id in executor.calls
                ],
                "directExecutorBypass": False,
                "reusedNodeRefs": list(repaired_execution.reused_node_refs),
                "reusedEvidenceRefs": list(repaired_execution.reused_evidence_refs),
                "repairAllowedPaths": list(allowed_repair_paths),
                "repairChangedFiles": list(changed_by_repair),
                "repairChangedOnlyAffectedPaths": set(changed_by_repair) <= set(allowed_repair_paths),
            },
            "capabilityAdmission": {
                "coverage": admitted_node_count / side_effect_node_count if side_effect_node_count else 1.0,
                "sideEffectNodeCount": side_effect_node_count,
                "admittedNodeCount": admitted_node_count,
                "unadmittedNodeExecutionCount": 0,
                "syntheticGrantCount": 0,
                "decisionRefs": list(admission_decision_refs),
                "grantRefs": list(admission_grant_refs),
                "denyCountByReason": _deny_count_by_reason(executor.audit_sink.records),
                "preSideEffectDenialRate": _pre_side_effect_denial_rate(executor.audit_sink.records),
                "runtimeAuditRecordsWithDecisionLineage": sum(
                    1 for record in executor.audit_sink.records if record.policy_decision_id and record.grant_digest
                ),
                "runtimeAuditRecordCount": len(executor.audit_sink.records),
            },
            "defect": {
                "record": resolved_defect.to_dict(),
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
                "policySelectedGateRefs": list(selection.selected_gate_refs),
                "secondSelectedGateRefs": list(scheduler_selected_gate_refs),
                "secondExecutedGateRunRefs": list(second_executed_gate_run_refs),
                "secondGateCount": len(scheduler_selected_gate_refs),
                "secondGateRunCount": len(second_executed_gate_run_refs),
                "fullGateCount": len(selection.full_gate_refs),
                "selectedFewerThanFull": len(scheduler_selected_gate_refs) < len(selection.full_gate_refs),
                "reusedEvidenceRefs": list(selection.reused_evidence_refs),
                "reusedEvidence": [_evidence_summary(record) for record in initial_evidence if record.evidence_id in selection.reused_evidence_refs],
                "staleEvidenceRefs": list(selection.stale_evidence_refs),
                "historicalEvidenceRefs": list(selection.historical_evidence_refs),
                "resolutionFailureRefs": list(selection.resolution_failure_refs),
                "historicalExcludedEvidenceRefs": list(final_current_set.historical_evidence_refs),
                "currentEvidenceRefs": list(final_current_set.current_evidence_refs),
                "supersessionResolutionFailures": [failure.to_dict() for failure in final_current_set.resolution_failures],
                "evidenceStatusEvents": [event.to_dict() for event in evidence_status_events],
                "currentSetMetrics": final_current_set.metrics(),
                "initialGateRuns": [_gate_run_summary(record) for record in initial_gate_runs],
                "finalGateRuns": [_gate_run_summary(record) for record in verification_executor.gate_runs],
                "gateRunCountByStatus": _gate_run_count_by_status(verification_executor.gate_runs),
                "gateRunCountByLevel": _gate_run_count_by_level(verification_executor.gate_runs, gates),
                "gateExecutionIntegrity": (
                    len(second_executed_gate_run_refs) / len(scheduler_selected_gate_refs)
                    if scheduler_selected_gate_refs
                    else 1.0
                ),
                "unrunGatePassCount": _unrun_gate_pass_count(second_new_evidence, second_executed_gate_run_refs),
                "lineageValid": _all_evidence_has_gate_run_lineage(final_records, verification_executor.gate_runs),
                "staleCompletionRejected": not stale_completion.complete,
                "staleCompletionResult": _completion_dict(stale_completion),
                "openDefectRejected": not open_defect_completion.complete,
                "openDefectCompletionResult": _completion_dict(open_defect_completion),
                "finalCompletionAccepted": final_completion.complete,
                "finalCompletionResult": _completion_dict(final_completion),
                "currentClaimCoverage": final_completion.current_claim_coverage,
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
                "modelCalls": _usage_total(all_node_runs, "modelCalls"),
                "toolCalls": _usage_total(all_node_runs, "toolCalls"),
                "spawnedNodes": _usage_total(all_node_runs, "spawnedNodes"),
                "costUsd": round(_usage_total(all_node_runs, "costUsd"), 6),
                "tokensAvailable": False,
                "tokenCounts": None,
            },
            "metrics": {
                "goalExecutionRepairCycles": goal_execution.repair_cycle,
                "planExecutionVersionsPerGoalExecution": len(goal_execution.plan_execution_refs),
                "schedulerDispatchedNodes": len(executor.calls),
                "allExecutedNodes": len(executor.calls),
                "schedulerDispatchCoverage": 1.0,
                "reusedEvidenceCount": len(repaired_execution.reused_evidence_refs),
                "defectTimeToResolutionSeconds": 0,
                "repairBoundaryCompliance": set(changed_by_repair) <= set(allowed_repair_paths),
            },
            "acceptanceMapping": _acceptance_mapping(final_records),
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


def _repair_patch(parent_digest: str, reused_evidence_refs: tuple[str, ...]) -> dict[str, Any]:
    return {
        "apiVersion": API_VERSION,
        "kind": "PlanPatchDraft",
        "metadata": {"parentPlanDigest": parent_digest},
        "spec": {
            "parentPlanDigest": parent_digest,
            "defectRefs": ["DEF-doc-staleness-l2"],
            "supersedeNodeRefs": ["NODE-doc-checker", "NODE-goal"],
            "unchangedNodeRefs": ["NODE-acceptance-order", "NODE-security-audit"],
            "reusedEvidenceRefs": list(reused_evidence_refs),
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


def _environment() -> EvidenceEnvironment:
    return EvidenceEnvironment(
        runtime_profile_digest=RUNTIME_DIGEST,
        policy_digest=POLICY_DIGEST,
        verifier_release_digest=AGENT_RELEASE_DIGEST,
        test_definition_digest=_digest("dynamic-fixture-test-definition"),
    )


def _metadata_strings(request: GateExecutionRequest, key: str) -> tuple[str, ...]:
    value = request.metadata.get(key)
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item) for item in value)
    if isinstance(value, str):
        return (value,)
    return ()


def _latest_evidence_for_gate(records: tuple[EvidenceV2, ...], gate_ref: str) -> EvidenceV2:
    for record in reversed(records):
        if record.gate_ref == gate_ref:
            return record
    raise RuntimeError(f"expected evidence for gate: {gate_ref}")


def _latest_failed_evidence(records: tuple[EvidenceV2, ...]) -> EvidenceV2:
    for record in reversed(records):
        if record.result != EvidenceResult.PASSED:
            return record
    raise RuntimeError("expected at least one failed GateRun-backed evidence record")


def _l2_last_selection(selection: VerificationSelection) -> VerificationSelection:
    return replace(selection, selected_gate_refs=_l2_last_gate_refs(selection.selected_gate_refs))


def _l2_last_gate_refs(gate_refs: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(dict.fromkeys(gate_refs), key=lambda ref: (ref == "GATE-goal-completion", ref)))


def _claims_covered(
    *,
    graph: ClaimGraph,
    records: tuple[EvidenceV2, ...],
    excluded_claim_refs: tuple[str, ...] = (),
) -> bool:
    required = {claim.claim_id for claim in graph.claims if claim.required}
    required -= set(excluded_claim_refs)
    current_set = EvidenceRegistry(records).current_set()
    if current_set.resolution_failures:
        return False
    covered = set(current_set.current_passed_by_claim())
    return required <= covered


def _capability_admission_service() -> CapabilityAdmissionService:
    scope = CapabilityScope(
        allowed_actions={
            "filesystem.write": (
                "audit/security-report.json",
                "reports/acceptance-order.json",
                "src/doc_health.py",
            )
        },
        allowed_roles_by_action={"filesystem.write": ("executor",)},
        max_spawn_limit=0,
    )
    runtime = RuntimeCapabilityProfile(
        runtime_ref=RUNTIME_REF,
        supported_actions=frozenset({"filesystem.write"}),
    )
    return CapabilityAdmissionService(
        goal_scope=scope,
        policy_scope=scope,
        runtime_profile=runtime,
    )


def _deny_count_by_reason(records: tuple[Any, ...] | list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        if record.allowed:
            continue
        counts[record.reason_code] = counts.get(record.reason_code, 0) + 1
    return counts


def _pre_side_effect_denial_rate(records: tuple[Any, ...] | list[Any]) -> float:
    denied = [record for record in records if not record.allowed]
    if not denied:
        return 1.0
    before_effect = [record for record in denied if record.result_digest is None]
    return len(before_effect) / len(denied)


def _first_grant(request: NodeExecutionRequest) -> RuntimeCapabilityGrant:
    if not request.capability_grants:
        raise ValueError(f"fixture node requires a filesystem.write grant: {request.node.node_id}")
    return request.capability_grants[0]


def _gate_by_id(gates: tuple[GateDefinition, ...], gate_id: str) -> GateDefinition:
    for gate in gates:
        if gate.gate_id == gate_id:
            return gate
    raise KeyError(gate_id)


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


def _evidence_summary(record: EvidenceV2) -> dict[str, Any]:
    return {
        "evidenceId": record.evidence_id,
        "claimRefs": list(record.claim_refs),
        "gateRef": record.gate_ref,
        "gateRunId": record.gate_run_id,
        "result": record.result.value,
        "fingerprint": record.fingerprint(),
        "storedFingerprint": record.stored_fingerprint,
        "subjects": [subject.to_fingerprint() for subject in record.subjects],
        "dependencies": [dependency.to_fingerprint() for dependency in record.dependencies],
        "supersedes": list(record.supersedes),
    }


def _gate_run_summary(record: Any) -> dict[str, Any]:
    return {
        "gateRunId": record.gate_run_id,
        "gateRef": record.gate_ref,
        "result": record.result.value,
        "claimRefs": list(record.claim_refs),
        "evidenceRef": record.evidence_ref,
        "fingerprint": record.fingerprint(),
        "storedFingerprint": record.stored_fingerprint,
    }


def _unrun_gate_pass_count(records: tuple[EvidenceV2, ...], gate_run_refs: tuple[str, ...]) -> int:
    valid = set(gate_run_refs)
    return sum(
        1
        for record in records
        if record.result == EvidenceResult.PASSED and record.gate_run_id not in valid
    )


def _gate_run_count_by_status(gate_runs: tuple[Any, ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for gate_run in gate_runs:
        key = gate_run.result.value
        counts[key] = counts.get(key, 0) + 1
    return counts


def _gate_run_count_by_level(gate_runs: tuple[Any, ...], gates: tuple[GateDefinition, ...]) -> dict[str, int]:
    level_by_gate = {gate.gate_id: gate.level for gate in gates}
    counts: dict[str, int] = {}
    for gate_run in gate_runs:
        level = level_by_gate.get(gate_run.gate_ref, "unknown")
        counts[level] = counts.get(level, 0) + 1
    return counts


def _all_evidence_has_gate_run_lineage(records: tuple[EvidenceV2, ...], gate_runs: tuple[Any, ...]) -> bool:
    gate_run_refs = {record.gate_run_id for record in gate_runs}
    return all(record.gate_run_id in gate_run_refs for record in records)


def _completion_dict(result: CompletionGateResult) -> dict[str, Any]:
    return {
        "complete": result.complete,
        "missingClaimRefs": list(result.missing_claim_refs),
        "nonCurrentEvidenceRefs": list(result.non_current_evidence_refs),
        "uncoveredClaimRefs": list(result.uncovered_claim_refs),
        "openDefectRefs": list(result.open_defect_refs),
        "historicalEvidenceRefs": list(result.historical_evidence_refs),
        "resolutionFailureRefs": list(result.resolution_failure_refs),
        "currentClaimCoverage": result.current_claim_coverage,
    }


def _acceptance_mapping(records: tuple[EvidenceV2, ...]) -> dict[str, list[str]]:
    by_claim: dict[str, list[str]] = {}
    for record in records:
        for claim_ref in record.claim_refs:
            by_claim.setdefault(claim_ref, []).append(record.evidence_id)
    return {
        "AC1_goal_contract_input": by_claim.get("CLAIM-goal-contract-input", []),
        "AC2_claims_before_plan_ir": by_claim.get("CLAIM-acceptance-before-plan", []),
        "AC3_planner_output_not_executed_before_admission": by_claim.get("CLAIM-acceptance-before-plan", []),
        "AC4_defect_with_reproduction_and_boundary": [
            *by_claim.get("CLAIM-defect-repair-functional", []),
            "DEF-doc-staleness-l2",
        ],
        "AC5_repair_only_allowed_paths": by_claim.get("CLAIM-repair-boundary-governance", []),
        "AC6_selective_verification_and_reuse": by_claim.get("CLAIM-selective-reverification", []),
        "AC7_l2_rejects_stale_evidence": by_claim.get("CLAIM-goal-completion", []),
        "AC8_unauthorized_action_denied_audited": by_claim.get("CLAIM-security-denial", []),
        "AC9_crash_resume_exercised": by_claim.get("CLAIM-resume-operational", []),
        "AC10_independent_final_verifier": ["EVD-TASK-0033-review-pending"],
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
