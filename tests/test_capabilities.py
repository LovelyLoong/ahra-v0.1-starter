from __future__ import annotations

import os
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from tempfile import TemporaryDirectory
from pathlib import Path

from ahra.capabilities import (
    CapabilityAdmissionService,
    CapabilityRequest,
    CapabilityScope,
    InMemoryAuditSink,
    LocalRuntimeGateway,
    RuntimeCapabilityProfile,
)


NOW = datetime(2026, 6, 25, 10, 0, tzinfo=UTC)


class CapabilityAdmissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = CapabilityAdmissionService(
            goal_scope=CapabilityScope(
                allowed_actions={
                    "filesystem.write": ("src/**", "tests/**", "safe/*.txt"),
                    "process.exec": ("uv run python -B scripts/check.py",),
                    "spawn.agent": ("agent:reviewer",),
                },
                allowed_roles_by_action={
                    "filesystem.write": ("executor",),
                    "process.exec": ("executor",),
                    "spawn.agent": ("executor",),
                },
                max_spawn_limit=1,
            ),
            policy_scope=CapabilityScope(
                allowed_actions={
                    "filesystem.write": ("src/ahra/*.py", "safe/*.txt"),
                    "process.exec": ("uv run python -B scripts/check.py",),
                    "spawn.agent": ("agent:reviewer",),
                },
                allowed_roles_by_action={
                    "filesystem.write": ("executor",),
                    "process.exec": ("executor",),
                    "spawn.agent": ("executor",),
                },
                max_spawn_limit=1,
            ),
            runtime_profile=RuntimeCapabilityProfile(
                runtime_ref="runtime/local-test",
                supported_actions=frozenset({"filesystem.write", "process.exec", "spawn.agent", "network.access"}),
                allowed_commands=("uv run python -B scripts/check.py",),
            ),
        )

    def test_grant_cannot_be_broader_than_goal_or_policy_scope(self) -> None:
        allowed = self.service.admit(
            self._request("filesystem.write", ("src/ahra/capabilities.py",)),
            now=NOW,
        )
        self.assertTrue(allowed.allow)
        self.assertIsNotNone(allowed.grant)
        assert allowed.grant is not None
        self.assertEqual(allowed.grant.resources, ("src/ahra/capabilities.py",))

        outside_policy = self.service.admit(
            self._request("filesystem.write", ("tests/test_capabilities.py",)),
            now=NOW,
        )
        self.assertFalse(outside_policy.allow)
        self.assertEqual(outside_policy.reason_code, "privilege_widening")
        self.assertIsNone(outside_policy.grant)

    def test_planner_and_verifier_receive_no_write_grant_by_default(self) -> None:
        for role in ("planner", "verifier"):
            with self.subTest(role=role):
                decision = self.service.admit(
                    self._request("filesystem.write", ("src/ahra/capabilities.py",), role=role),
                    now=NOW,
                )
                self.assertFalse(decision.allow)
                self.assertEqual(decision.reason_code, "role_not_allowed")

    def test_admission_rejects_undeclared_command_before_grant(self) -> None:
        service = CapabilityAdmissionService(
            goal_scope=CapabilityScope(
                allowed_actions={"process.exec": ("git status",)},
                allowed_roles_by_action={"process.exec": ("executor",)},
            ),
            policy_scope=CapabilityScope(
                allowed_actions={"process.exec": ("git status",)},
                allowed_roles_by_action={"process.exec": ("executor",)},
            ),
            runtime_profile=RuntimeCapabilityProfile(
                runtime_ref="runtime/local-test",
                supported_actions=frozenset({"process.exec"}),
                allowed_commands=("uv run python -B scripts/check.py",),
            ),
        )
        decision = service.admit(
            self._request("process.exec", ("git status",)),
            now=NOW,
        )
        self.assertFalse(decision.allow)
        self.assertEqual(decision.reason_code, "undeclared_command")

    def test_unsupported_high_risk_capability_fails_closed(self) -> None:
        decision = self.service.admit(
            self._request(
                "network.access",
                ("https://example.invalid",),
                risk_level="R2",
                approval_refs=("APR-network",),
            ),
            now=NOW,
        )
        self.assertFalse(decision.allow)
        self.assertEqual(decision.reason_code, "unsupported_high_risk_capability")

    def test_spawn_limit_and_approval_absence_are_denied(self) -> None:
        spawn = self.service.admit(
            self._request("spawn.agent", ("agent:reviewer",), spawn_limit=2),
            now=NOW,
        )
        self.assertFalse(spawn.allow)
        self.assertEqual(spawn.reason_code, "spawn_limit_exceeded")

        approval = self.service.admit(
            self._request(
                "process.exec",
                ("uv run python -B scripts/check.py",),
                risk_level="R2",
                approval_refs=(),
            ),
            now=NOW,
        )
        self.assertFalse(approval.allow)
        self.assertEqual(approval.reason_code, "approval_required")

    def _request(
        self,
        action: str,
        resources: tuple[str, ...],
        *,
        role: str = "executor",
        risk_level: str = "R1",
        approval_refs: tuple[str, ...] = (),
        spawn_limit: int = 0,
    ) -> CapabilityRequest:
        return CapabilityRequest(
            request_id=f"CREQ-{action}",
            plan_id="PLAN-capability-test",
            node_id="NODE-capability-test",
            requested_by="agent:test",
            role=role,
            capability=action,
            action=action,
            resources=resources,
            scope=resources,
            risk_level=risk_level,
            expires_at=NOW + timedelta(minutes=10),
            approval_refs=approval_refs,
            spawn_limit=spawn_limit,
        )


class LocalRuntimeGatewayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.grant = CapabilityAdmissionService(
            goal_scope=CapabilityScope(
                allowed_actions={
                    "filesystem.write": ("safe/*.txt", "link/*.txt"),
                    "process.exec": ("uv run python -B scripts/check.py", "echo $(whoami)"),
                },
                allowed_roles_by_action={"filesystem.write": ("executor",), "process.exec": ("executor",)},
            ),
            runtime_profile=RuntimeCapabilityProfile(
                runtime_ref="runtime/local-test",
                supported_actions=frozenset({"filesystem.write", "process.exec"}),
                allowed_commands=("uv run python -B scripts/check.py", "echo $(whoami)"),
            ),
        ).admit(
            CapabilityRequest(
                request_id="CREQ-gateway",
                plan_id="PLAN-capability-test",
                node_id="NODE-capability-test",
                requested_by="agent:test",
                role="executor",
                capability="filesystem.write",
                action="filesystem.write",
                resources=("safe/*.txt", "link/*.txt"),
                scope=("safe/*.txt", "link/*.txt"),
                risk_level="R1",
                expires_at=NOW + timedelta(minutes=10),
            ),
            now=NOW,
        ).grant
        self.command_grant = CapabilityAdmissionService(
            goal_scope=CapabilityScope(
                allowed_actions={"process.exec": ("uv run python -B scripts/check.py", "echo $(whoami)")},
                allowed_roles_by_action={"process.exec": ("executor",)},
            ),
            runtime_profile=RuntimeCapabilityProfile(
                runtime_ref="runtime/local-test",
                supported_actions=frozenset({"process.exec"}),
                allowed_commands=("uv run python -B scripts/check.py", "echo $(whoami)"),
            ),
        ).admit(
            CapabilityRequest(
                request_id="CREQ-command",
                plan_id="PLAN-capability-test",
                node_id="NODE-capability-test",
                requested_by="agent:test",
                role="executor",
                capability="process.exec",
                action="process.exec",
                resources=("uv run python -B scripts/check.py", "echo $(whoami)"),
                scope=("uv run python -B scripts/check.py", "echo $(whoami)"),
                risk_level="R1",
                expires_at=NOW + timedelta(minutes=10),
            ),
            now=NOW,
        ).grant
        assert self.grant is not None
        assert self.command_grant is not None

    def test_allowed_and_denied_writes_emit_linked_audit_records(self) -> None:
        with TemporaryDirectory() as tmp:
            audit = InMemoryAuditSink()
            gateway = LocalRuntimeGateway(Path(tmp), audit)

            allowed = gateway.write_text(
                self.grant,
                plan_id="PLAN-capability-test",
                node_id="NODE-capability-test",
                actor="executor",
                relative_path="safe/output.txt",
                content="ok",
                now=NOW,
            )
            denied = gateway.write_text(
                self.grant,
                plan_id="PLAN-capability-test",
                node_id="NODE-capability-test",
                actor="executor",
                relative_path="safe/output.md",
                content="blocked",
                now=NOW,
            )

            self.assertTrue(allowed.allowed)
            self.assertEqual(allowed.plan_id, "PLAN-capability-test")
            self.assertEqual(allowed.node_id, "NODE-capability-test")
            self.assertEqual(allowed.policy_decision_id, self.grant.policy_decision_id)
            self.assertIsNotNone(allowed.result_digest)
            self.assertFalse(denied.allowed)
            self.assertEqual(denied.reason_code, "path_not_granted")
            self.assertEqual(denied.policy_decision_id, self.grant.policy_decision_id)
            self.assertEqual(len(audit.records), 2)
            self.assertFalse((Path(tmp) / "safe" / "output.md").exists())

    def test_path_traversal_is_blocked_before_write(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "workspace"
            root.mkdir()
            audit = InMemoryAuditSink()
            gateway = LocalRuntimeGateway(root, audit)
            record = gateway.write_text(
                self.grant,
                plan_id="PLAN-capability-test",
                node_id="NODE-capability-test",
                actor="executor",
                relative_path="../escape.txt",
                content="blocked",
                now=NOW,
            )

            self.assertFalse(record.allowed)
            self.assertEqual(record.reason_code, "path_escape")
            self.assertFalse((Path(tmp) / "escape.txt").exists())

    def test_symlink_escape_is_blocked_where_supported(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "workspace"
            outside = Path(tmp) / "outside"
            root.mkdir()
            outside.mkdir()
            link = root / "link"
            try:
                os.symlink(outside, link, target_is_directory=True)
            except (AttributeError, NotImplementedError, OSError) as exc:
                self.skipTest(f"symlink not available in this environment: {exc}")

            gateway = LocalRuntimeGateway(root, InMemoryAuditSink())
            record = gateway.write_text(
                self.grant,
                plan_id="PLAN-capability-test",
                node_id="NODE-capability-test",
                actor="executor",
                relative_path="link/escape.txt",
                content="blocked",
                now=NOW,
            )

            self.assertFalse(record.allowed)
            self.assertEqual(record.reason_code, "path_escape")
            self.assertFalse((outside / "escape.txt").exists())

    def test_command_substitution_and_undeclared_commands_are_blocked(self) -> None:
        with TemporaryDirectory() as tmp:
            gateway = LocalRuntimeGateway(Path(tmp), InMemoryAuditSink())
            called = False

            def runner(_: tuple[str, ...]) -> dict[str, object]:
                nonlocal called
                called = True
                return {"returncode": 0}

            substitution = gateway.run_command(
                self.command_grant,
                plan_id="PLAN-capability-test",
                node_id="NODE-capability-test",
                actor="executor",
                command=("echo", "$(whoami)"),
                now=NOW,
                runner=runner,
            )
            undeclared = gateway.run_command(
                self.command_grant,
                plan_id="PLAN-capability-test",
                node_id="NODE-capability-test",
                actor="executor",
                command=("git", "status"),
                now=NOW,
                runner=runner,
            )

            self.assertFalse(substitution.allowed)
            self.assertEqual(substitution.reason_code, "command_substitution_denied")
            self.assertFalse(undeclared.allowed)
            self.assertEqual(undeclared.reason_code, "command_not_granted")
            self.assertFalse(called)

    def test_stale_grant_and_role_mismatch_are_blocked(self) -> None:
        with TemporaryDirectory() as tmp:
            gateway = LocalRuntimeGateway(Path(tmp), InMemoryAuditSink())

            stale = gateway.write_text(
                replace(self.grant, superseded_by="CGRANT-new"),
                plan_id="PLAN-capability-test",
                node_id="NODE-capability-test",
                actor="executor",
                relative_path="safe/output.txt",
                content="blocked",
                now=NOW,
            )
            mismatch = gateway.write_text(
                self.grant,
                plan_id="PLAN-capability-test",
                node_id="NODE-capability-test",
                actor="planner",
                relative_path="safe/output.txt",
                content="blocked",
                now=NOW,
            )

            self.assertFalse(stale.allowed)
            self.assertEqual(stale.reason_code, "stale_grant")
            self.assertFalse(mismatch.allowed)
            self.assertEqual(mismatch.reason_code, "role_mismatch")
            self.assertFalse((Path(tmp) / "safe" / "output.txt").exists())

    def test_allowed_command_runs_and_audits_result(self) -> None:
        with TemporaryDirectory() as tmp:
            gateway = LocalRuntimeGateway(Path(tmp), InMemoryAuditSink())

            record = gateway.run_command(
                self.command_grant,
                plan_id="PLAN-capability-test",
                node_id="NODE-capability-test",
                actor="executor",
                command=("uv", "run", "python", "-B", "scripts/check.py"),
                now=NOW,
                runner=lambda _: {"returncode": 0, "stdoutDigest": "sha256:" + "0" * 64},
            )

            self.assertTrue(record.allowed)
            self.assertEqual(record.policy_decision_id, self.command_grant.policy_decision_id)
            self.assertIsNotNone(record.argument_digest)
            self.assertIsNotNone(record.result_digest)


if __name__ == "__main__":
    unittest.main()
