from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Mapping


SUPPORTED_API_VERSION = "ahra.dev/v1alpha1"


class EvidenceValidityState(StrEnum):
    CURRENT = "current"
    STALE = "stale"
    EXPIRED = "expired"
    REVOKED = "revoked"
    CONTRADICTED = "contradicted"


class EvidenceResult(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class DigestRef:
    ref: str
    digest: str

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "DigestRef":
        return cls(ref=str(data["ref"]), digest=str(data["digest"]))

    def to_fingerprint(self) -> dict[str, str]:
        return {"ref": self.ref, "digest": self.digest}


@dataclass(frozen=True, slots=True)
class EvidenceEnvironment:
    runtime_profile_digest: str
    policy_digest: str
    verifier_release_digest: str
    test_definition_digest: str
    relevant_environment_digest: str | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "EvidenceEnvironment":
        return cls(
            runtime_profile_digest=str(data["runtimeProfileDigest"]),
            policy_digest=str(data["policyDigest"]),
            verifier_release_digest=str(data["verifierReleaseDigest"]),
            test_definition_digest=str(data["testDefinitionDigest"]),
            relevant_environment_digest=(
                str(data["relevantEnvironmentDigest"]) if data.get("relevantEnvironmentDigest") else None
            ),
        )

    def to_fingerprint(self) -> dict[str, str | None]:
        return {
            "policyDigest": self.policy_digest,
            "relevantEnvironmentDigest": self.relevant_environment_digest,
            "runtimeProfileDigest": self.runtime_profile_digest,
            "testDefinitionDigest": self.test_definition_digest,
            "verifierReleaseDigest": self.verifier_release_digest,
        }


@dataclass(frozen=True, slots=True)
class EvidenceV2:
    evidence_id: str
    claim_refs: tuple[str, ...]
    gate_ref: str
    gate_definition_digest: str
    gate_run_id: str
    result: EvidenceResult
    confidence: str
    subjects: tuple[DigestRef, ...]
    dependencies: tuple[DigestRef, ...]
    environment: EvidenceEnvironment
    validity_state: EvidenceValidityState = EvidenceValidityState.CURRENT
    valid_until: datetime | None = None
    dependency_scope_complete: bool = True
    stored_fingerprint: str | None = None
    refs: tuple[str, ...] = ()
    supersedes: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "EvidenceV2":
        _require_api_version(data, "Evidence")
        metadata = _mapping(data["metadata"])
        spec = _mapping(data["spec"])
        validity = _mapping(spec["validity"])
        return cls(
            evidence_id=str(metadata["evidenceId"]),
            claim_refs=tuple(str(item) for item in spec["claimRefs"]),
            gate_ref=str(spec["gateRef"]),
            gate_definition_digest=str(spec["gateDefinitionDigest"]),
            gate_run_id=str(spec["gateRunId"]),
            result=EvidenceResult(str(spec["result"])),
            confidence=str(spec["confidence"]),
            subjects=tuple(DigestRef.from_mapping(_mapping(item)) for item in spec["subjects"]),
            dependencies=tuple(DigestRef.from_mapping(_mapping(item)) for item in spec.get("dependencies", ())),
            environment=EvidenceEnvironment.from_mapping(_mapping(spec["environment"])),
            validity_state=EvidenceValidityState(str(validity["state"])),
            valid_until=_parse_datetime(validity.get("validUntil")),
            dependency_scope_complete=str(spec.get("dependencyScope", "complete")) == "complete",
            stored_fingerprint=str(spec["fingerprint"]) if spec.get("fingerprint") else None,
            refs=tuple(str(item) for item in spec.get("refs", ())),
            supersedes=tuple(str(item) for item in spec.get("supersedes", ())),
        )

    def fingerprint_payload(self) -> dict[str, Any]:
        return {
            "claimRefs": sorted(self.claim_refs),
            "dependencies": sorted((item.to_fingerprint() for item in self.dependencies), key=lambda item: item["ref"]),
            "environment": self.environment.to_fingerprint(),
            "gateDefinitionDigest": self.gate_definition_digest,
            "gateRef": self.gate_ref,
            "subjects": sorted((item.to_fingerprint() for item in self.subjects), key=lambda item: item["ref"]),
        }

    def fingerprint(self) -> str:
        return canonical_fingerprint(self.fingerprint_payload())

    def bound_refs(self) -> dict[str, str]:
        result = {item.ref: item.digest for item in self.subjects}
        result.update({item.ref: item.digest for item in self.dependencies})
        return result


@dataclass(frozen=True, slots=True)
class GateRunV2:
    gate_run_id: str
    gate_ref: str
    gate_definition_digest: str
    claim_refs: tuple[str, ...]
    result: EvidenceResult
    started_at: datetime
    completed_at: datetime
    subjects: tuple[DigestRef, ...]
    dependencies: tuple[DigestRef, ...]
    environment: EvidenceEnvironment
    validity_state: EvidenceValidityState = EvidenceValidityState.CURRENT
    valid_until: datetime | None = None
    stored_fingerprint: str | None = None
    command: tuple[str, ...] = ()
    evidence_ref: str | None = None
    decision_at: datetime | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "GateRunV2":
        _require_api_version(data, "GateRun")
        metadata = _mapping(data["metadata"])
        spec = _mapping(data["spec"])
        validity = _mapping(spec["validity"])
        return cls(
            gate_run_id=str(metadata["gateRunId"]),
            gate_ref=str(spec["gateRef"]),
            gate_definition_digest=str(spec["gateDefinitionDigest"]),
            claim_refs=tuple(str(item) for item in spec["claimRefs"]),
            result=EvidenceResult(str(spec["result"])),
            started_at=_parse_datetime(spec["startedAt"]) or _epoch(),
            completed_at=_parse_datetime(spec["completedAt"]) or _epoch(),
            subjects=tuple(DigestRef.from_mapping(_mapping(item)) for item in spec["subjects"]),
            dependencies=tuple(DigestRef.from_mapping(_mapping(item)) for item in spec.get("dependencies", ())),
            environment=EvidenceEnvironment.from_mapping(_mapping(spec["environment"])),
            validity_state=EvidenceValidityState(str(validity["state"])),
            valid_until=_parse_datetime(validity.get("validUntil")),
            stored_fingerprint=str(spec["fingerprint"]) if spec.get("fingerprint") else None,
            command=tuple(str(item) for item in spec.get("command", ())),
            evidence_ref=str(spec["evidenceRef"]) if spec.get("evidenceRef") else None,
            decision_at=_parse_datetime(spec.get("decisionAt")),
        )

    def fingerprint_payload(self) -> dict[str, Any]:
        return {
            "claimRefs": sorted(self.claim_refs),
            "command": list(self.command),
            "dependencies": sorted((item.to_fingerprint() for item in self.dependencies), key=lambda item: item["ref"]),
            "environment": self.environment.to_fingerprint(),
            "gateDefinitionDigest": self.gate_definition_digest,
            "gateRef": self.gate_ref,
            "subjects": sorted((item.to_fingerprint() for item in self.subjects), key=lambda item: item["ref"]),
        }

    def fingerprint(self) -> str:
        return canonical_fingerprint(self.fingerprint_payload())


@dataclass(frozen=True, slots=True)
class EvidenceInvalidationTrigger:
    changed_refs: Mapping[str, str] = field(default_factory=dict)
    changed_claim_refs: frozenset[str] = frozenset()
    changed_gate_refs: frozenset[str] = frozenset()
    policy_digest: str | None = None
    runtime_profile_digest: str | None = None
    test_definition_digest: str | None = None
    verifier_release_digest: str | None = None
    now: datetime | None = None
    revoked_evidence_refs: frozenset[str] = frozenset()
    contradicted_evidence_refs: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class EvidenceInspection:
    evidence_id: str
    state: EvidenceValidityState
    fingerprint: str | None
    current: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "state": self.state.value,
            "fingerprint": self.fingerprint,
            "current": self.current,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True, slots=True)
class EvidenceSupersessionFailure:
    code: str
    evidence_ref: str
    message: str
    ref: str | None = None

    def to_dict(self) -> dict[str, str]:
        result = {
            "code": self.code,
            "evidenceRef": self.evidence_ref,
            "message": self.message,
        }
        if self.ref:
            result["ref"] = self.ref
        return result


@dataclass(frozen=True, slots=True)
class EvidenceCurrentSet:
    records: tuple[EvidenceV2, ...]
    current_records: tuple[EvidenceV2, ...]
    historical_records: tuple[EvidenceV2, ...]
    inspections: Mapping[str, EvidenceInspection]
    resolution_failures: tuple[EvidenceSupersessionFailure, ...] = ()

    @property
    def current_evidence_refs(self) -> tuple[str, ...]:
        return tuple(record.evidence_id for record in self.current_records)

    @property
    def historical_evidence_refs(self) -> tuple[str, ...]:
        return tuple(record.evidence_id for record in self.historical_records)

    @property
    def resolution_failure_refs(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    failure.evidence_ref
                    for failure in self.resolution_failures
                }
            )
        )

    def current_passed_by_claim(self) -> dict[str, tuple[EvidenceV2, ...]]:
        by_claim: dict[str, list[EvidenceV2]] = {}
        if self.resolution_failures:
            return {}
        for record in self.current_records:
            inspection = self.inspections[record.evidence_id]
            if (
                not inspection.current
                or record.result != EvidenceResult.PASSED
                or record.stored_fingerprint is None
                or record.stored_fingerprint != record.fingerprint()
            ):
                continue
            for claim_ref in record.claim_refs:
                by_claim.setdefault(claim_ref, []).append(record)
        return {
            claim_ref: tuple(sorted(records, key=lambda item: item.evidence_id))
            for claim_ref, records in sorted(by_claim.items())
        }

    def metrics(self) -> dict[str, int]:
        stale_by_reason: dict[str, int] = {}
        for inspection in self.inspections.values():
            if inspection.current:
                continue
            for reason in inspection.reasons:
                key = reason.split(":", 1)[0]
                stale_by_reason[key] = stale_by_reason.get(key, 0) + 1
        return {
            "historicalEvidenceCount": len(self.historical_records),
            "currentEvidenceLeafCount": len(self.current_records),
            "supersessionResolutionFailures": len(self.resolution_failures),
            "staleEvidenceCount": sum(1 for inspection in self.inspections.values() if not inspection.current),
            **{f"staleEvidenceCountByReason.{key}": value for key, value in sorted(stale_by_reason.items())},
        }


@dataclass(frozen=True, slots=True)
class EvidenceStatusEvent:
    event_id: str
    evidence_ref: str
    from_state: EvidenceValidityState
    to_state: EvidenceValidityState
    reason: str
    occurred_at: datetime
    superseded_by: str | None = None

    def to_dict(self) -> dict[str, Any]:
        spec: dict[str, Any] = {
            "evidenceRef": self.evidence_ref,
            "fromState": self.from_state.value,
            "toState": self.to_state.value,
            "reason": self.reason,
        }
        if self.superseded_by:
            spec["supersededBy"] = self.superseded_by
        return {
            "apiVersion": SUPPORTED_API_VERSION,
            "kind": "EvidenceStatusEvent",
            "metadata": {
                "eventId": self.event_id,
                "occurredAt": self.occurred_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            },
            "spec": spec,
        }


@dataclass(frozen=True, slots=True)
class LegacyEvidenceRecord:
    evidence_id: str
    task_id: str
    name: str
    sha256: str
    status: str
    reason: str


def canonical_fingerprint(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class EvidenceRegistry:
    def __init__(self, records: tuple[EvidenceV2, ...]) -> None:
        self._ordered_records = tuple(records)
        self._records = {record.evidence_id: record for record in records}
        if len(self._records) != len(records):
            raise ValueError("duplicate evidence_id in registry")

    def inspect(
        self,
        evidence_id: str,
        trigger: EvidenceInvalidationTrigger | None = None,
    ) -> EvidenceInspection:
        if evidence_id not in self._records:
            raise KeyError(f"unknown evidence: {evidence_id}")
        return self.inspect_all(trigger).get(evidence_id)  # type: ignore[return-value]

    def inspect_all(
        self,
        trigger: EvidenceInvalidationTrigger | None = None,
    ) -> dict[str, EvidenceInspection]:
        trigger = trigger or EvidenceInvalidationTrigger()
        inspections = {
            evidence_id: self._inspect_direct(record, trigger)
            for evidence_id, record in self._records.items()
        }
        changed = True
        while changed:
            changed = False
            for record in self._records.values():
                current = inspections[record.evidence_id]
                if current.state != EvidenceValidityState.CURRENT:
                    continue
                stale_dependencies = [
                    dependency.ref
                    for dependency in record.dependencies
                    if dependency.ref in inspections
                    and inspections[dependency.ref].state != EvidenceValidityState.CURRENT
                ]
                if stale_dependencies:
                    inspections[record.evidence_id] = EvidenceInspection(
                        evidence_id=record.evidence_id,
                        state=EvidenceValidityState.STALE,
                        fingerprint=record.fingerprint(),
                        current=False,
                        reasons=tuple(f"dependency_evidence_not_current:{ref}" for ref in sorted(stale_dependencies)),
                    )
                    changed = True
        superseded_by, failures = self._superseded_by()
        if not failures:
            for evidence_id, superseding_refs in superseded_by.items():
                inspection = inspections[evidence_id]
                inspections[evidence_id] = EvidenceInspection(
                    evidence_id=evidence_id,
                    state=inspection.state,
                    fingerprint=inspection.fingerprint,
                    current=False,
                    reasons=tuple(
                        sorted(
                            (
                                *inspection.reasons,
                                *(f"superseded_by:{ref}" for ref in sorted(superseding_refs)),
                            )
                        )
                    ),
                )
        return inspections

    def current_set(
        self,
        trigger: EvidenceInvalidationTrigger | None = None,
    ) -> EvidenceCurrentSet:
        inspections = self.inspect_all(trigger)
        superseded_by, validation_failures = self._superseded_by()
        historical = tuple(
            sorted(
                (record for record in self._ordered_records if record.evidence_id in superseded_by),
                key=lambda item: item.evidence_id,
            )
        )
        current = tuple(
            sorted(
                (record for record in self._ordered_records if record.evidence_id not in superseded_by),
                key=lambda item: item.evidence_id,
            )
        )
        competition_failures = self._competing_leaf_failures(current) if not validation_failures else ()
        failures = (*validation_failures, *competition_failures)
        if failures:
            current = ()
        return EvidenceCurrentSet(
            records=self._ordered_records,
            current_records=current,
            historical_records=historical,
            inspections=inspections,
            resolution_failures=failures,
        )

    def current_passed_by_claim(
        self,
        trigger: EvidenceInvalidationTrigger | None = None,
    ) -> dict[str, tuple[EvidenceV2, ...]]:
        return self.current_set(trigger).current_passed_by_claim()

    def supersession_status_events(
        self,
        *,
        occurred_at: datetime,
    ) -> tuple[EvidenceStatusEvent, ...]:
        superseded_by, failures = self._superseded_by()
        if failures:
            return ()
        events: list[EvidenceStatusEvent] = []
        for evidence_ref, superseding_refs in sorted(superseded_by.items()):
            for superseding_ref in sorted(superseding_refs):
                events.append(
                    make_status_event(
                        event_id=f"EVT-{evidence_ref}-superseded-by-{superseding_ref}",
                        evidence_ref=evidence_ref,
                        from_state=EvidenceValidityState.CURRENT,
                        to_state=EvidenceValidityState.CURRENT,
                        reason="superseded",
                        occurred_at=occurred_at,
                        superseded_by=superseding_ref,
                    )
                )
        return tuple(events)

    def _inspect_direct(
        self,
        record: EvidenceV2,
        trigger: EvidenceInvalidationTrigger,
    ) -> EvidenceInspection:
        fingerprint = record.fingerprint()
        reasons: list[str] = []
        if record.stored_fingerprint and record.stored_fingerprint != fingerprint:
            reasons.append("stored_fingerprint_mismatch")
        if record.validity_state != EvidenceValidityState.CURRENT:
            return EvidenceInspection(record.evidence_id, record.validity_state, fingerprint, False, (f"record_state:{record.validity_state.value}", *reasons))
        if record.evidence_id in trigger.revoked_evidence_refs:
            return EvidenceInspection(record.evidence_id, EvidenceValidityState.REVOKED, fingerprint, False, ("revoked", *reasons))
        if record.evidence_id in trigger.contradicted_evidence_refs:
            return EvidenceInspection(record.evidence_id, EvidenceValidityState.CONTRADICTED, fingerprint, False, ("contradicted", *reasons))
        now = trigger.now
        if now and record.valid_until and record.valid_until <= now:
            return EvidenceInspection(record.evidence_id, EvidenceValidityState.EXPIRED, fingerprint, False, ("ttl_expired", *reasons))

        stale_reasons = self._stale_reasons(record, trigger)
        if stale_reasons or reasons:
            return EvidenceInspection(record.evidence_id, EvidenceValidityState.STALE, fingerprint, False, tuple((*stale_reasons, *reasons)))
        return EvidenceInspection(record.evidence_id, EvidenceValidityState.CURRENT, fingerprint, True, ())

    def _stale_reasons(
        self,
        record: EvidenceV2,
        trigger: EvidenceInvalidationTrigger,
    ) -> tuple[str, ...]:
        reasons: list[str] = []
        bound = record.bound_refs()
        matched_changed_ref = False
        for ref, changed_digest in sorted(trigger.changed_refs.items()):
            if ref not in bound:
                continue
            matched_changed_ref = True
            if bound[ref] != changed_digest:
                reasons.append(f"digest_changed:{ref}")
        if trigger.changed_refs and not matched_changed_ref and not record.dependency_scope_complete:
            reasons.append("dependency_scope_incomplete")
        for claim_ref in sorted(set(record.claim_refs) & set(trigger.changed_claim_refs)):
            reasons.append(f"claim_changed:{claim_ref}")
        if _gate_base_ref(record.gate_ref) in {_gate_base_ref(ref) for ref in trigger.changed_gate_refs}:
            reasons.append(f"gate_changed:{_gate_base_ref(record.gate_ref)}")
        if trigger.policy_digest and trigger.policy_digest != record.environment.policy_digest:
            reasons.append("policy_changed")
        if trigger.runtime_profile_digest and trigger.runtime_profile_digest != record.environment.runtime_profile_digest:
            reasons.append("runtime_profile_changed")
        if trigger.test_definition_digest and trigger.test_definition_digest != record.environment.test_definition_digest:
            reasons.append("test_definition_changed")
        if trigger.verifier_release_digest and trigger.verifier_release_digest != record.environment.verifier_release_digest:
            reasons.append("verifier_release_changed")
        return tuple(reasons)

    def _superseded_by(self) -> tuple[dict[str, set[str]], tuple[EvidenceSupersessionFailure, ...]]:
        superseded_by: dict[str, set[str]] = {}
        failures: list[EvidenceSupersessionFailure] = []
        for record in self._ordered_records:
            if len(set(record.supersedes)) != len(record.supersedes):
                failures.append(
                    EvidenceSupersessionFailure(
                        code="duplicate_supersedes_ref",
                        evidence_ref=record.evidence_id,
                        message="Evidence supersedes list contains duplicate refs.",
                    )
                )
            for superseded_ref in record.supersedes:
                if superseded_ref == record.evidence_id:
                    failures.append(
                        EvidenceSupersessionFailure(
                            code="self_supersession",
                            evidence_ref=record.evidence_id,
                            ref=superseded_ref,
                            message="Evidence cannot supersede itself.",
                        )
                    )
                    continue
                if superseded_ref not in self._records:
                    failures.append(
                        EvidenceSupersessionFailure(
                            code="unknown_supersedes_ref",
                            evidence_ref=record.evidence_id,
                            ref=superseded_ref,
                            message=f"Evidence supersedes unknown record {superseded_ref}.",
                        )
                    )
                    continue
                superseded_by.setdefault(superseded_ref, set()).add(record.evidence_id)
        cycle_refs = self._supersession_cycle_refs()
        for evidence_ref in cycle_refs:
            failures.append(
                EvidenceSupersessionFailure(
                    code="supersession_cycle",
                    evidence_ref=evidence_ref,
                    message="Evidence supersession graph contains a cycle.",
                )
            )
        return superseded_by, tuple(sorted(failures, key=lambda item: (item.code, item.evidence_ref, item.ref or "")))

    def _supersession_cycle_refs(self) -> tuple[str, ...]:
        graph = {
            record.evidence_id: tuple(ref for ref in record.supersedes if ref in self._records)
            for record in self._ordered_records
        }
        visiting: set[str] = set()
        visited: set[str] = set()
        cycle_refs: set[str] = set()

        def visit(evidence_ref: str, path: tuple[str, ...]) -> None:
            if evidence_ref in visiting:
                if evidence_ref in path:
                    cycle_refs.update(path[path.index(evidence_ref) :])
                else:
                    cycle_refs.add(evidence_ref)
                return
            if evidence_ref in visited:
                return
            visiting.add(evidence_ref)
            for superseded_ref in graph.get(evidence_ref, ()):
                visit(superseded_ref, (*path, superseded_ref))
            visiting.remove(evidence_ref)
            visited.add(evidence_ref)

        for record in self._ordered_records:
            visit(record.evidence_id, (record.evidence_id,))
        return tuple(sorted(cycle_refs))

    def _competing_leaf_failures(self, current_records: tuple[EvidenceV2, ...]) -> tuple[EvidenceSupersessionFailure, ...]:
        by_key: dict[tuple[str, str, tuple[tuple[str, str], ...]], list[str]] = {}
        for record in current_records:
            subject_key = tuple(sorted((subject.ref, subject.digest) for subject in record.subjects))
            for claim_ref in record.claim_refs:
                key = (claim_ref, _gate_base_ref(record.gate_ref), subject_key)
                by_key.setdefault(key, []).append(record.evidence_id)
        failures: list[EvidenceSupersessionFailure] = []
        for refs in by_key.values():
            unique_refs = sorted(set(refs))
            if len(unique_refs) <= 1:
                continue
            for evidence_ref in unique_refs:
                failures.append(
                    EvidenceSupersessionFailure(
                        code="competing_current_leaves",
                        evidence_ref=evidence_ref,
                        ref=",".join(unique_refs),
                        message="Multiple unsuperseded Evidence leaves cover the same Claim, Gate, and subject set.",
                    )
                )
        return tuple(failures)


def make_status_event(
    *,
    event_id: str,
    evidence_ref: str,
    from_state: EvidenceValidityState,
    to_state: EvidenceValidityState,
    reason: str,
    occurred_at: datetime,
    superseded_by: str | None = None,
) -> EvidenceStatusEvent:
    return EvidenceStatusEvent(
        event_id=event_id,
        evidence_ref=evidence_ref,
        from_state=from_state,
        to_state=to_state,
        reason=reason,
        occurred_at=occurred_at,
        superseded_by=superseded_by,
    )


def adapt_legacy_evidence_manifest(manifest: Mapping[str, Any]) -> tuple[LegacyEvidenceRecord, ...]:
    task_id = str(manifest.get("task_id") or "")
    records = manifest.get("evidence", ())
    if not isinstance(records, list):
        raise ValueError("legacy evidence manifest evidence must be an array")
    result: list[LegacyEvidenceRecord] = []
    for item in records:
        if not isinstance(item, Mapping):
            raise ValueError("legacy evidence manifest entries must be objects")
        result.append(
            LegacyEvidenceRecord(
                evidence_id=str(item.get("evidence_id") or ""),
                task_id=str(item.get("task_id") or task_id),
                name=str(item.get("name") or ""),
                sha256=str(item.get("sha256") or ""),
                status="legacy_partial",
                reason=(
                    "Legacy AWKP evidence lacks full v2 fingerprint bindings "
                    "for claims, subjects, dependencies, gates, policies, runtimes, tests, and verifier releases."
                ),
            )
        )
    return tuple(result)


def _gate_base_ref(value: str) -> str:
    return value.split("@", 1)[0]


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("expected mapping")
    return value


def _require_api_version(data: Mapping[str, Any], kind: str) -> None:
    if data.get("apiVersion") != SUPPORTED_API_VERSION:
        raise ValueError(f"{kind} apiVersion must be {SUPPORTED_API_VERSION}")
    if data.get("kind") != kind:
        raise ValueError(f"expected kind {kind}")


def _parse_datetime(value: Any) -> datetime | None:
    if value in {None, ""}:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _epoch() -> datetime:
    return datetime(1970, 1, 1, tzinfo=UTC)
