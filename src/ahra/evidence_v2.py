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
        self._records = {record.evidence_id: record for record in records}

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
        return inspections

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
