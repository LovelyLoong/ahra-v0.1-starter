from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping

from .evidence_v2 import SUPPORTED_API_VERSION, canonical_fingerprint


BOUNDARY_CONTRACT_KIND = "BoundaryContract"


class BoundaryContractError(ValueError):
    """Structured failure for boundary-contract violations."""

    def __init__(self, code: str, message: str, *, ref: str, refs: tuple[str, ...] = ()) -> None:
        self.code = code
        self.message = message
        self.ref = ref
        self.refs = refs or (ref,)
        super().__init__(f"{code} {ref}: {message}")


class BoundaryEntryKind(StrEnum):
    MUST = "must"
    MUST_NOT = "must_not"
    COMPLETION_SIGNAL = "completion_signal"
    FREE_ZONE = "free_zone"
    OPEN_QUESTION = "open_question"


@dataclass(frozen=True, slots=True)
class BoundaryContractEntry:
    entry_id: str
    kind: str
    statement: str
    source_refs: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "BoundaryContractEntry":
        entry_id = _required_string(data, "id", "entry.id")
        return cls(
            entry_id=entry_id,
            kind=_required_string(data, "kind", f"entries.{entry_id}.kind"),
            statement=_required_string(data, "statement", f"entries.{entry_id}.statement"),
            source_refs=_string_tuple(data.get("sourceRefs"), f"entries.{entry_id}.sourceRefs"),
        )

    def to_mapping(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.entry_id,
            "kind": self.kind,
            "statement": self.statement,
        }
        if self.source_refs:
            data["sourceRefs"] = list(self.source_refs)
        return data


@dataclass(frozen=True, slots=True)
class BoundaryContract:
    name: str
    version: int
    entries: tuple[BoundaryContractEntry, ...]
    api_version: str = SUPPORTED_API_VERSION
    kind: str = BOUNDARY_CONTRACT_KIND

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "BoundaryContract":
        if data.get("apiVersion") != SUPPORTED_API_VERSION:
            raise BoundaryContractError(
                "invalid_api_version",
                f"BoundaryContract apiVersion must be {SUPPORTED_API_VERSION}",
                ref="apiVersion",
            )
        if data.get("kind") != BOUNDARY_CONTRACT_KIND:
            raise BoundaryContractError(
                "invalid_kind",
                f"expected kind {BOUNDARY_CONTRACT_KIND}",
                ref="kind",
            )
        metadata = _mapping(data.get("metadata"), "metadata")
        spec = _mapping(data.get("spec"), "spec")
        entries = _entries(spec.get("entries"))
        return cls(
            name=_required_string(metadata, "name", "metadata.name"),
            version=_positive_int(metadata.get("version"), "metadata.version"),
            entries=entries,
        )

    @classmethod
    def freeze(cls, data: Mapping[str, Any]) -> "BoundaryContract":
        return cls.from_mapping(data).validate_for_freeze()

    def validate_for_freeze(self) -> "BoundaryContract":
        if not self.entries:
            raise BoundaryContractError("empty_boundary_contract", "boundary contract must contain entries", ref="spec.entries")
        seen: set[str] = set()
        duplicates: list[str] = []
        for index, entry in enumerate(self.entries):
            ref = f"spec.entries.{index}"
            if entry.entry_id in seen:
                duplicates.append(entry.entry_id)
            seen.add(entry.entry_id)
            kind = _entry_kind(entry.kind, ref=f"{ref}.kind")
            if kind == BoundaryEntryKind.OPEN_QUESTION:
                raise BoundaryContractError(
                    "open_question_not_freezable",
                    "boundary contract freeze cannot include open_question entries",
                    ref=f"{ref}.kind",
                    refs=(entry.entry_id,),
                )
        if duplicates:
            unique_duplicates = tuple(sorted(set(duplicates)))
            raise BoundaryContractError(
                "duplicate_entry_id",
                "boundary contract entry IDs must be unique",
                ref="spec.entries",
                refs=unique_duplicates,
            )
        return self

    def digest(self) -> str:
        return canonical_fingerprint(self.to_mapping())

    def to_mapping(self) -> dict[str, Any]:
        return {
            "apiVersion": self.api_version,
            "kind": self.kind,
            "metadata": {
                "name": self.name,
                "version": self.version,
            },
            "spec": {
                "entries": [entry.to_mapping() for entry in self.entries],
            },
        }


def _entries(value: Any) -> tuple[BoundaryContractEntry, ...]:
    if isinstance(value, Mapping):
        entries = []
        for entry_id, entry_data in sorted(value.items()):
            entry_mapping = dict(_mapping(entry_data, f"spec.entries.{entry_id}"))
            entry_mapping.setdefault("id", str(entry_id))
            entries.append(BoundaryContractEntry.from_mapping(entry_mapping))
        return tuple(entries)
    if not isinstance(value, list):
        raise BoundaryContractError("invalid_entries", "spec.entries must be an array or mapping", ref="spec.entries")
    return tuple(BoundaryContractEntry.from_mapping(_mapping(item, "spec.entries")) for item in value)


def _mapping(value: Any, ref: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BoundaryContractError("invalid_mapping", f"{ref} must be a mapping", ref=ref)
    return value


def _required_string(data: Mapping[str, Any], key: str, ref: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise BoundaryContractError("missing_string", f"{key} must be a non-empty string", ref=ref)
    return value


def _positive_int(value: Any, ref: str) -> int:
    if not isinstance(value, int) or value < 1:
        raise BoundaryContractError("invalid_integer", f"{ref} must be an integer greater than zero", ref=ref)
    return value


def _string_tuple(value: Any, ref: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise BoundaryContractError("invalid_string_list", f"{ref} must be a list of strings", ref=ref)
    result = tuple(str(item) for item in value)
    if any(not item.strip() for item in result):
        raise BoundaryContractError("invalid_string_list", f"{ref} must contain only non-empty strings", ref=ref)
    return result


def _entry_kind(value: str, *, ref: str) -> BoundaryEntryKind:
    try:
        return BoundaryEntryKind(value)
    except ValueError as exc:
        raise BoundaryContractError("unknown_entry_kind", "boundary contract entry kind is not registered", ref=ref, refs=(value,)) from exc


__all__ = [
    "BOUNDARY_CONTRACT_KIND",
    "BoundaryContract",
    "BoundaryContractEntry",
    "BoundaryContractError",
    "BoundaryEntryKind",
]
