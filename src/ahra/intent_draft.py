from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


SUPPORTED_API_VERSION = "ahra.dev/v1alpha1"


@dataclass(frozen=True, slots=True)
class IntentCapabilityNeed:
    action: str
    resources: tuple[str, ...]
    reason: str = ""
    risk_level: str = "R1"
    policy_refs: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "IntentCapabilityNeed":
        return cls(
            action=_string(data, "action"),
            resources=_string_tuple(data.get("resources", ())),
            reason=str(data.get("reason") or ""),
            risk_level=str(data.get("riskLevel") or "R1"),
            policy_refs=_string_tuple(data.get("policyRefs", ()), allow_empty=True),
        )

    def to_mapping(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "action": self.action,
            "resources": list(self.resources),
            "riskLevel": self.risk_level,
        }
        if self.reason:
            result["reason"] = self.reason
        if self.policy_refs:
            result["policyRefs"] = list(self.policy_refs)
        return result


@dataclass(frozen=True, slots=True)
class IntentConstraint:
    key: str
    value: str
    required: bool = True

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "IntentConstraint":
        return cls(
            key=_string(data, "key"),
            value=_string(data, "value"),
            required=bool(data.get("required", True)),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "required": self.required,
        }


@dataclass(frozen=True, slots=True)
class IntentDraft:
    intent_id: str
    name: str
    abstract_goal: str
    constraints: tuple[IntentConstraint, ...]
    capability_needs: tuple[IntentCapabilityNeed, ...]
    context: Mapping[str, Any] = field(default_factory=dict)
    priority_hint: str | None = None
    risk_hint: str | None = None
    requester: str | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "IntentDraft":
        _require_kind(data, "IntentDraft")
        metadata = _mapping(data.get("metadata"), "metadata")
        spec = _mapping(data.get("spec"), "spec")
        return cls(
            intent_id=_string(metadata, "intentId"),
            name=str(metadata.get("name") or _name_from_id(_string(metadata, "intentId"))),
            abstract_goal=_string(spec, "abstractGoal"),
            constraints=tuple(IntentConstraint.from_mapping(_mapping(item, "constraint")) for item in spec.get("constraints", ())),
            capability_needs=tuple(
                IntentCapabilityNeed.from_mapping(_mapping(item, "capabilityNeed"))
                for item in spec.get("capabilityNeeds", ())
            ),
            context=dict(_mapping(spec.get("context", {}), "context")),
            priority_hint=str(spec["priorityHint"]) if spec.get("priorityHint") else None,
            risk_hint=str(spec["riskHint"]) if spec.get("riskHint") else None,
            requester=str(spec["requester"]) if spec.get("requester") else None,
        )

    def to_mapping(self) -> dict[str, Any]:
        spec: dict[str, Any] = {
            "abstractGoal": self.abstract_goal,
            "constraints": [constraint.to_mapping() for constraint in self.constraints],
            "capabilityNeeds": [need.to_mapping() for need in self.capability_needs],
            "context": dict(self.context),
        }
        if self.priority_hint:
            spec["priorityHint"] = self.priority_hint
        if self.risk_hint:
            spec["riskHint"] = self.risk_hint
        if self.requester:
            spec["requester"] = self.requester
        return {
            "apiVersion": SUPPORTED_API_VERSION,
            "kind": "IntentDraft",
            "metadata": {
                "intentId": self.intent_id,
                "name": self.name,
            },
            "spec": spec,
        }


def _require_kind(data: Mapping[str, Any], kind: str) -> None:
    if data.get("apiVersion") != SUPPORTED_API_VERSION:
        raise ValueError(f"{kind} apiVersion must be {SUPPORTED_API_VERSION}")
    if data.get("kind") != kind:
        raise ValueError(f"expected kind {kind}")


def _mapping(value: Any, ref: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{ref} must be a mapping")
    return value


def _string(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _string_tuple(value: Any, *, allow_empty: bool = False) -> tuple[str, ...]:
    if value is None:
        value = ()
    if not isinstance(value, list | tuple):
        raise TypeError("expected a list of strings")
    result = tuple(str(item) for item in value if str(item))
    if not result and not allow_empty:
        raise ValueError("string list must not be empty")
    return result


def _name_from_id(value: str) -> str:
    return value.lower().replace("_", "-").replace(".", "-")
