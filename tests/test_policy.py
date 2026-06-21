from __future__ import annotations

import unittest

from ahra.domain import PolicyInput, SideEffect, ToolDescriptor
from ahra.policy import ReferencePolicyEngine


class PolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = ReferencePolicyEngine()
        self.tool = ToolDescriptor(
            name="deployment.production",
            version="1.0.0",
            side_effect=SideEffect.EXTERNAL_WRITE,
            risk_level="R2",
            required_scopes=("deploy:billing",),
            data_classes_allowed=("internal",),
            idempotency="caller_key_required",
            timeout_seconds=300,
        )

    def request(self, approval_refs=()):
        return PolicyInput(
            human_identity="user:42",
            agent_release="sha256:test",
            workload_identity="spiffe://example/worker/1",
            task_id="TASK-1",
            task_risk="R2",
            action="tool.invoke",
            resource=self.tool.name,
            granted_scopes=("deploy:billing",),
            data_classes=("internal",),
            approval_refs=approval_refs,
        )

    def test_high_risk_tool_requires_approval(self) -> None:
        decision = self.engine.decide(self.request(), self.tool)
        self.assertFalse(decision.allow)
        self.assertEqual(decision.reason_code, "approval_required")
        self.assertTrue(decision.approval_required)

    def test_specific_approval_allows_tool(self) -> None:
        decision = self.engine.decide(self.request(("APR-1",)), self.tool)
        self.assertTrue(decision.allow)
        self.assertEqual(decision.credential_scopes, ("deploy:billing",))


if __name__ == "__main__":
    unittest.main()
