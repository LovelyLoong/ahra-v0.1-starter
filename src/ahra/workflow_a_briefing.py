from __future__ import annotations

import html
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Mapping

from .approval_service import ApprovalRecord
from .evidence_v2 import canonical_fingerprint
from .request_admission import RequestDraftAdmission
from .request_draft import RequestDraft


BRIEFING_SCHEMA_VERSION = "ahra/workflow-a-gate2-briefing/0.1"
DEFAULT_GATE2_BRIEFING_NAME = "gate-2-briefing.html"


@dataclass(frozen=True, slots=True)
class Gate2BriefingBinding:
    request_id: str
    approval_id: str
    request_digest: str
    plan_digest: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": BRIEFING_SCHEMA_VERSION,
            "requestId": self.request_id,
            "approvalId": self.approval_id,
            "requestDigest": self.request_digest,
            "planDigest": self.plan_digest,
        }


def request_digest(draft: RequestDraft) -> str:
    return canonical_fingerprint(draft.to_mapping())


def plan_digest(draft: RequestDraft) -> str | None:
    admission = RequestDraftAdmission().evaluate(draft)
    return admission.plan_digest


def briefing_binding(draft: RequestDraft, approval: ApprovalRecord | Mapping[str, Any]) -> Gate2BriefingBinding:
    approval_mapping = _approval_mapping(approval)
    return Gate2BriefingBinding(
        request_id=draft.request_id,
        approval_id=str(approval_mapping.get("approvalId") or ""),
        request_digest=request_digest(draft),
        plan_digest=plan_digest(draft),
    )


def render_gate2_briefing(
    draft: RequestDraft,
    approval: ApprovalRecord | Mapping[str, Any],
    *,
    request_draft_path: Path | str | None = None,
    approval_path: Path | str | None = None,
    output_path: Path | str | None = None,
) -> str:
    approval_mapping = _approval_mapping(approval)
    binding = briefing_binding(draft, approval_mapping)
    nodes = draft.plan_draft.nodes
    claim_ids_by_node = {claim_ref for node in nodes for claim_ref in node.claim_refs}
    allowed_write_scope = _allowed_write_scope(draft)
    unauthorized_scope = _unauthorized_scope(draft, allowed_write_scope)
    non_goals = _non_goals(unauthorized_scope)
    request_path_text = str(request_draft_path) if request_draft_path else "<request-draft.json>"
    approval_path_text = str(approval_path) if approval_path else "<approval.json>"
    output_path_text = str(output_path) if output_path else "<goal-execution-request.yaml>"
    briefing_path_text = "<gate-2-briefing.html>"
    next_command = (
        "uv run python -B -m ahra.cli workflow-a authorize "
        f"--request-draft {request_path_text} --approval {approval_path_text} "
        f"--briefing {briefing_path_text} --output {output_path_text} "
        "--actor human:<name>"
    )
    status = str(approval_mapping.get("status") or "unknown")
    checklist = (
        "Request id and approval id match this briefing.",
        "Request digest in this briefing matches the RequestDraft.",
        "Allowed write scope is limited to the listed resources.",
        "Unauthorized scope and non-goals are acceptable.",
        "Plan nodes cover required claims before Workflow B starts.",
        "The approving actor is human and distinct from the producer.",
    )
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f'<meta name="ahra-briefing-schema" content="{_e(BRIEFING_SCHEMA_VERSION)}">',
            f'<meta name="ahra-request-id" content="{_e(binding.request_id)}">',
            f'<meta name="ahra-approval-id" content="{_e(binding.approval_id)}">',
            f'<meta name="ahra-request-digest" content="{_e(binding.request_digest)}">',
            f'<meta name="ahra-plan-digest" content="{_e(binding.plan_digest or "")}">',
            "<title>Workflow A Gate 2 Briefing</title>",
            "<style>",
            "body{font-family:Arial,sans-serif;line-height:1.45;margin:2rem;color:#182026;background:#fff}",
            "main{max-width:960px;margin:0 auto}",
            "h1,h2{line-height:1.2}",
            "section{border-top:1px solid #d7dde2;padding-top:1rem;margin-top:1rem}",
            "code{background:#f4f6f8;padding:.1rem .25rem;border-radius:3px}",
            "table{border-collapse:collapse;width:100%}",
            "th,td{border:1px solid #d7dde2;padding:.45rem;text-align:left;vertical-align:top}",
            ".status{font-weight:700}",
            "</style>",
            "</head>",
            "<body>",
            "<main>",
            "<h1>Workflow A Gate 2 Briefing</h1>",
            "<section>",
            "<h2>Binding</h2>",
            "<dl>",
            f"<dt>Request id</dt><dd><code>{_e(binding.request_id)}</code></dd>",
            f"<dt>Approval id</dt><dd><code>{_e(binding.approval_id)}</code></dd>",
            f"<dt>Request digest</dt><dd><code>{_e(binding.request_digest)}</code></dd>",
            f"<dt>Plan digest</dt><dd><code>{_e(binding.plan_digest or 'unavailable')}</code></dd>",
            f"<dt>Current status</dt><dd class=\"status\">{_e(status)}</dd>",
            "</dl>",
            "</section>",
            "<section>",
            "<h2>Next Safe Command</h2>",
            f"<p><code>{_e(next_command)}</code></p>",
            "</section>",
            "<section>",
            "<h2>Allowed Write Scope</h2>",
            _list(allowed_write_scope),
            "</section>",
            "<section>",
            "<h2>Explicitly Unauthorized Scope</h2>",
            _list(unauthorized_scope),
            "</section>",
            "<section>",
            "<h2>Plan Node Summary</h2>",
            _node_table(draft),
            "</section>",
            "<section>",
            "<h2>Claim Coverage Summary</h2>",
            _claim_table(draft, claim_ids_by_node),
            "</section>",
            "<section>",
            "<h2>Non-goals</h2>",
            _list(non_goals),
            "</section>",
            "<section>",
            "<h2>Human Checklist</h2>",
            _checklist(checklist),
            "</section>",
            "</main>",
            "</body>",
            "</html>",
            "",
        ]
    )


def write_gate2_briefing(
    path: Path,
    draft: RequestDraft,
    approval: ApprovalRecord | Mapping[str, Any],
    *,
    request_draft_path: Path | str | None = None,
    approval_path: Path | str | None = None,
    output_path: Path | str | None = None,
) -> dict[str, Any]:
    html_text = render_gate2_briefing(
        draft,
        approval,
        request_draft_path=request_draft_path,
        approval_path=approval_path,
        output_path=output_path,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_text, encoding="utf-8")
    binding = briefing_binding(draft, approval)
    return {
        **binding.to_dict(),
        "briefingPath": str(path),
        "briefingDigest": canonical_fingerprint({"html": html_text}),
    }


def extract_briefing_metadata(html_text: str) -> dict[str, str]:
    parser = _MetaParser()
    parser.feed(html_text)
    return dict(parser.metadata)


def verify_gate2_briefing(
    html_text: str,
    draft: RequestDraft,
    approval: ApprovalRecord | Mapping[str, Any],
) -> dict[str, Any]:
    metadata = extract_briefing_metadata(html_text)
    approval_mapping = _approval_mapping(approval)
    expected = briefing_binding(draft, approval_mapping)
    checks = {
        "requestId": (metadata.get("ahra-request-id"), expected.request_id),
        "approvalId": (metadata.get("ahra-approval-id"), expected.approval_id),
        "requestDigest": (metadata.get("ahra-request-digest"), expected.request_digest),
    }
    mismatches = [
        {"field": field, "actual": actual or "", "expected": wanted}
        for field, (actual, wanted) in checks.items()
        if actual != wanted
    ]
    serialized_request_digest = approval_mapping.get("requestDigest")
    serialized_request_id = approval_mapping.get("requestId")
    serialized_approval_id = approval_mapping.get("approvalId")
    if serialized_request_id != expected.request_id:
        mismatches.append(
            {
                "field": "approval.requestId",
                "actual": str(serialized_request_id or ""),
                "expected": expected.request_id,
            }
        )
    if serialized_approval_id != expected.approval_id:
        mismatches.append(
            {
                "field": "approval.approvalId",
                "actual": str(serialized_approval_id or ""),
                "expected": expected.approval_id,
            }
        )
    if serialized_request_digest and serialized_request_digest != expected.request_digest:
        mismatches.append(
            {
                "field": "approval.requestDigest",
                "actual": str(serialized_request_digest),
                "expected": expected.request_digest,
            }
        )
    if mismatches:
        raise ValueError(f"Gate 2 briefing binding mismatch: {mismatches}")
    return {
        **expected.to_dict(),
        "metadata": metadata,
    }


def _approval_mapping(approval: ApprovalRecord | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(approval, ApprovalRecord):
        return approval.to_dict()
    return approval


def _allowed_write_scope(draft: RequestDraft) -> tuple[str, ...]:
    resources: set[str] = set()
    for node in draft.plan_draft.nodes:
        for request in node.capability_requests:
            if request.capability == "filesystem.write":
                resources.update(request.resources)
    if not resources:
        return ("No filesystem.write resources are requested.",)
    return tuple(sorted(resources))


def _unauthorized_scope(draft: RequestDraft, allowed_write_scope: tuple[str, ...]) -> tuple[str, ...]:
    return (
        "Any filesystem path not listed in the allowed write scope.",
        "Any capability not listed in RequestDraft.spec.registry.allowedCapabilities: "
        + ", ".join(draft.allowed_capabilities),
        "Any top-level objective, claim, plan node, or output not present in the RequestDraft.",
    )


def _non_goals(unauthorized_scope: tuple[str, ...]) -> tuple[str, ...]:
    return (
        "Do not expand the request beyond the RequestDraft goal and required claims.",
        "Do not start Workflow B until Gate 2 authorization freezes the GoalExecutionRequest.",
        *unauthorized_scope,
    )


def _node_table(draft: RequestDraft) -> str:
    rows = [
        "<tr><th>Node</th><th>Type</th><th>Claims</th><th>Gates</th><th>Capabilities</th></tr>",
    ]
    for node in draft.plan_draft.nodes:
        capabilities = [
            request.capability + ": " + ", ".join(request.resources)
            for request in node.capability_requests
        ]
        rows.append(
            "<tr>"
            f"<td>{_e(node.node_id)}</td>"
            f"<td>{_e(node.node_type)}</td>"
            f"<td>{_e(', '.join(node.claim_refs) or 'none')}</td>"
            f"<td>{_e(', '.join(node.gate_refs) or 'none')}</td>"
            f"<td>{_e('; '.join(capabilities) or 'none')}</td>"
            "</tr>"
        )
    return "<table>" + "".join(rows) + "</table>"


def _claim_table(draft: RequestDraft, claim_ids_by_node: set[str]) -> str:
    rows = [
        "<tr><th>Claim</th><th>Type</th><th>Criteria</th><th>Required</th><th>Plan coverage</th></tr>",
    ]
    for claim in draft.claim_graph.claims:
        rows.append(
            "<tr>"
            f"<td>{_e(claim.claim_id)}</td>"
            f"<td>{_e(claim.claim_type.value)}</td>"
            f"<td>{_e(', '.join(claim.criterion_refs))}</td>"
            f"<td>{_e(str(claim.required))}</td>"
            f"<td>{_e('covered' if claim.claim_id in claim_ids_by_node else 'not covered')}</td>"
            "</tr>"
        )
    return "<table>" + "".join(rows) + "</table>"


def _list(items: tuple[str, ...]) -> str:
    return "<ul>" + "".join(f"<li>{_e(item)}</li>" for item in items) + "</ul>"


def _checklist(items: tuple[str, ...]) -> str:
    return "<ul>" + "".join(f'<li><label><input type="checkbox"> {_e(item)}</label></li>' for item in items) + "</ul>"


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


class _MetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.metadata: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "meta":
            return
        values = {key.lower(): value or "" for key, value in attrs}
        name = values.get("name")
        if name:
            self.metadata[name] = values.get("content", "")


__all__ = [
    "BRIEFING_SCHEMA_VERSION",
    "DEFAULT_GATE2_BRIEFING_NAME",
    "Gate2BriefingBinding",
    "briefing_binding",
    "extract_briefing_metadata",
    "plan_digest",
    "render_gate2_briefing",
    "request_digest",
    "verify_gate2_briefing",
    "write_gate2_briefing",
]
