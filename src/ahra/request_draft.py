from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .acceptance_contracts import ClaimGraph
from .evidence_v2 import canonical_fingerprint
from .goal_operations import GoalOperationError, GoalOperationProfile, GoalOperationProfileRegistry
from .intent_draft import IntentDraft
from .plan_ir import PlanDraft


NODE_BOUNDED_TASK_DIGEST = "sha256:" + "1" * 64
NODE_GOAL_VERIFICATION_DIGEST = "sha256:" + "2" * 64
GATE_ALIGNMENT_OBJECTIVE_DIGEST = "sha256:" + "3" * 64
GATE_ALIGNMENT_COMPLETION_DIGEST = "sha256:" + "4" * 64


class RequestDraftError(ValueError):
    def __init__(self, code: str, message: str, *, refs: tuple[str, ...] = ()) -> None:
        self.code = code
        self.message = message
        self.refs = refs
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class RequestDraftRegistry:
    profiles: GoalOperationProfileRegistry = field(default_factory=GoalOperationProfileRegistry)
    node_type_digests: Mapping[str, str] = field(
        default_factory=lambda: {
            "bounded_task": NODE_BOUNDED_TASK_DIGEST,
            "goal_verification": NODE_GOAL_VERIFICATION_DIGEST,
        }
    )
    gate_ref_digests: Mapping[str, str] = field(
        default_factory=lambda: {
            "GATE-alignment-objective": GATE_ALIGNMENT_OBJECTIVE_DIGEST,
            "GATE-alignment-complete": GATE_ALIGNMENT_COMPLETION_DIGEST,
        }
    )

    def resolve_profile(self, profile_ref: str) -> GoalOperationProfile:
        try:
            return self.profiles.get(profile_ref)
        except GoalOperationError as exc:
            raise RequestDraftError("unknown_profile_ref", "RequestDraft selected an unknown profile ref", refs=(profile_ref,)) from exc


@dataclass(frozen=True, slots=True)
class RequestDraft:
    request_id: str
    intent_id: str
    producer_actor: str
    name: str
    idempotency_key: str
    profile_ref: str
    workspace_ref: str
    artifact_dir: str
    store_kind: str
    store_path: str
    planner_adapter_ref: str
    executor_adapter_ref: str
    gate_runner_adapter_ref: str
    runtime_ref: str
    runtime_digest: str
    goal_ref: str
    goal_digest: str
    claim_graph: ClaimGraph
    claim_graph_digest: str
    required_claim_refs: tuple[str, ...]
    registered_node_types: Mapping[str, str]
    registered_gate_refs: Mapping[str, str]
    registered_runtime_refs: Mapping[str, str]
    allowed_capabilities: tuple[str, ...]
    capability_policies: Mapping[str, tuple[str, ...]]
    plan_draft: PlanDraft
    max_repair_cycles: int = 0
    max_concurrency: int = 1
    branch: str = "main"

    def to_mapping(self) -> dict[str, Any]:
        return {
            "apiVersion": "ahra.dev/v1alpha1",
            "kind": "RequestDraft",
            "metadata": {
                "requestId": self.request_id,
                "intentId": self.intent_id,
                "producerActor": self.producer_actor,
                "name": self.name,
                "idempotencyKey": self.idempotency_key,
            },
            "spec": {
                "profileRef": self.profile_ref,
                "workspaceRef": self.workspace_ref,
                "artifactDir": self.artifact_dir,
                "store": {"kind": self.store_kind, "path": self.store_path},
                "planner": {"adapterRef": self.planner_adapter_ref},
                "executor": {"adapterRef": self.executor_adapter_ref},
                "gateRunner": {"adapterRef": self.gate_runner_adapter_ref},
                "runtime": {"runtimeRef": self.runtime_ref, "digest": self.runtime_digest},
                "goal": {
                    "goalRef": self.goal_ref,
                    "goalDigest": self.goal_digest,
                    "claimGraphDigest": self.claim_graph_digest,
                    "requiredClaimRefs": list(self.required_claim_refs),
                },
                "claimGraph": _claim_graph_to_mapping(self.claim_graph),
                "registry": {
                    "nodeTypes": dict(sorted(self.registered_node_types.items())),
                    "gateRefs": dict(sorted(self.registered_gate_refs.items())),
                    "runtimeRefs": dict(sorted(self.registered_runtime_refs.items())),
                    "allowedCapabilities": list(self.allowed_capabilities),
                },
                "capabilityPolicies": {key: list(value) for key, value in sorted(self.capability_policies.items())},
                "execution": {
                    "maxRepairCycles": self.max_repair_cycles,
                    "maxConcurrency": self.max_concurrency,
                    "branch": self.branch,
                },
                "planDraft": self.plan_draft.to_dict(),
            },
        }


def _claim_graph_to_mapping(graph: ClaimGraph) -> dict[str, Any]:
    return {
        "apiVersion": "ahra.dev/v1alpha1",
        "kind": "ClaimGraph",
        "metadata": {
            "name": graph.goal_ref.removeprefix("GOAL-").lower(),
            "goalId": graph.goal_ref,
            "version": graph.version,
        },
        "spec": {
            "goalRef": graph.goal_ref,
            "claims": [
                {
                    "id": claim.claim_id,
                    "type": claim.claim_type.value,
                    "statement": claim.statement,
                    "criterionRefs": list(claim.criterion_refs),
                    "dependsOn": list(claim.depends_on),
                    "riskLevel": claim.risk_level.value,
                    "required": claim.required,
                    "requiredEvidenceKinds": list(claim.required_evidence_kinds),
                    "gateRefs": list(claim.gate_refs),
                    "approvalRequired": claim.approval_required,
                }
                for claim in graph.claims
            ],
        },
    }


def _goal_ref_from_intent(intent_id: str) -> str:
    return "GOAL-" + _id_tail(intent_id, "ALIGNED")


def _request_id(
    intent: IntentDraft,
    *,
    profile: GoalOperationProfile,
    producer_actor: str,
    workspace_ref: str,
    artifact_dir: str,
    store_path: str,
    goal_ref: str,
    goal_digest: str,
    claim_graph_digest: str,
    required_claim_refs: tuple[str, ...],
    allowed_capabilities: tuple[str, ...],
    capability_policies: Mapping[str, tuple[str, ...]],
    plan: PlanDraft,
) -> str:
    payload = {
        "intent": intent.to_mapping(),
        "profileRef": profile.profile_ref,
        "producerActor": producer_actor,
        "workspaceRef": workspace_ref,
        "artifactDir": artifact_dir,
        "storeKind": "sqlite",
        "storePath": store_path,
        "plannerAdapterRef": profile.planner_adapter_ref,
        "executorAdapterRef": profile.executor_adapter_ref,
        "gateRunnerAdapterRef": profile.gate_runner_adapter_ref,
        "runtimeRef": profile.runtime_ref,
        "runtimeDigest": profile.runtime_digest,
        "goalRef": goal_ref,
        "goalDigest": goal_digest,
        "claimGraphDigest": claim_graph_digest,
        "requiredClaimRefs": list(required_claim_refs),
        "allowedCapabilities": list(allowed_capabilities),
        "capabilityPolicies": {key: list(value) for key, value in sorted(capability_policies.items())},
        "planDraft": plan.to_dict(),
    }
    return "REQ-" + canonical_fingerprint(payload).removeprefix("sha256:")[:16]


def _request_name(intent_id: str) -> str:
    return ("phase1-" + intent_id.lower().replace("_", "-").replace(".", "-").removeprefix("intent-"))[:63]


def _id_tail(intent_id: str, fallback: str) -> str:
    cleaned = "".join(char if char.isalnum() else "-" for char in intent_id.upper())
    cleaned = cleaned.removeprefix("INTENT-").strip("-")
    if not cleaned:
        return fallback
    return f"{cleaned}-{fallback}"


__all__ = [
    "GATE_ALIGNMENT_COMPLETION_DIGEST",
    "GATE_ALIGNMENT_OBJECTIVE_DIGEST",
    "NODE_BOUNDED_TASK_DIGEST",
    "NODE_GOAL_VERIFICATION_DIGEST",
    "RequestDraft",
    "RequestDraftError",
    "RequestDraftRegistry",
]
