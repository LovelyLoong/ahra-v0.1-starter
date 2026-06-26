from __future__ import annotations

import asyncio
import hashlib
import os
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Mapping

from .acceptance_contracts import Claim, ClaimGraph, ClaimType, GateDefinition, GatePlan, RiskLevel
from .evidence_v2 import (
    DigestRef,
    EvidenceInvalidationTrigger,
    EvidenceEnvironment,
    EvidenceRegistry,
    EvidenceResult,
    EvidenceV2,
    EvidenceValidityState,
    GateRunV2,
    canonical_fingerprint,
)


class GateLevel(StrEnum):
    L0 = "L0"
    L1 = "L1"
    L2 = "L2"


class DefectStatus(StrEnum):
    OPEN = "open"
    TRIAGED = "triaged"
    REPAIR_PLANNED = "repair_planned"
    REPAIRING = "repairing"
    REVERIFYING = "reverifying"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    REJECTED = "rejected"


class GateExecutionStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    ERROR = "error"
    TIMED_OUT = "timed_out"
    CANCELED = "canceled"

    @property
    def terminal(self) -> bool:
        return True

    def to_evidence_result(self) -> EvidenceResult:
        if self == GateExecutionStatus.PASSED:
            return EvidenceResult.PASSED
        if self == GateExecutionStatus.FAILED:
            return EvidenceResult.FAILED
        return EvidenceResult.BLOCKED


@dataclass(frozen=True, slots=True)
class GateExecutionRequest:
    goal_execution_id: str
    plan_execution_id: str
    node_run_id: str | None
    gate_ref: str
    gate_kind: str
    runner_release_ref: str
    gate_definition_digest: str
    claim_refs: tuple[str, ...]
    level: GateLevel
    evidence_kind: str
    subjects: tuple[DigestRef, ...]
    dependency_evidence: tuple[EvidenceV2, ...]
    environment: EvidenceEnvironment
    workspace_ref: str | None
    idempotency_key: str
    attempt: int = 1
    command: tuple[str, ...] = ()
    timeout_seconds: float | None = None
    mutation_allowed: bool = False
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GateExecutionResult:
    gate_ref: str
    status: GateExecutionStatus
    started_at: datetime
    completed_at: datetime
    artifact_refs: tuple[str, ...] = ()
    subjects: tuple[DigestRef, ...] = ()
    dependencies: tuple[DigestRef, ...] = ()
    command: tuple[str, ...] = ()
    usage: Mapping[str, object] = field(default_factory=dict)
    cost: Mapping[str, object] = field(default_factory=dict)
    failure_class: str | None = None
    reason: str = ""
    raw_output_ref: str | None = None


@dataclass(frozen=True, slots=True)
class VerificationExecutionContext:
    goal_execution_id: str
    plan_execution_id: str
    node_run_id: str | None = None
    gate_definitions: Mapping[str, GateDefinition] = field(default_factory=dict)
    gate_definition_digests: Mapping[str, str] = field(default_factory=dict)
    gate_claim_refs: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    subjects: tuple[DigestRef, ...] = ()
    dependency_evidence: tuple[EvidenceV2, ...] = ()
    environment: EvidenceEnvironment | None = None
    workspace_ref: str | None = None
    attempt: int = 1
    timeout_seconds: float | None = None
    mutation_allowed: bool = False
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class VerificationGateAttempt:
    gate_ref: str
    status: GateExecutionStatus
    level: GateLevel | None = None
    gate_run: GateRunV2 | None = None
    evidence: EvidenceV2 | None = None
    failure_class: str | None = None
    message: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "gateRef": self.gate_ref,
            "status": self.status.value,
            "level": self.level.value if self.level else None,
            "gateRunRef": self.gate_run.gate_run_id if self.gate_run else None,
            "evidenceRef": self.evidence.evidence_id if self.evidence else None,
            "failureClass": self.failure_class,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class VerificationExecutionReport:
    selection: VerificationSelection
    attempts: tuple[VerificationGateAttempt, ...]
    reused_evidence_refs: tuple[str, ...]
    duplicate_idempotency_keys: tuple[str, ...] = ()

    @property
    def gate_runs(self) -> tuple[GateRunV2, ...]:
        return tuple(attempt.gate_run for attempt in self.attempts if attempt.gate_run is not None)

    @property
    def evidence_records(self) -> tuple[EvidenceV2, ...]:
        return tuple(attempt.evidence for attempt in self.attempts if attempt.evidence is not None)

    @property
    def executed_gate_run_refs(self) -> tuple[str, ...]:
        return tuple(gate_run.gate_run_id for gate_run in self.gate_runs)

    @property
    def failed_gate_refs(self) -> tuple[str, ...]:
        return tuple(
            attempt.gate_ref
            for attempt in self.attempts
            if attempt.status != GateExecutionStatus.PASSED
        )

    @property
    def missing_runner_gate_refs(self) -> tuple[str, ...]:
        return tuple(
            attempt.gate_ref
            for attempt in self.attempts
            if attempt.failure_class == "missing_gate_runner"
        )

    @property
    def passed(self) -> bool:
        expected_count = len(self.selection.selected_gate_refs)
        if not self.selection.selected_gate_refs:
            return True
        if self.duplicate_idempotency_keys:
            return False
        if len(self.gate_runs) != expected_count:
            return False
        return all(attempt.status == GateExecutionStatus.PASSED for attempt in self.attempts)

    @property
    def gate_execution_integrity(self) -> float:
        selected = len(self.selection.selected_gate_refs)
        if selected == 0:
            return 1.0
        return len(self.gate_runs) / selected

    @property
    def unrun_gate_pass_count(self) -> int:
        gate_run_refs = {gate_run.gate_run_id for gate_run in self.gate_runs}
        return sum(
            1
            for evidence in self.evidence_records
            if evidence.result == EvidenceResult.PASSED and evidence.gate_run_id not in gate_run_refs
        )

    def to_dict(self) -> dict[str, object]:
        status_counts: dict[str, int] = {}
        level_counts: dict[str, int] = {}
        gate_counts: dict[str, int] = {}
        for attempt in self.attempts:
            status_counts[attempt.status.value] = status_counts.get(attempt.status.value, 0) + 1
            if attempt.gate_run and attempt.level:
                level_counts[attempt.level.value] = level_counts.get(attempt.level.value, 0) + 1
            if attempt.gate_run:
                gate_counts[attempt.gate_run.gate_ref] = gate_counts.get(attempt.gate_run.gate_ref, 0) + 1
        evidence_with_lineage = sum(1 for evidence in self.evidence_records if evidence.gate_run_id)
        return {
            "selection": self.selection.to_dict(),
            "selectedGateRefs": list(self.selection.selected_gate_refs),
            "executedGateRunRefs": list(self.executed_gate_run_refs),
            "reusedEvidenceRefs": list(self.reused_evidence_refs),
            "attempts": [attempt.to_dict() for attempt in self.attempts],
            "passed": self.passed,
            "metrics": {
                "gateExecutionIntegrity": self.gate_execution_integrity,
                "unrunGatePassCount": self.unrun_gate_pass_count,
                "gateRunCountByStatus": status_counts,
                "gateRunCountByLevel": level_counts,
                "gateRunCountByGate": gate_counts,
                "evidenceWithValidGateRunLineage": evidence_with_lineage,
                "newEvidenceCount": len(self.evidence_records),
            },
            "duplicateIdempotencyKeys": list(self.duplicate_idempotency_keys),
        }


class GateRunnerRegistry:
    def __init__(self) -> None:
        self._runners: dict[tuple[str, str], object] = {}

    def register(self, runner: object, *, gate_kind: str | None = None, release_ref: str | None = None) -> None:
        kind = str(gate_kind or getattr(runner, "gate_kind", ""))
        release = str(release_ref or getattr(runner, "release_ref", ""))
        if not kind or not release:
            raise ValueError("gate runner registration requires gate_kind and release_ref")
        key = (kind, release)
        if key in self._runners:
            raise ValueError(f"duplicate gate runner: {kind}@{release}")
        self._runners[key] = runner

    def resolve(self, gate_kind: str, release_ref: str) -> object:
        keys = (
            (gate_kind, release_ref),
            (gate_kind, "*"),
            ("*", release_ref),
            ("*", "*"),
        )
        for key in keys:
            if key in self._runners:
                return self._runners[key]
        raise KeyError(f"no gate runner for {gate_kind}@{release_ref}")


class DeterministicGateRunner:
    gate_kind = "*"
    release_ref = "*"

    def __init__(
        self,
        *,
        outcomes: Mapping[str, GateExecutionStatus] | None = None,
        delay_seconds: float = 0.0,
        mutate_workspace: bool = False,
    ) -> None:
        self.outcomes = dict(outcomes or {})
        self.delay_seconds = delay_seconds
        self.mutate_workspace = mutate_workspace
        self.calls: list[GateExecutionRequest] = []

    async def run(self, request: GateExecutionRequest) -> GateExecutionResult:
        self.calls.append(request)
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if self.mutate_workspace and request.workspace_ref:
            Path(request.workspace_ref, ".ahra-gate-runner-mutation").write_text("mutated\n", encoding="utf-8")
        now = datetime.now(UTC)
        status = self.outcomes.get(request.gate_ref, GateExecutionStatus.PASSED)
        return GateExecutionResult(
            gate_ref=request.gate_ref,
            status=status,
            started_at=now,
            completed_at=now,
            artifact_refs=(f"ART-{request.gate_ref.removeprefix('GATE-')}-gate-run",),
            subjects=request.subjects,
            command=("deterministic-gate-runner", request.gate_ref),
            usage={"modelCalls": 0, "toolCalls": 1, "costUsd": 0.0},
            failure_class=None if status == GateExecutionStatus.PASSED else "deterministic_gate_failed",
            reason="deterministic gate passed" if status == GateExecutionStatus.PASSED else "deterministic gate failed",
        )


class VerificationExecutor:
    def __init__(self, registry: GateRunnerRegistry) -> None:
        self.registry = registry
        self._gate_runs: list[GateRunV2] = []
        self._evidence_records: list[EvidenceV2] = []
        self._used_idempotency_keys: set[str] = set()

    @property
    def gate_runs(self) -> tuple[GateRunV2, ...]:
        return tuple(self._gate_runs)

    @property
    def evidence_records(self) -> tuple[EvidenceV2, ...]:
        return tuple(self._evidence_records)

    async def execute_selection(
        self,
        selection: VerificationSelection,
        context: VerificationExecutionContext,
    ) -> VerificationExecutionReport:
        attempts: list[VerificationGateAttempt] = []
        seen_keys: set[str] = set()
        duplicate_keys: set[str] = set()
        for gate_ref in selection.selected_gate_refs:
            request = self._request_for_gate(selection, context, gate_ref)
            if request.idempotency_key in seen_keys or request.idempotency_key in self._used_idempotency_keys:
                duplicate_keys.add(request.idempotency_key)
                attempts.append(
                    VerificationGateAttempt(
                        gate_ref=gate_ref,
                        status=GateExecutionStatus.BLOCKED,
                        level=request.level,
                        failure_class="duplicate_idempotency_key",
                        message=f"duplicate gate execution idempotency key: {request.idempotency_key}",
                    )
                )
                continue
            seen_keys.add(request.idempotency_key)
            attempt = await self._execute_request(request)
            attempts.append(attempt)
        self._used_idempotency_keys.update(seen_keys)
        return VerificationExecutionReport(
            selection=selection,
            attempts=tuple(attempts),
            reused_evidence_refs=selection.reused_evidence_refs,
            duplicate_idempotency_keys=tuple(sorted(duplicate_keys)),
        )

    def _request_for_gate(
        self,
        selection: VerificationSelection,
        context: VerificationExecutionContext,
        gate_ref: str,
    ) -> GateExecutionRequest:
        definition = context.gate_definitions.get(gate_ref)
        if definition:
            level = GateLevel(definition.level)
            evidence_kind = definition.evidence_kind
            gate_kind = definition.evidence_kind
            release_ref = definition.verifier_mode
            gate_definition_digest = context.gate_definition_digests.get(gate_ref) or _gate_definition_digest(definition)
        else:
            level = GateLevel.L2 if "goal" in gate_ref.casefold() else GateLevel.L0
            evidence_kind = "deterministic_gate"
            gate_kind = gate_ref
            release_ref = "*"
            gate_definition_digest = context.gate_definition_digests.get(gate_ref, _synthetic_digest("gate", gate_ref))
        claim_refs = context.gate_claim_refs.get(gate_ref)
        if claim_refs is None:
            metadata_claim_refs = context.metadata.get("claimRefs", ())
            if isinstance(metadata_claim_refs, (tuple, list, set)):
                claim_refs = tuple(sorted(str(item) for item in metadata_claim_refs))
            else:
                claim_refs = ()
        if not claim_refs:
            claim_refs = selection.affected_claim_refs
        environment = context.environment or EvidenceEnvironment(
            runtime_profile_digest=_synthetic_digest("runtime", context.plan_execution_id),
            policy_digest=_synthetic_digest("policy", context.goal_execution_id),
            verifier_release_digest=_synthetic_digest("verifier", release_ref),
            test_definition_digest=_synthetic_digest("test", gate_ref),
        )
        return GateExecutionRequest(
            goal_execution_id=context.goal_execution_id,
            plan_execution_id=context.plan_execution_id,
            node_run_id=context.node_run_id,
            gate_ref=gate_ref,
            gate_kind=gate_kind,
            runner_release_ref=release_ref,
            gate_definition_digest=gate_definition_digest,
            claim_refs=tuple(sorted(claim_refs)),
            level=level,
            evidence_kind=evidence_kind,
            subjects=context.subjects,
            dependency_evidence=context.dependency_evidence,
            environment=environment,
            workspace_ref=context.workspace_ref,
            idempotency_key=_gate_idempotency_key(context, gate_ref, gate_definition_digest),
            attempt=context.attempt,
            timeout_seconds=context.timeout_seconds,
            mutation_allowed=context.mutation_allowed,
            metadata=context.metadata,
        )

    async def _execute_request(self, request: GateExecutionRequest) -> VerificationGateAttempt:
        try:
            runner = self.registry.resolve(request.gate_kind, request.runner_release_ref)
        except KeyError as exc:
            return VerificationGateAttempt(
                gate_ref=request.gate_ref,
                status=GateExecutionStatus.BLOCKED,
                level=request.level,
                failure_class="missing_gate_runner",
                message=str(exc),
            )
        before_digest = _workspace_digest(request.workspace_ref)
        try:
            run_result = runner.run(request)  # type: ignore[attr-defined]
            if request.timeout_seconds:
                result = await asyncio.wait_for(run_result, timeout=request.timeout_seconds)
            else:
                result = await run_result
            if not isinstance(result, GateExecutionResult):
                return self._attempt_from_structured_failure(
                    request,
                    status=GateExecutionStatus.BLOCKED,
                    failure_class="malformed_gate_result",
                    message="GateRunner returned a non-GateExecutionResult value.",
                )
        except TimeoutError:
            return self._attempt_from_structured_failure(
                request,
                status=GateExecutionStatus.TIMED_OUT,
                failure_class="runner_timeout",
                message="GateRunner timed out.",
            )
        except Exception as exc:
            return self._attempt_from_structured_failure(
                request,
                status=GateExecutionStatus.ERROR,
                failure_class="runner_exception",
                message=str(exc),
            )
        after_digest = _workspace_digest(request.workspace_ref)
        if before_digest and after_digest and before_digest != after_digest and not request.mutation_allowed:
            result = GateExecutionResult(
                gate_ref=request.gate_ref,
                status=GateExecutionStatus.ERROR,
                started_at=result.started_at,
                completed_at=result.completed_at,
                artifact_refs=result.artifact_refs,
                subjects=result.subjects,
                dependencies=result.dependencies,
                command=result.command,
                usage=result.usage,
                cost=result.cost,
                failure_class="unexpected_workspace_mutation",
                reason="GateRunner mutated the governed workspace without an isolated mutation contract.",
                raw_output_ref=result.raw_output_ref,
            )
        return self._attempt_from_result(request, result)

    def _attempt_from_structured_failure(
        self,
        request: GateExecutionRequest,
        *,
        status: GateExecutionStatus,
        failure_class: str,
        message: str,
    ) -> VerificationGateAttempt:
        now = datetime.now(UTC)
        result = GateExecutionResult(
            gate_ref=request.gate_ref,
            status=status,
            started_at=now,
            completed_at=now,
            failure_class=failure_class,
            reason=message,
        )
        return self._attempt_from_result(request, result)

    def _attempt_from_result(
        self,
        request: GateExecutionRequest,
        result: GateExecutionResult,
    ) -> VerificationGateAttempt:
        if result.gate_ref != request.gate_ref:
            result = GateExecutionResult(
                gate_ref=request.gate_ref,
                status=GateExecutionStatus.BLOCKED,
                started_at=result.started_at,
                completed_at=result.completed_at,
                failure_class="malformed_gate_result",
                reason="GateExecutionResult gate_ref does not match request.",
            )
        gate_run, evidence = _gate_run_and_evidence_from_result(request, result)
        if request.metadata.get("supersedeMatchingGateEvidence") is True:
            superseded_refs = tuple(
                record.evidence_id
                for record in self._evidence_records
                if record.gate_ref == evidence.gate_ref
            )
            if superseded_refs:
                evidence = replace(evidence, supersedes=superseded_refs)
                evidence = replace(evidence, stored_fingerprint=evidence.fingerprint())
        self._gate_runs.append(gate_run)
        self._evidence_records.append(evidence)
        return VerificationGateAttempt(
            gate_ref=request.gate_ref,
            status=result.status,
            level=request.level,
            gate_run=gate_run,
            evidence=evidence,
            failure_class=result.failure_class,
            message=result.reason,
        )


@dataclass(frozen=True, slots=True)
class VerificationTrigger:
    changed_refs: Mapping[str, str] = field(default_factory=dict)
    failed_gate_refs: frozenset[str] = frozenset()
    changed_claim_refs: frozenset[str] = frozenset()
    changed_gate_refs: frozenset[str] = frozenset()
    policy_digest: str | None = None
    runtime_profile_digest: str | None = None
    test_definition_digest: str | None = None
    verifier_release_digest: str | None = None
    now: datetime | None = None
    revoked_evidence_refs: frozenset[str] = frozenset()
    contradicted_evidence_refs: frozenset[str] = frozenset()

    def to_evidence_trigger(self) -> EvidenceInvalidationTrigger:
        return EvidenceInvalidationTrigger(
            changed_refs=self.changed_refs,
            changed_claim_refs=self.changed_claim_refs,
            changed_gate_refs=self.changed_gate_refs,
            policy_digest=self.policy_digest,
            runtime_profile_digest=self.runtime_profile_digest,
            test_definition_digest=self.test_definition_digest,
            verifier_release_digest=self.verifier_release_digest,
            now=self.now,
            revoked_evidence_refs=self.revoked_evidence_refs,
            contradicted_evidence_refs=self.contradicted_evidence_refs,
        )


@dataclass(frozen=True, slots=True)
class VerificationPolicy:
    mandatory_gate_refs: frozenset[str] = frozenset()
    mandatory_claim_types: frozenset[ClaimType] = frozenset({ClaimType.SECURITY, ClaimType.GOVERNANCE})
    integration_boundary_level: GateLevel = GateLevel.L1


@dataclass(frozen=True, slots=True)
class VerificationGate:
    gate_ref: str
    level: GateLevel
    claim_refs: tuple[str, ...]
    evidence_kind: str
    risk_level: RiskLevel

    @classmethod
    def from_definition(cls, definition: GateDefinition, claim_refs: tuple[str, ...]) -> "VerificationGate":
        level = GateLevel(definition.level)
        gate_cls: type[VerificationGate]
        if level == GateLevel.L0:
            gate_cls = L0Gate
        elif level == GateLevel.L1:
            gate_cls = L1Gate
        else:
            gate_cls = L2Gate
        return gate_cls(
            gate_ref=definition.gate_id,
            level=level,
            claim_refs=tuple(sorted(claim_refs)),
            evidence_kind=definition.evidence_kind,
            risk_level=definition.risk_level,
        )


class L0Gate(VerificationGate):
    pass


class L1Gate(VerificationGate):
    pass


class L2Gate(VerificationGate):
    pass


@dataclass(frozen=True, slots=True)
class VerificationSelection:
    selected_gate_refs: tuple[str, ...]
    full_gate_refs: tuple[str, ...]
    affected_claim_refs: tuple[str, ...]
    reused_evidence_refs: tuple[str, ...]
    stale_evidence_refs: tuple[str, ...]
    rationale: tuple[str, ...]
    historical_evidence_refs: tuple[str, ...] = ()
    resolution_failure_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "selectedGateRefs": list(self.selected_gate_refs),
            "fullGateRefs": list(self.full_gate_refs),
            "affectedClaimRefs": list(self.affected_claim_refs),
            "reusedEvidenceRefs": list(self.reused_evidence_refs),
            "staleEvidenceRefs": list(self.stale_evidence_refs),
            "historicalEvidenceRefs": list(self.historical_evidence_refs),
            "resolutionFailureRefs": list(self.resolution_failure_refs),
            "rationale": list(self.rationale),
        }


@dataclass(frozen=True, slots=True)
class VerificationResult:
    gate_ref: str
    claim_refs: tuple[str, ...]
    result: EvidenceResult
    expected: str
    actual: str
    refs: tuple[str, ...] = ()
    evidence_ref: str | None = None


@dataclass(frozen=True, slots=True)
class DefectRecord:
    defect_id: str
    claim_ref: str
    gate_ref: str
    expected: str
    actual: str
    refs: tuple[str, ...]
    repair_boundary: str
    direct_claim_refs: tuple[str, ...] = ()
    affected_claim_refs: tuple[str, ...] = ()
    status: DefectStatus = DefectStatus.OPEN
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        direct = tuple(sorted(set(self.direct_claim_refs or (self.claim_ref,))))
        affected = tuple(sorted(set(self.affected_claim_refs or direct)))
        if not direct:
            raise ValueError("DefectRecord requires at least one direct claim")
        if not affected:
            raise ValueError("DefectRecord requires at least one affected claim")
        if not set(direct) <= set(affected):
            affected = tuple(sorted(set((*affected, *direct))))
        object.__setattr__(self, "direct_claim_refs", direct)
        object.__setattr__(self, "affected_claim_refs", affected)
        object.__setattr__(self, "claim_ref", direct[0])

    def to_dict(self) -> dict[str, object]:
        return {
            "apiVersion": "ahra.dev/v1alpha1",
            "kind": "DefectRecord",
            "metadata": {
                "defectId": self.defect_id,
                "createdAt": self.created_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            },
            "spec": {
                "claimRef": self.claim_ref,
                "directClaimRefs": list(self.direct_claim_refs),
                "affectedClaimRefs": list(self.affected_claim_refs),
                "gateRef": self.gate_ref,
                "expected": self.expected,
                "actual": self.actual,
                "refs": list(self.refs),
                "repairBoundary": self.repair_boundary,
                "status": self.status.value,
            },
        }


@dataclass(frozen=True, slots=True)
class CompletionGateResult:
    complete: bool
    missing_claim_refs: tuple[str, ...] = ()
    non_current_evidence_refs: tuple[str, ...] = ()
    uncovered_claim_refs: tuple[str, ...] = ()
    open_defect_refs: tuple[str, ...] = ()
    historical_evidence_refs: tuple[str, ...] = ()
    resolution_failure_refs: tuple[str, ...] = ()
    current_claim_coverage: float = 0.0


def select_gates(
    *,
    graph: ClaimGraph,
    gate_definitions: tuple[GateDefinition, ...],
    gate_plan: GatePlan,
    evidence_records: tuple[EvidenceV2, ...],
    trigger: VerificationTrigger,
    policy: VerificationPolicy | None = None,
) -> VerificationSelection:
    policy = policy or VerificationPolicy()
    claims_by_id = {claim.claim_id: claim for claim in graph.claims}
    gates = _materialize_gates(gate_definitions, gate_plan)
    gate_by_ref = {gate.gate_ref: gate for gate in gates}
    current_set = EvidenceRegistry(evidence_records).current_set(trigger.to_evidence_trigger())

    direct_claims = set(trigger.changed_claim_refs)
    stale_evidence_refs: set[str] = set()
    reused_evidence_refs: set[str] = set()
    rationale: set[str] = set()
    for failure in current_set.resolution_failures:
        rationale.add(f"evidence_resolution_failure:{failure.code}:{failure.evidence_ref}")
        record = next((item for item in evidence_records if item.evidence_id == failure.evidence_ref), None)
        if record:
            direct_claims.update(record.claim_refs)
    for evidence in current_set.current_records:
        inspection = current_set.inspections[evidence.evidence_id]
        if inspection.current and evidence.result == EvidenceResult.PASSED and _stored_fingerprint_matches(evidence):
            reused_evidence_refs.add(evidence.evidence_id)
        else:
            stale_evidence_refs.add(evidence.evidence_id)
            direct_claims.update(evidence.claim_refs)
            if inspection.current and evidence.result == EvidenceResult.PASSED:
                rationale.add(f"fingerprint_not_matched:{evidence.evidence_id}")

    affected_claims = _reverse_dependency_closure(graph, direct_claims)
    selected_gate_refs: set[str] = set()

    for claim_ref in sorted(affected_claims):
        claim = claims_by_id.get(claim_ref)
        if not claim:
            continue
        for gate_ref in claim.gate_refs:
            if gate_ref in gate_by_ref:
                selected_gate_refs.add(gate_ref)
                rationale.add(f"affected_claim:{claim_ref}->{gate_ref}")

    for gate_ref in sorted(trigger.failed_gate_refs):
        if gate_ref in gate_by_ref:
            selected_gate_refs.add(gate_ref)
            rationale.add(f"failed_gate:{gate_ref}")

    for gate in gates:
        if gate.level == policy.integration_boundary_level and set(gate.claim_refs) & affected_claims:
            selected_gate_refs.add(gate.gate_ref)
            rationale.add(f"integration_boundary:{gate.gate_ref}")

    for gate_ref in sorted(policy.mandatory_gate_refs):
        if gate_ref in gate_by_ref:
            selected_gate_refs.add(gate_ref)
            rationale.add(f"mandatory_policy_gate:{gate_ref}")

    for claim in graph.claims:
        if claim.claim_type in policy.mandatory_claim_types and claim.required:
            for gate_ref in claim.gate_refs:
                if gate_ref in gate_by_ref:
                    selected_gate_refs.add(gate_ref)
                    rationale.add(f"mandatory_safety_claim:{claim.claim_id}->{gate_ref}")

    return VerificationSelection(
        selected_gate_refs=tuple(sorted(selected_gate_refs)),
        full_gate_refs=tuple(sorted(gate.gate_ref for gate in gates)),
        affected_claim_refs=tuple(sorted(affected_claims)),
        reused_evidence_refs=tuple(sorted(reused_evidence_refs - stale_evidence_refs)),
        stale_evidence_refs=tuple(sorted(stale_evidence_refs)),
        historical_evidence_refs=current_set.historical_evidence_refs,
        resolution_failure_refs=current_set.resolution_failure_refs,
        rationale=tuple(sorted(rationale)),
    )


def evaluate_completion(
    *,
    graph: ClaimGraph,
    evidence_records: tuple[EvidenceV2, ...],
    trigger: VerificationTrigger | None = None,
    open_defects: tuple[DefectRecord, ...] = (),
) -> CompletionGateResult:
    trigger = trigger or VerificationTrigger()
    current_set = EvidenceRegistry(evidence_records).current_set(trigger.to_evidence_trigger())
    current_by_claim: dict[str, list[EvidenceV2]] = {}
    for evidence in current_set.current_records:
        for claim_ref in evidence.claim_refs:
            current_by_claim.setdefault(claim_ref, []).append(evidence)

    missing: list[str] = []
    non_current: list[str] = []
    uncovered: list[str] = []
    covered_claim_count = 0
    required_claim_count = 0
    for claim in graph.claims:
        if not claim.required:
            continue
        required_claim_count += 1
        records = current_by_claim.get(claim.claim_id, [])
        if not records:
            missing.append(claim.claim_id)
            continue
        current_passed = False
        for record in records:
            inspection = current_set.inspections[record.evidence_id]
            if inspection.current and record.result == EvidenceResult.PASSED and _stored_fingerprint_matches(record):
                current_passed = True
            else:
                non_current.append(record.evidence_id)
        if not current_passed:
            uncovered.append(claim.claim_id)
        else:
            covered_claim_count += 1

    open_defect_refs = tuple(sorted(defect.defect_id for defect in open_defects if defect.status != DefectStatus.RESOLVED))
    resolution_failure_refs = current_set.resolution_failure_refs
    return CompletionGateResult(
        complete=not missing and not non_current and not uncovered and not open_defect_refs and not resolution_failure_refs,
        missing_claim_refs=tuple(sorted(missing)),
        non_current_evidence_refs=tuple(sorted(set(non_current))),
        uncovered_claim_refs=tuple(sorted(uncovered)),
        open_defect_refs=open_defect_refs,
        historical_evidence_refs=current_set.historical_evidence_refs,
        resolution_failure_refs=resolution_failure_refs,
        current_claim_coverage=covered_claim_count / required_claim_count if required_claim_count else 1.0,
    )


def validate_gate_run_lineage(
    evidence_records: tuple[EvidenceV2, ...],
    gate_runs: tuple[GateRunV2, ...],
) -> tuple[str, ...]:
    gate_run_refs = {gate_run.gate_run_id for gate_run in gate_runs}
    return tuple(
        sorted(
            evidence.evidence_id
            for evidence in evidence_records
            if evidence.gate_run_id not in gate_run_refs
        )
    )


def defect_from_result(
    *,
    defect_id: str,
    result: VerificationResult,
    repair_boundary: str,
    graph: ClaimGraph | None = None,
    affected_claim_refs: tuple[str, ...] | None = None,
    created_at: datetime | None = None,
) -> DefectRecord:
    if result.result == EvidenceResult.PASSED:
        raise ValueError("passed gate result does not create a defect")
    if not result.claim_refs:
        raise ValueError("failed gate result must name at least one claim")
    direct_claim_refs = tuple(sorted(set(result.claim_refs)))
    if affected_claim_refs is None:
        affected_claim_refs = tuple(sorted(_reverse_dependency_closure(graph, set(direct_claim_refs)))) if graph else direct_claim_refs
    return DefectRecord(
        defect_id=defect_id,
        claim_ref=direct_claim_refs[0],
        gate_ref=result.gate_ref,
        expected=result.expected,
        actual=result.actual,
        refs=result.refs,
        repair_boundary=repair_boundary,
        direct_claim_refs=direct_claim_refs,
        affected_claim_refs=affected_claim_refs,
        created_at=created_at or datetime.now(UTC),
    )


def _materialize_gates(
    gate_definitions: tuple[GateDefinition, ...],
    gate_plan: GatePlan,
) -> tuple[VerificationGate, ...]:
    definition_by_id = {definition.gate_id: definition for definition in gate_definitions}
    gates: list[VerificationGate] = []
    for entry in sorted(gate_plan.gates, key=lambda item: item.gate_ref):
        definition = definition_by_id.get(entry.gate_ref)
        if definition is None:
            continue
        gates.append(VerificationGate.from_definition(definition, entry.claim_refs))
    return tuple(gates)


def _stored_fingerprint_matches(evidence: EvidenceV2) -> bool:
    return evidence.stored_fingerprint is not None and evidence.stored_fingerprint == evidence.fingerprint()


def _reverse_dependency_closure(graph: ClaimGraph, direct_claim_refs: set[str]) -> set[str]:
    reverse: dict[str, set[str]] = {}
    for claim in graph.claims:
        for dependency in claim.depends_on:
            reverse.setdefault(dependency, set()).add(claim.claim_id)
    affected = set(direct_claim_refs)
    pending = list(sorted(direct_claim_refs))
    while pending:
        claim_ref = pending.pop(0)
        for dependant in sorted(reverse.get(claim_ref, ())):
            if dependant not in affected:
                affected.add(dependant)
                pending.append(dependant)
    return affected


def _gate_run_and_evidence_from_result(
    request: GateExecutionRequest,
    result: GateExecutionResult,
) -> tuple[GateRunV2, EvidenceV2]:
    subjects = result.subjects or request.subjects or (DigestRef(request.gate_ref, _synthetic_digest("gate", request.gate_ref)),)
    dependency_refs = tuple(
        DigestRef(ref=record.evidence_id, digest=record.fingerprint())
        for record in request.dependency_evidence
    )
    dependencies = (*dependency_refs, *result.dependencies)
    command = result.command or request.command
    gate_run_id = _gate_run_id(request)
    evidence_id = "EVD-" + gate_run_id.removeprefix("GATERUN-")
    evidence_result = result.status.to_evidence_result()
    gate_run = GateRunV2(
        gate_run_id=gate_run_id,
        gate_ref=request.gate_ref,
        gate_definition_digest=request.gate_definition_digest,
        claim_refs=request.claim_refs,
        result=evidence_result,
        started_at=result.started_at,
        completed_at=result.completed_at,
        subjects=subjects,
        dependencies=dependencies,
        environment=request.environment,
        command=command,
        evidence_ref=evidence_id,
    )
    gate_run = GateRunV2(
        gate_run_id=gate_run.gate_run_id,
        gate_ref=gate_run.gate_ref,
        gate_definition_digest=gate_run.gate_definition_digest,
        claim_refs=gate_run.claim_refs,
        result=gate_run.result,
        started_at=gate_run.started_at,
        completed_at=gate_run.completed_at,
        subjects=gate_run.subjects,
        dependencies=gate_run.dependencies,
        environment=gate_run.environment,
        stored_fingerprint=gate_run.fingerprint(),
        command=gate_run.command,
        evidence_ref=evidence_id,
    )
    evidence = EvidenceV2(
        evidence_id=evidence_id,
        claim_refs=request.claim_refs,
        gate_ref=request.gate_ref,
        gate_definition_digest=request.gate_definition_digest,
        gate_run_id=gate_run_id,
        result=evidence_result,
        confidence="verified" if result.status == GateExecutionStatus.PASSED else "reviewed",
        subjects=subjects,
        dependencies=dependencies,
        environment=request.environment,
        refs=(*result.artifact_refs, gate_run_id),
    )
    evidence = EvidenceV2(
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
        dependency_scope_complete=evidence.dependency_scope_complete,
        stored_fingerprint=evidence.fingerprint(),
        refs=evidence.refs,
        supersedes=evidence.supersedes,
    )
    return gate_run, evidence


def _gate_run_id(request: GateExecutionRequest) -> str:
    return "GATERUN-" + canonical_fingerprint(
        {
            "idempotencyKey": request.idempotency_key,
            "attempt": request.attempt,
        }
    ).removeprefix("sha256:")[:16]


def _gate_idempotency_key(
    context: VerificationExecutionContext,
    gate_ref: str,
    gate_definition_digest: str,
) -> str:
    subject_payload = [subject.to_fingerprint() for subject in context.subjects]
    dependency_payload = [
        {"evidenceRef": evidence.evidence_id, "fingerprint": evidence.fingerprint()}
        for evidence in context.dependency_evidence
    ]
    return canonical_fingerprint(
        {
            "goalExecution": context.goal_execution_id,
            "planExecution": context.plan_execution_id,
            "nodeRun": context.node_run_id,
            "gateRef": gate_ref,
            "gateDefinitionDigest": gate_definition_digest,
            "subjects": subject_payload,
            "dependencies": dependency_payload,
            "attempt": context.attempt,
        }
    )


def _gate_definition_digest(definition: GateDefinition) -> str:
    return canonical_fingerprint(
        {
            "gateId": definition.gate_id,
            "version": definition.version,
            "level": definition.level,
            "evidenceKind": definition.evidence_kind,
            "verifierMode": definition.verifier_mode,
            "riskLevel": definition.risk_level.value,
        }
    )


def _synthetic_digest(kind: str, value: str) -> str:
    return canonical_fingerprint({"kind": kind, "value": value})


def _workspace_digest(workspace_ref: str | None) -> str | None:
    if not workspace_ref:
        return None
    path = Path(workspace_ref)
    if not path.exists() or not path.is_dir():
        return None
    entries: list[tuple[str, str]] = []
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        try:
            relative = item.relative_to(path).as_posix()
            digest = "sha256:" + hashlib.sha256(item.read_bytes()).hexdigest()
            entries.append((relative, digest))
        except OSError:
            continue
    payload = {"workspace": os.fspath(path), "files": entries}
    return canonical_fingerprint(payload)
