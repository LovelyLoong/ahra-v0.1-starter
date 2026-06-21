from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Iterable

from .domain import ContextItem, ContextManifest


TRUST_VALUES = {
    "system-authoritative",
    "project-authoritative",
    "human-provided",
    "retrieved-untrusted",
    "tool-output-untrusted",
    "remote-agent-untrusted",
    "model-generated",
}

KIND_ORDER = {
    "policy": 0,
    "agent_release": 1,
    "task": 2,
    "run_state": 3,
    "awkp_document": 4,
    "skill": 5,
    "tool_schema": 6,
    "memory": 7,
    "session": 8,
    "input": 9,
    "output_contract": 10,
}

MANDATORY_KINDS = {"policy", "agent_release", "task", "run_state", "output_contract"}


@dataclass(frozen=True, slots=True)
class ContextSource:
    kind: str
    ref: str
    content: bytes
    trust: str
    priority: int = 100
    estimated_tokens: int | None = None


class ContextBudgetError(RuntimeError):
    pass


class ContextBuilder:
    compiler_version = "context-builder/0.1"

    @staticmethod
    def _digest(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def _estimate_tokens(content: bytes) -> int:
        # Deterministic approximation for budgeting, not provider billing.
        return max(1, (len(content.decode("utf-8", errors="replace")) + 3) // 4)

    def build(
        self,
        *,
        run_id: str,
        agent_release_digest: str,
        sources: Iterable[ContextSource],
        token_budget: int,
    ) -> ContextManifest:
        if token_budget <= 0:
            raise ValueError("token_budget must be positive")

        normalized: list[ContextItem] = []
        for source in sources:
            if source.kind not in KIND_ORDER:
                raise ValueError(f"unknown context kind: {source.kind}")
            if source.trust not in TRUST_VALUES:
                raise ValueError(f"unknown trust label: {source.trust}")
            normalized.append(
                ContextItem(
                    kind=source.kind,
                    ref=source.ref,
                    sha256=self._digest(source.content),
                    trust=source.trust,
                    priority=source.priority,
                    estimated_tokens=source.estimated_tokens
                    if source.estimated_tokens is not None
                    else self._estimate_tokens(source.content),
                )
            )

        normalized.sort(key=lambda item: (KIND_ORDER[item.kind], -item.priority, item.ref))
        mandatory_cost = sum(item.estimated_tokens for item in normalized if item.kind in MANDATORY_KINDS)
        if mandatory_cost > token_budget:
            raise ContextBudgetError(
                f"mandatory context requires {mandatory_cost} tokens, budget is {token_budget}"
            )

        selected: list[ContextItem] = []
        used = 0
        for index, item in enumerate(normalized):
            remaining_mandatory = sum(
                future.estimated_tokens
                for future in normalized[index + 1 :]
                if future.kind in MANDATORY_KINDS
            )
            if item.kind in MANDATORY_KINDS:
                selected.append(item)
                used += item.estimated_tokens
            elif used + item.estimated_tokens + remaining_mandatory <= token_budget:
                selected.append(item)
                used += item.estimated_tokens

        payload = {
            "schema_version": "ahra/context-manifest/0.1",
            "run_id": run_id,
            "agent_release_digest": agent_release_digest,
            "items": [
                {
                    "kind": item.kind,
                    "ref": item.ref,
                    "sha256": item.sha256,
                    "trust": item.trust,
                    "priority": item.priority,
                    "estimated_tokens": item.estimated_tokens,
                }
                for item in selected
            ],
            "token_budget": token_budget,
            "compiler_version": self.compiler_version,
        }
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        digest = hashlib.sha256(canonical).hexdigest()
        return ContextManifest(
            context_manifest_id=f"CTXMAN-{digest[:24]}",
            run_id=run_id,
            agent_release_digest=agent_release_digest,
            items=tuple(selected),
            token_budget=token_budget,
            compiler_version=self.compiler_version,
            sha256=digest,
        )
