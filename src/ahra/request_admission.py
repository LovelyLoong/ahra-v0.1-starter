from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .alignment_engine import AlignmentRegistry, RequestDraft
from .capabilities import HIGH_RISK_ACTIONS
from .plan_ir import PlanCompilerConfig, compile_plan_draft


@dataclass(frozen=True, slots=True)
class RequestDraftRejection:
    code: str
    message: str
    ref: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "ref": self.ref}


@dataclass(frozen=True, slots=True)
class RequestDraftAdmissionResult:
    accepted: bool
    request_id: str
    rejections: tuple[RequestDraftRejection, ...] = ()
    plan_digest: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "ahra/request-draft-admission/0.1",
            "accepted": self.accepted,
            "requestId": self.request_id,
            "planDigest": self.plan_digest,
            "rejections": [rejection.to_dict() for rejection in self.rejections],
        }


class RequestDraftAdmission:
    def __init__(self, registry: AlignmentRegistry | None = None) -> None:
        self.registry = registry or AlignmentRegistry()

    def evaluate(self, draft: RequestDraft) -> RequestDraftAdmissionResult:
        rejections: list[RequestDraftRejection] = []
        rejections.extend(self._profile_rejections(draft))
        rejections.extend(self._registry_rejections(draft))
        rejections.extend(_digest_rejections(draft))
        rejections.extend(_claim_graph_rejections(draft))
        rejections.extend(_capability_rejections(draft))
        plan_result = compile_plan_draft(
            draft.plan_draft,
            PlanCompilerConfig(
                goal_ref=draft.goal_ref,
                goal_digest=draft.goal_digest,
                claim_graph_digest=draft.claim_graph_digest,
                required_claim_refs=frozenset(draft.required_claim_refs),
                registered_node_types=draft.registered_node_types,
                registered_gate_refs=draft.registered_gate_refs,
                registered_runtime_refs=draft.registered_runtime_refs,
                allowed_capabilities=frozenset(draft.allowed_capabilities),
                default_runtime_ref=draft.runtime_ref,
            ),
        )
        if not plan_result.report.valid:
            for error in plan_result.report.errors:
                rejections.append(RequestDraftRejection(error.code, error.message, error.ref))
        if rejections:
            return RequestDraftAdmissionResult(
                accepted=False,
                request_id=draft.request_id,
                rejections=tuple(sorted(rejections, key=lambda item: (item.code, item.ref))),
            )
        assert plan_result.plan is not None
        return RequestDraftAdmissionResult(
            accepted=True,
            request_id=draft.request_id,
            plan_digest=plan_result.plan.digest(),
        )

    def require_accepted(self, draft: RequestDraft) -> RequestDraftAdmissionResult:
        result = self.evaluate(draft)
        if not result.accepted:
            codes = ", ".join(rejection.code for rejection in result.rejections)
            raise ValueError(f"RequestDraft admission rejected {draft.request_id}: {codes}")
        return result

    def _profile_rejections(self, draft: RequestDraft) -> tuple[RequestDraftRejection, ...]:
        try:
            profile = self.registry.resolve_profile(draft.profile_ref)
        except Exception as exc:  # noqa: BLE001 - normalize into structured admission rejection.
            return (RequestDraftRejection("unknown_profile_ref", str(exc), "spec.profileRef"),)
        rejections: list[RequestDraftRejection] = []
        if draft.planner_adapter_ref != profile.planner_adapter_ref:
            rejections.append(RequestDraftRejection("unknown_planner_adapter", "planner adapter does not match selected profile", "spec.planner.adapterRef"))
        if draft.executor_adapter_ref != profile.executor_adapter_ref:
            rejections.append(RequestDraftRejection("unknown_executor_adapter", "executor adapter does not match selected profile", "spec.executor.adapterRef"))
        if draft.gate_runner_adapter_ref != profile.gate_runner_adapter_ref:
            rejections.append(RequestDraftRejection("unknown_gate_runner", "gate runner adapter does not match selected profile", "spec.gateRunner.adapterRef"))
        if draft.runtime_ref != profile.runtime_ref or draft.runtime_digest != profile.runtime_digest:
            rejections.append(RequestDraftRejection("unknown_runtime_ref", "runtime ref/digest does not match selected profile", "spec.runtime"))
        return tuple(rejections)

    def _registry_rejections(self, draft: RequestDraft) -> tuple[RequestDraftRejection, ...]:
        rejections: list[RequestDraftRejection] = []
        trusted_node_digests = dict(self.registry.node_type_digests)
        trusted_gate_digests = dict(self.registry.gate_ref_digests)
        for node_type, digest in draft.registered_node_types.items():
            expected = trusted_node_digests.get(node_type)
            ref = f"spec.registry.nodeTypes.{node_type}"
            if expected is None:
                rejections.append(RequestDraftRejection("untrusted_node_type_ref", "node type is not in the trusted alignment registry", ref))
            elif digest != expected:
                rejections.append(RequestDraftRejection("node_digest_mismatch", "node type digest does not match the trusted alignment registry", ref))
        for gate_ref, digest in draft.registered_gate_refs.items():
            expected = trusted_gate_digests.get(gate_ref)
            ref = f"spec.registry.gateRefs.{gate_ref}"
            if expected is None:
                rejections.append(RequestDraftRejection("untrusted_gate_ref", "gate ref is not in the trusted alignment registry", ref))
            elif digest != expected:
                rejections.append(RequestDraftRejection("gate_digest_mismatch", "gate ref digest does not match the trusted alignment registry", ref))
        return tuple(rejections)


def _digest_rejections(draft: RequestDraft) -> tuple[RequestDraftRejection, ...]:
    rejections: list[RequestDraftRejection] = []
    for ref, value in {
        "spec.goal.goalDigest": draft.goal_digest,
        "spec.goal.claimGraphDigest": draft.claim_graph_digest,
        "spec.runtime.digest": draft.runtime_digest,
        **{f"spec.registry.nodeTypes.{key}": item for key, item in draft.registered_node_types.items()},
        **{f"spec.registry.gateRefs.{key}": item for key, item in draft.registered_gate_refs.items()},
        **{f"spec.registry.runtimeRefs.{key}": item for key, item in draft.registered_runtime_refs.items()},
    }.items():
        if not _is_digest(value):
            rejections.append(RequestDraftRejection("invalid_digest", "digest reference must be sha256:<64 hex chars>", ref))
    runtime_digest = draft.registered_runtime_refs.get(draft.runtime_ref)
    if runtime_digest != draft.runtime_digest:
        rejections.append(RequestDraftRejection("runtime_digest_mismatch", "runtime registry does not resolve selected runtime digest", "spec.registry.runtimeRefs"))
    return tuple(rejections)


def _claim_graph_rejections(draft: RequestDraft) -> tuple[RequestDraftRejection, ...]:
    claims = {claim.claim_id: claim for claim in draft.claim_graph.claims}
    rejections: list[RequestDraftRejection] = []
    if len(claims) != len(draft.claim_graph.claims):
        rejections.append(RequestDraftRejection("duplicate_claim_id", "ClaimGraph contains duplicate claim ids", "spec.claimGraph.spec.claims"))
    for claim in draft.claim_graph.claims:
        for dependency in claim.depends_on:
            if dependency not in claims:
                rejections.append(RequestDraftRejection("unknown_claim_dependency", f"{claim.claim_id} depends on unknown claim", dependency))
        for gate_ref in claim.gate_refs:
            if gate_ref not in draft.registered_gate_refs:
                rejections.append(RequestDraftRejection("unregistered_gate_ref", f"{claim.claim_id} references unregistered gate", gate_ref))
    rejections.extend(_claim_cycle_rejections(draft))
    known_claims = set(claims)
    for node in draft.plan_draft.nodes:
        for claim_ref in node.claim_refs:
            if claim_ref not in known_claims:
                rejections.append(RequestDraftRejection("unknown_plan_claim_ref", f"{node.node_id} references unknown claim", claim_ref))
    return tuple(rejections)


def _claim_cycle_rejections(draft: RequestDraft) -> tuple[RequestDraftRejection, ...]:
    claims = {claim.claim_id: claim for claim in draft.claim_graph.claims}
    visiting: set[str] = set()
    visited: set[str] = set()
    rejections: list[RequestDraftRejection] = []

    def visit(claim_id: str, path: tuple[str, ...]) -> None:
        if claim_id in visiting:
            rejections.append(RequestDraftRejection("cyclic_claim_graph", "ClaimGraph dependency cycle detected", " -> ".join((*path, claim_id))))
            return
        if claim_id in visited:
            return
        claim = claims.get(claim_id)
        if claim is None:
            return
        visiting.add(claim_id)
        for dependency in claim.depends_on:
            visit(dependency, (*path, claim_id))
        visiting.remove(claim_id)
        visited.add(claim_id)

    for claim_id in sorted(claims):
        visit(claim_id, ())
    return tuple(rejections)


def _capability_rejections(draft: RequestDraft) -> tuple[RequestDraftRejection, ...]:
    rejections: list[RequestDraftRejection] = []
    allowed = set(draft.allowed_capabilities)
    for node in draft.plan_draft.nodes:
        for request in node.capability_requests:
            if request.capability not in allowed:
                rejections.append(RequestDraftRejection("capability_not_allowed", "capability is outside the RequestDraft allowed set", request.capability))
            if request.capability in HIGH_RISK_ACTIONS and not draft.capability_policies.get(request.capability):
                rejections.append(
                    RequestDraftRejection(
                        "high_risk_capability_requires_policy",
                        "high-risk capability must carry an explicit policy/approval reference before authorization",
                        request.capability,
                    )
                )
    return tuple(rejections)


def _is_digest(value: str) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return False
    raw = value.removeprefix("sha256:")
    if len(raw) != 64:
        return False
    try:
        int(raw, 16)
    except ValueError:
        return False
    return True


__all__ = [
    "RequestDraftAdmission",
    "RequestDraftAdmissionResult",
    "RequestDraftRejection",
]
