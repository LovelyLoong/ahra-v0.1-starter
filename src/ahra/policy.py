from __future__ import annotations

import uuid

from .domain import PolicyDecision, PolicyInput, SideEffect, ToolDescriptor, utc_now


RISK_ORDER = {"R0": 0, "R1": 1, "R2": 2, "R3": 3}


class ReferencePolicyEngine:
    """Fail-closed reference policy. Replace with OPA or another PDP in production."""

    policy_version = "reference-policy/0.1"

    def decide(self, request: PolicyInput, tool: ToolDescriptor) -> PolicyDecision:
        missing_scopes = set(tool.required_scopes) - set(request.granted_scopes)
        disallowed_data = set(request.data_classes) - set(tool.data_classes_allowed)
        approval_required = (
            RISK_ORDER.get(tool.risk_level, 99) >= 2
            or tool.side_effect in {SideEffect.EXTERNAL_WRITE, SideEffect.IRREVERSIBLE_OR_HIGH_IMPACT}
        )

        allow = True
        reason = "allow"
        if missing_scopes:
            allow = False
            reason = "missing_scope"
        elif disallowed_data:
            allow = False
            reason = "data_class_not_allowed"
        elif approval_required and not request.approval_refs:
            allow = False
            reason = "approval_required"
        elif tool.idempotency == "not_idempotent" and request.action.endswith(".retry"):
            allow = False
            reason = "unsafe_retry"

        runtime_tier = None
        if tool.side_effect == SideEffect.IRREVERSIBLE_OR_HIGH_IMPACT:
            runtime_tier = "T3"

        return PolicyDecision(
            decision_id=f"PDEC-{uuid.uuid4()}",
            allow=allow,
            reason_code=reason,
            policy_version=self.policy_version,
            approval_required=approval_required,
            credential_scopes=tuple(tool.required_scopes if allow else ()),
            decided_at=utc_now(),
            required_runtime_tier=runtime_tier,
        )
