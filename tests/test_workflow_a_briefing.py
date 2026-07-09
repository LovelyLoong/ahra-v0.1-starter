from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from ahra.approval_service import ApprovalService
from ahra.workflow_a_briefing import (
    extract_briefing_metadata,
    render_gate2_briefing,
    request_digest,
    verify_gate2_briefing,
    write_gate2_briefing,
)
from tests.phase1_helpers import example_intent, request_draft_from_intent


class WorkflowAGate2BriefingTests(unittest.TestCase):
    def test_rendered_briefing_is_self_contained_and_escaped(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            draft = _draft(root)
            bad_request = replace(
                draft.plan_draft.nodes[0].capability_requests[0],
                resources=("<script>alert(1)</script>",),
            )
            bad_plan = replace(
                draft.plan_draft,
                nodes=(
                    replace(
                        draft.plan_draft.nodes[0],
                        capability_requests=(bad_request,),
                    ),
                    *draft.plan_draft.nodes[1:],
                ),
            )
            draft = replace(draft, plan_draft=bad_plan)
            approval = ApprovalService().request_authorization(draft, actor="agent:producer")

            html = render_gate2_briefing(draft, approval)

            self.assertIn("Workflow A Gate 2 Briefing", html)
            self.assertIn("Allowed Write Scope", html)
            self.assertIn("Explicitly Unauthorized Scope", html)
            self.assertIn("Human Checklist", html)
            self.assertNotIn("<script>alert(1)</script>", html)
            self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
            self.assertNotIn("<script", html.lower())
            self.assertNotIn("<link", html.lower())
            self.assertNotIn("http://", html.lower())
            self.assertNotIn("https://", html.lower())

    def test_binding_metadata_verifies_request_approval_and_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            draft = _draft(root)
            approval = ApprovalService().request_authorization(draft, actor="agent:producer").to_dict()
            approval["requestDigest"] = request_digest(draft)
            html = render_gate2_briefing(draft, approval)

            verified = verify_gate2_briefing(html, draft, approval)

            self.assertEqual(verified["requestId"], draft.request_id)
            self.assertEqual(verified["approvalId"], approval["approvalId"])
            self.assertEqual(verified["requestDigest"], approval["requestDigest"])

            tampered = html.replace(approval["requestDigest"], "sha256:" + "0" * 64)
            with self.assertRaisesRegex(ValueError, "requestDigest"):
                verify_gate2_briefing(tampered, draft, approval)

    def test_write_briefing_returns_artifact_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            draft = _draft(root)
            approval = ApprovalService().request_authorization(draft, actor="agent:producer")
            path = root / "gate-2.html"

            result = write_gate2_briefing(path, draft, approval)

            self.assertTrue(path.exists())
            self.assertEqual(result["briefingPath"], str(path))
            metadata = extract_briefing_metadata(path.read_text(encoding="utf-8"))
            self.assertEqual(metadata["ahra-request-id"], draft.request_id)
            self.assertEqual(metadata["ahra-approval-id"], approval.approval_id)


def _draft(root: Path):
    return request_draft_from_intent(root, example_intent())


if __name__ == "__main__":
    unittest.main()
