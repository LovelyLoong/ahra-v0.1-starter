from __future__ import annotations

import fnmatch
import os
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Iterable, Mapping

from .evidence_v2 import canonical_fingerprint


REFERENCE_MONITOR_VERSION = "ahra-reference-monitor/0.1"
HIGH_RISK_ACTIONS = {"network.access", "secret.read", "external.write", "production.deploy"}
SUPPORTED_LOCAL_ACTIONS = {"filesystem.write", "process.exec", "spawn.agent", "network.access"}
DEFAULT_WRITE_DENY_ROLES = {"planner", "task_reviewer", "goal_reviewer", "verifier"}
COMMAND_META_CHARS = ("&&", "||", "|", "$(", "`", ">", "<", "\n", "\r")


@dataclass(frozen=True, slots=True)
class CapabilityRequest:
    request_id: str
    plan_id: str
    node_id: str
    requested_by: str
    role: str
    capability: str
    action: str
    resources: tuple[str, ...]
    scope: tuple[str, ...]
    risk_level: str
    expires_at: datetime
    approval_refs: tuple[str, ...] = ()
    spawn_limit: int = 0

    def normalized(self) -> "CapabilityRequest":
        return CapabilityRequest(
            request_id=self.request_id,
            plan_id=self.plan_id,
            node_id=self.node_id,
            requested_by=self.requested_by,
            role=self.role,
            capability=self.capability,
            action=self.action,
            resources=tuple(sorted(set(self.resources))),
            scope=tuple(sorted(set(self.scope))),
            risk_level=self.risk_level,
            expires_at=self.expires_at,
            approval_refs=tuple(sorted(set(self.approval_refs))),
            spawn_limit=self.spawn_limit,
        )

    def to_dict(self) -> dict:
        request = self.normalized()
        return {
            "apiVersion": "ahra.dev/v1alpha1",
            "kind": "CapabilityRequest",
            "metadata": {
                "requestId": request.request_id,
                "planId": request.plan_id,
                "nodeId": request.node_id,
                "requestedBy": request.requested_by,
                "role": request.role,
            },
            "spec": {
                "capability": request.capability,
                "action": request.action,
                "resources": list(request.resources),
                "scope": list(request.scope),
                "riskLevel": request.risk_level,
                "expiresAt": _iso(request.expires_at),
                "approvalRefs": list(request.approval_refs),
                "spawnLimit": request.spawn_limit,
            },
        }


@dataclass(frozen=True, slots=True)
class CapabilityGrant:
    grant_id: str
    request_id: str
    plan_id: str
    node_id: str
    role: str
    capability: str
    action: str
    resources: tuple[str, ...]
    scope: tuple[str, ...]
    expires_at: datetime
    issued_at: datetime
    issuer: str
    policy_decision_id: str
    approval_refs: tuple[str, ...] = ()
    spawn_limit: int = 0
    superseded_by: str | None = None
    denied_resources: tuple[str, ...] = ()

    def fingerprint_payload(self) -> dict:
        return {
            "action": self.action,
            "approvalRefs": sorted(self.approval_refs),
            "capability": self.capability,
            "expiresAt": _iso(self.expires_at),
            "grantId": self.grant_id,
            "issuedAt": _iso(self.issued_at),
            "issuer": self.issuer,
            "nodeId": self.node_id,
            "planId": self.plan_id,
            "policyDecisionId": self.policy_decision_id,
            "requestId": self.request_id,
            "resources": sorted(self.resources),
            "role": self.role,
            "scope": sorted(self.scope),
            "spawnLimit": self.spawn_limit,
            "supersededBy": self.superseded_by,
            "deniedResources": sorted(self.denied_resources),
        }

    def digest(self) -> str:
        return canonical_fingerprint(self.fingerprint_payload())

    def current_at(self, now: datetime) -> bool:
        return self.expires_at > now and self.superseded_by is None

    def to_dict(self) -> dict:
        return {
            "apiVersion": "ahra.dev/v1alpha1",
            "kind": "CapabilityGrant",
            "metadata": {
                "grantId": self.grant_id,
                "requestId": self.request_id,
                "planId": self.plan_id,
                "nodeId": self.node_id,
                "digest": self.digest(),
            },
            "spec": {
                "role": self.role,
                "capability": self.capability,
                "action": self.action,
                "resources": list(self.resources),
                "scope": list(self.scope),
                "expiresAt": _iso(self.expires_at),
                "issuedAt": _iso(self.issued_at),
                "issuer": self.issuer,
                "policyDecisionId": self.policy_decision_id,
                "approvalRefs": list(self.approval_refs),
                "spawnLimit": self.spawn_limit,
                "supersededBy": self.superseded_by,
                **({"deniedResources": list(self.denied_resources)} if self.denied_resources else {}),
            },
        }


@dataclass(frozen=True, slots=True)
class CapabilityScope:
    allowed_actions: Mapping[str, tuple[str, ...]]
    allowed_roles_by_action: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    max_spawn_limit: int = 0


@dataclass(frozen=True, slots=True)
class RuntimeCapabilityProfile:
    runtime_ref: str
    supported_actions: frozenset[str]
    allowed_write_paths: tuple[str, ...] = ()
    denied_write_paths: tuple[str, ...] = ()
    allowed_commands: tuple[str, ...] = ()
    allowed_network_egress: tuple[str, ...] = ()
    local_profile: bool = True


@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    decision_id: str
    allow: bool
    reason_code: str
    approval_required: bool
    policy_version: str
    decided_at: datetime
    grant: CapabilityGrant | None = None

    def to_dict(self) -> dict:
        return {
            "decisionId": self.decision_id,
            "allow": self.allow,
            "reasonCode": self.reason_code,
            "approvalRequired": self.approval_required,
            "policyVersion": self.policy_version,
            "decidedAt": _iso(self.decided_at),
            "grantRef": self.grant.grant_id if self.grant else None,
            "grantDigest": self.grant.digest() if self.grant else None,
        }


class CapabilityAdmissionService:
    def __init__(
        self,
        *,
        goal_scope: CapabilityScope,
        policy_scope: CapabilityScope | None = None,
        runtime_profile: RuntimeCapabilityProfile,
        policy_version: str = REFERENCE_MONITOR_VERSION,
        issuer: str = "harness:capability-admission",
    ) -> None:
        self.goal_scope = goal_scope
        self.policy_scope = policy_scope or goal_scope
        self.runtime_profile = runtime_profile
        self.policy_version = policy_version
        self.issuer = issuer

    def admit(self, request: CapabilityRequest, *, now: datetime | None = None) -> AdmissionDecision:
        now = now or _now()
        request = request.normalized()
        approval_required = request.risk_level in {"R2", "R3"} or request.action in HIGH_RISK_ACTIONS
        reason = self._deny_reason(request, approval_required, now)
        allow = reason == "allow"
        decision_id = f"PDEC-{uuid.uuid4()}"
        grant = None
        if allow:
            goal_allowed = self.goal_scope.allowed_actions.get(request.action, ())
            policy_allowed = self.policy_scope.allowed_actions.get(request.action, ())
            runtime_allowed = ()
            if request.action == "filesystem.write":
                runtime_allowed = _unique_refs((*self.runtime_profile.allowed_write_paths, *self.runtime_profile.denied_write_paths))
            elif request.action == "process.exec":
                runtime_allowed = self.runtime_profile.allowed_commands
            elif request.action == "network.access":
                runtime_allowed = self.runtime_profile.allowed_network_egress
            resources = _narrow_resources(
                request.resources,
                goal_allowed,
                policy_allowed,
                runtime_allowed,
            )
            grant = CapabilityGrant(
                grant_id=f"CGRANT-{uuid.uuid4()}",
                request_id=request.request_id,
                plan_id=request.plan_id,
                node_id=request.node_id,
                role=request.role,
                capability=request.capability,
                action=request.action,
                resources=resources,
                scope=tuple(sorted(item for item in request.scope if _resource_allowed(item, goal_allowed) and _resource_allowed(item, policy_allowed))),
                expires_at=request.expires_at,
                issued_at=now,
                issuer=self.issuer,
                policy_decision_id=decision_id,
                approval_refs=request.approval_refs,
                spawn_limit=request.spawn_limit,
                denied_resources=(
                    tuple(sorted(set(self.runtime_profile.denied_write_paths)))
                    if request.action == "filesystem.write"
                    else ()
                ),
            )
        return AdmissionDecision(
            decision_id=decision_id,
            allow=allow,
            reason_code=reason,
            approval_required=approval_required,
            policy_version=self.policy_version,
            decided_at=now,
            grant=grant,
        )

    def _deny_reason(self, request: CapabilityRequest, approval_required: bool, now: datetime) -> str:
        if request.expires_at <= now:
            return "request_expired"
        if request.action in HIGH_RISK_ACTIONS and request.action not in SUPPORTED_LOCAL_ACTIONS:
            return "unsupported_high_risk_capability"
        if request.action not in self.runtime_profile.supported_actions:
            return "runtime_unsupported"
        if approval_required and not request.approval_refs:
            return "approval_required"
        goal_roles = set(self.goal_scope.allowed_roles_by_action.get(request.action, ("executor",)))
        policy_roles = set(self.policy_scope.allowed_roles_by_action.get(request.action, ("executor",)))
        if request.role not in goal_roles or request.role not in policy_roles:
            return "role_not_allowed"
        if request.action == "filesystem.write" and request.role in DEFAULT_WRITE_DENY_ROLES:
            return "role_not_allowed"
        if request.action == "spawn.agent" and request.spawn_limit > min(self.goal_scope.max_spawn_limit, self.policy_scope.max_spawn_limit):
            return "spawn_limit_exceeded"
        goal_allowed = self.goal_scope.allowed_actions.get(request.action)
        if not goal_allowed:
            return "capability_not_in_goal_scope"
        policy_allowed = self.policy_scope.allowed_actions.get(request.action)
        if not policy_allowed:
            return "capability_not_in_policy_scope"
        if not _resources_within_scope(request.resources, goal_allowed):
            return "privilege_widening"
        if not _resources_within_scope(request.resources, policy_allowed):
            return "privilege_widening"
        if (
            request.action == "filesystem.write"
            and self.runtime_profile.allowed_write_paths
            and not _resources_within_scope(
                request.resources,
                _unique_refs((*self.runtime_profile.allowed_write_paths, *self.runtime_profile.denied_write_paths)),
            )
        ):
            return "runtime_write_not_allowed"
        if request.action == "process.exec" and not _resources_within_scope(request.resources, self.runtime_profile.allowed_commands):
            return "undeclared_command"
        if request.action == "network.access" and not _resources_within_scope(request.resources, self.runtime_profile.allowed_network_egress):
            return "runtime_egress_not_allowed"
        return "allow"


@dataclass(frozen=True, slots=True)
class CapabilityAuditRecord:
    audit_id: str
    plan_id: str
    node_id: str
    actor: str
    action: str
    allowed: bool
    reason_code: str
    policy_decision_id: str | None
    grant_digest: str | None
    argument_digest: str
    result_digest: str | None
    occurred_at: datetime
    resource_scope: tuple[str, ...] = ()
    evidence_summary: Mapping[str, object] | None = None

    def to_dict(self) -> dict:
        spec = {
            "planId": self.plan_id,
            "nodeId": self.node_id,
            "actor": self.actor,
            "action": self.action,
            "allowed": self.allowed,
            "reasonCode": self.reason_code,
            "policyDecisionId": self.policy_decision_id,
            "grantDigest": self.grant_digest,
            "argumentDigest": self.argument_digest,
            "resultDigest": self.result_digest,
        }
        if self.resource_scope:
            spec["resourceScope"] = list(self.resource_scope)
        if self.evidence_summary is not None:
            spec["evidenceSummary"] = dict(self.evidence_summary)
        return {
            "apiVersion": "ahra.dev/v1alpha1",
            "kind": "CapabilityAuditRecord",
            "metadata": {
                "auditId": self.audit_id,
                "occurredAt": _iso(self.occurred_at),
            },
            "spec": spec,
        }


class InMemoryAuditSink:
    def __init__(self) -> None:
        self.records: list[CapabilityAuditRecord] = []

    def append(self, record: CapabilityAuditRecord) -> None:
        self.records.append(record)


CommandRunner = Callable[[tuple[str, ...]], Mapping[str, object]]


class LocalRuntimeGateway:
    def __init__(self, workspace_root: Path, audit_sink: InMemoryAuditSink | None = None) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.audit_sink = audit_sink or InMemoryAuditSink()

    def write_text(
        self,
        grant: CapabilityGrant,
        *,
        plan_id: str,
        node_id: str,
        actor: str,
        relative_path: str,
        content: str,
        now: datetime | None = None,
    ) -> CapabilityAuditRecord:
        now = now or _now()
        args = {"relativePath": relative_path, "contentDigest": _digest_text(content)}
        reason = self._grant_denial(grant, "filesystem.write", plan_id, node_id, actor, now)
        target = self._resolve_target(relative_path)
        if reason == "allow" and target is None:
            reason = "path_escape"
        if reason == "allow" and _resource_allowed(relative_path.replace("\\", "/"), grant.denied_resources):
            reason = "path_blacklisted"
        if reason == "allow" and not _resource_allowed(relative_path.replace("\\", "/"), grant.resources):
            reason = "path_not_granted"
        if reason == "allow":
            assert target is not None
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return self._audit(grant, plan_id, node_id, actor, "filesystem.write", True, "allow", args, {"sha256": _hash_bytes(content.encode("utf-8"))}, now)
        return self._audit(grant, plan_id, node_id, actor, "filesystem.write", False, reason, args, None, now)

    def authorize_write_path(
        self,
        grant: CapabilityGrant,
        *,
        plan_id: str,
        node_id: str,
        actor: str,
        relative_path: str,
        now: datetime | None = None,
    ) -> CapabilityAuditRecord:
        now = now or _now()
        args = {"relativePath": relative_path, "operation": "authorize"}
        reason = self._grant_denial(grant, "filesystem.write", plan_id, node_id, actor, now)
        target = self._resolve_target(relative_path)
        if reason == "allow" and target is None:
            reason = "path_escape"
        if reason == "allow" and _resource_allowed(relative_path.replace("\\", "/"), grant.denied_resources):
            reason = "path_blacklisted"
        if reason == "allow" and not _resource_allowed(relative_path.replace("\\", "/"), grant.resources):
            reason = "path_not_granted"
        if reason == "allow":
            return self._audit(grant, plan_id, node_id, actor, "filesystem.write", True, "allow", args, {"authorized": True}, now)
        return self._audit(grant, plan_id, node_id, actor, "filesystem.write", False, reason, args, None, now)

    def run_command(
        self,
        grant: CapabilityGrant,
        *,
        plan_id: str,
        node_id: str,
        actor: str,
        command: tuple[str, ...],
        now: datetime | None = None,
        runner: CommandRunner | None = None,
    ) -> CapabilityAuditRecord:
        now = now or _now()
        command_text = " ".join(command)
        args = {"command": list(command)}
        reason = self._grant_denial(grant, "process.exec", plan_id, node_id, actor, now)
        if reason == "allow" and any(token in command_text for token in COMMAND_META_CHARS):
            reason = "command_substitution_denied"
        if reason == "allow" and command_text not in grant.resources:
            reason = "command_not_granted"
        if reason == "allow":
            result = dict(runner(command) if runner else _default_runner(command))
            return self._audit(grant, plan_id, node_id, actor, "process.exec", True, "allow", args, result, now)
        return self._audit(grant, plan_id, node_id, actor, "process.exec", False, reason, args, None, now)

    def record_network_access(
        self,
        grant: CapabilityGrant | None,
        *,
        plan_id: str,
        node_id: str,
        actor: str,
        resource: str,
        request_summary: Mapping[str, object],
        response_summary: Mapping[str, object] | None = None,
        now: datetime | None = None,
    ) -> CapabilityAuditRecord:
        now = now or _now()
        args = {
            "resource": resource,
            "requestSummaryDigest": canonical_fingerprint(dict(request_summary)),
        }
        result = {
            "resource": resource,
            "requestSummary": dict(request_summary),
            "responseSummary": dict(response_summary or {}),
        }
        if grant is None:
            return self._audit_without_grant(
                plan_id,
                node_id,
                actor,
                "network.access",
                False,
                "missing_grant",
                args,
                None,
                now,
                resource_scope=(resource,),
                evidence_summary=result,
            )
        reason = self._grant_denial(grant, "network.access", plan_id, node_id, actor, now)
        if reason == "allow" and not _resource_allowed(resource, grant.resources):
            reason = "resource_not_granted"
        if reason == "allow":
            return self._audit(
                grant,
                plan_id,
                node_id,
                actor,
                "network.access",
                True,
                "allow",
                args,
                result,
                now,
                resource_scope=(resource,),
                evidence_summary=result,
            )
        return self._audit(
            grant,
            plan_id,
            node_id,
            actor,
            "network.access",
            False,
            reason,
            args,
            None,
            now,
            resource_scope=(resource,),
            evidence_summary=result,
        )

    def _grant_denial(
        self,
        grant: CapabilityGrant,
        action: str,
        plan_id: str,
        node_id: str,
        actor: str,
        now: datetime,
    ) -> str:
        if grant.action != action:
            return "wrong_action"
        if grant.plan_id != plan_id:
            return "wrong_plan"
        if grant.node_id != node_id:
            return "wrong_node"
        if grant.role != actor:
            return "role_mismatch"
        if grant.digest() != canonical_fingerprint(grant.fingerprint_payload()):
            return "stale_grant"
        if not grant.current_at(now):
            return "stale_grant"
        return "allow"

    def _resolve_target(self, relative_path: str) -> Path | None:
        target = (self.workspace_root / relative_path).resolve()
        try:
            common = os.path.commonpath([str(self.workspace_root), str(target)])
        except ValueError:
            return None
        if common != str(self.workspace_root):
            return None
        parent = target.parent
        if parent.exists():
            try:
                real_parent = parent.resolve(strict=True)
                if os.path.commonpath([str(self.workspace_root), str(real_parent)]) != str(self.workspace_root):
                    return None
            except OSError:
                return None
        return target

    def _audit(
        self,
        grant: CapabilityGrant,
        plan_id: str,
        node_id: str,
        actor: str,
        action: str,
        allowed: bool,
        reason_code: str,
        arguments: Mapping[str, object],
        result: Mapping[str, object] | None,
        occurred_at: datetime,
        *,
        resource_scope: tuple[str, ...] = (),
        evidence_summary: Mapping[str, object] | None = None,
    ) -> CapabilityAuditRecord:
        record = CapabilityAuditRecord(
            audit_id=f"AUD-{uuid.uuid4()}",
            plan_id=plan_id,
            node_id=node_id,
            actor=actor,
            action=action,
            allowed=allowed,
            reason_code=reason_code,
            policy_decision_id=grant.policy_decision_id,
            grant_digest=grant.digest(),
            argument_digest=canonical_fingerprint(dict(arguments)),
            result_digest=canonical_fingerprint(dict(result)) if result is not None else None,
            occurred_at=occurred_at,
            resource_scope=resource_scope,
            evidence_summary=evidence_summary,
        )
        self.audit_sink.append(record)
        return record

    def _audit_without_grant(
        self,
        plan_id: str,
        node_id: str,
        actor: str,
        action: str,
        allowed: bool,
        reason_code: str,
        arguments: Mapping[str, object],
        result: Mapping[str, object] | None,
        occurred_at: datetime,
        *,
        resource_scope: tuple[str, ...] = (),
        evidence_summary: Mapping[str, object] | None = None,
    ) -> CapabilityAuditRecord:
        record = CapabilityAuditRecord(
            audit_id=f"AUD-{uuid.uuid4()}",
            plan_id=plan_id,
            node_id=node_id,
            actor=actor,
            action=action,
            allowed=allowed,
            reason_code=reason_code,
            policy_decision_id=None,
            grant_digest=None,
            argument_digest=canonical_fingerprint(dict(arguments)),
            result_digest=canonical_fingerprint(dict(result)) if result is not None else None,
            occurred_at=occurred_at,
            resource_scope=resource_scope,
            evidence_summary=evidence_summary,
        )
        self.audit_sink.append(record)
        return record


def _resources_within_scope(resources: Iterable[str], allowed: Iterable[str]) -> bool:
    allowed_items = tuple(allowed)
    if not allowed_items:
        return False
    return all(_resource_allowed(resource, allowed_items) for resource in resources)


def _resource_allowed(resource: str, allowed: Iterable[str]) -> bool:
    normalized = resource.replace("\\", "/")
    for pattern in allowed:
        normalized_pattern = pattern.replace("\\", "/")
        if normalized == normalized_pattern or fnmatch.fnmatch(normalized, normalized_pattern):
            return True
    return False


def _narrow_resources(
    resources: Iterable[str],
    goal_allowed: Iterable[str],
    policy_allowed: Iterable[str],
    runtime_allowed: Iterable[str],
) -> tuple[str, ...]:
    runtime_items = tuple(runtime_allowed)
    return tuple(
        sorted(
            resource
            for resource in resources
            if _resource_allowed(resource, goal_allowed)
            and _resource_allowed(resource, policy_allowed)
            and (not runtime_items or _resource_allowed(resource, runtime_items))
        )
    )


def _unique_refs(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return tuple(result)


def _default_runner(command: tuple[str, ...]) -> Mapping[str, object]:
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    return {
        "returncode": result.returncode,
        "stdoutDigest": _digest_text(result.stdout),
        "stderrDigest": _digest_text(result.stderr),
    }


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _digest_text(value: str) -> str:
    return _hash_bytes(value.encode("utf-8"))


def _hash_bytes(value: bytes) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(value).hexdigest()
