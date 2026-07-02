"""Tests for TASK-0085: Request-scoped write admission for development-bounded profile."""

from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ahra.capabilities import (
    CapabilityAdmissionService,
    CapabilityRequest,
    CapabilityScope,
    RuntimeCapabilityProfile,
)
from ahra.goal_operations import (
    DEVELOPMENT_BOUNDED_PROFILE_REF,
    DEVELOPMENT_BOUNDED_WRITE_BLACKLIST,
    GoalExecutionRequest,
    GoalOperationProfile,
    GoalOperationProfileRegistry,
    GoalOperationService,
    _capability_admission_service,
)
from ahra.plan_ir import PlanBudget, PlanDraft, PlanNodeDraft, CapabilityRequest as PlanCapabilityRequest
from ahra.reference_runner.git_ops import IsolatedGitWorkspaceProvider, WorktreeManager

NOW = datetime(2026, 7, 1, 10, 0, tzinfo=UTC)


class TestBase(unittest.TestCase):
    """Base class with helper methods for all test cases."""

    def _minimal_request(self, filesystem_write_resources: list[str]) -> GoalExecutionRequest:
        """Create a minimal GoalExecutionRequest for testing."""
        plan_draft = PlanDraft(
            goal_ref="GOAL-test",
            proposed_by="planner/test",
            nodes=(
                PlanNodeDraft(
                    node_id="NODE-test",
                    node_type="bounded_task",
                    objective="Test objective",
                    claim_refs=(),
                    depends_on=(),
                    input_refs=(),
                    expected_outputs=(),
                    capability_requests=(
                        PlanCapabilityRequest(
                            capability="filesystem.write",
                            resources=tuple(filesystem_write_resources),
                        ),
                    ),
                    gate_refs=(),
                    runtime_ref=None,
                    budget=PlanBudget(max_model_calls=1, max_tool_calls=1),
                ),
            ),
        )

        return GoalExecutionRequest(
            name="test-request",
            request_id="REQ-test",
            idempotency_key="test:key",
            profile_ref=DEVELOPMENT_BOUNDED_PROFILE_REF,
            workspace_ref=Path("/tmp/workspace"),
            artifact_dir=Path("/tmp/artifacts"),
            store_kind="sqlite",
            store_path=Path("/tmp/store.db"),
            planner_adapter_ref="planner/test",
            executor_adapter_ref="executor/test",
            gate_runner_adapter_ref="gate-runner/test",
            runtime_ref="runtime/test",
            runtime_digest="sha256:test",
            goal_ref="GOAL-test",
            goal_digest="sha256:test",
            claim_graph_digest="sha256:test",
            claim_graph_ref=None,
            required_claim_refs=(),
            registered_node_types={},
            registered_gate_refs={},
            gate_definitions=(),
            registered_runtime_refs={},
            allowed_capabilities=("filesystem.write", "process.exec"),
            plan_draft=plan_draft,
            max_repair_cycles=0,
            max_concurrency=1,
            branch="main",
        )

    def _development_bounded_profile(self) -> GoalOperationProfile:
        """Get the development-bounded profile from the registry."""
        registry = GoalOperationProfileRegistry()
        return registry.get(DEVELOPMENT_BOUNDED_PROFILE_REF)


class RequestScopedWriteAdmissionTests(TestBase):
    """Test that filesystem.write allowlist is derived from planDraft for development-bounded profile."""

    def test_effective_allowlist_derived_from_plan_draft(self) -> None:
        """Verify that the effective write allowlist comes from planDraft capability requests."""
        # Create a minimal GoalExecutionRequest with specific filesystem.write resources
        request = self._minimal_request(
            filesystem_write_resources=[
                "src/ahra/workflow_a_cli.py",
                "tests/test_workflow_a_cli.py",
            ]
        )
        profile = self._development_bounded_profile()

        # Get the capability admission service
        service = _capability_admission_service(request, profile)

        # Verify that a resource in the planDraft is allowed
        decision = service.admit(
            CapabilityRequest(
                request_id="REQ-test-001",
                plan_id="PLAN-test",
                node_id="NODE-test",
                requested_by="executor",
                role="executor",
                capability="filesystem.write",
                action="filesystem.write",
                resources=("src/ahra/workflow_a_cli.py",),
                scope=(),
                risk_level="R1",
                expires_at=NOW + timedelta(hours=1),
            ),
            now=NOW,
        )
        self.assertTrue(decision.allow, f"Expected allow, got {decision.reason_code}")
        self.assertIsNotNone(decision.grant)

        # Verify that a resource NOT in the planDraft is rejected
        decision_denied = service.admit(
            CapabilityRequest(
                request_id="REQ-test-002",
                plan_id="PLAN-test",
                node_id="NODE-test",
                requested_by="executor",
                role="executor",
                capability="filesystem.write",
                action="filesystem.write",
                resources=("src/ahra/some_other_file.py",),
                scope=(),
                risk_level="R1",
                expires_at=NOW + timedelta(hours=1),
            ),
            now=NOW,
        )
        self.assertFalse(decision_denied.allow)
        self.assertIn(decision_denied.reason_code, ["privilege_widening", "runtime_write_not_allowed"])

    def test_isolated_workspace_provider_does_not_fallback_when_request_scope_empty(self) -> None:
        """Empty planDraft filesystem.write resources must produce an empty workspace allowlist."""
        request = self._minimal_request(filesystem_write_resources=[])
        profile = self._development_bounded_profile()

        provider = GoalOperationService()._real_executor_workspace_provider(request, profile)

        self.assertIsInstance(provider, IsolatedGitWorkspaceProvider)
        self.assertEqual(provider.allowed_globs, ())


class KernelBlacklistTests(TestBase):
    """Test that hardened kernel blacklist is enforced during capability admission."""

    def test_kernel_module_write_rejected(self) -> None:
        """Verify that writes to kernel modules are rejected at runtime via denied_resources."""
        # Create a hostile request that tries to write to a kernel module
        request = self._minimal_request(
            filesystem_write_resources=[
                "src/ahra/capabilities.py",  # Kernel module - should be blacklisted
                "tests/test_capabilities.py",  # Normal test - should be allowed
            ]
        )
        profile = self._development_bounded_profile()

        service = _capability_admission_service(request, profile)

        # The admission ALLOWS the request but marks kernel modules as denied_resources
        decision = service.admit(
            CapabilityRequest(
                request_id="REQ-hostile-001",
                plan_id="PLAN-hostile",
                node_id="NODE-hostile",
                requested_by="executor",
                role="executor",
                capability="filesystem.write",
                action="filesystem.write",
                resources=("src/ahra/capabilities.py", "tests/test_capabilities.py"),
                scope=(),
                risk_level="R1",
                expires_at=NOW + timedelta(hours=1),
            ),
            now=NOW,
        )
        self.assertTrue(decision.allow, "Admission should succeed with denied_resources constraint")
        self.assertIsNotNone(decision.grant)

        # Verify that the kernel module is in denied_resources
        assert decision.grant is not None
        self.assertIn("src/ahra/capabilities.py", decision.grant.denied_resources,
                     "Kernel module should be in denied_resources")

        # Verify that runtime gateway rejects writes to denied paths
        from ahra.capabilities import LocalRuntimeGateway, InMemoryAuditSink
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            gateway = LocalRuntimeGateway(Path(temp), InMemoryAuditSink())

            # Try to write to kernel module - should be rejected by runtime gateway
            audit = gateway.write_text(
                decision.grant,
                plan_id="PLAN-hostile",
                node_id="NODE-hostile",
                actor="executor",
                relative_path="src/ahra/capabilities.py",
                content="malicious content",
                now=NOW,
            )
            self.assertFalse(audit.allowed, "Runtime gateway should reject kernel module write")
            self.assertEqual(audit.reason_code, "path_blacklisted")

            # Writing to allowed path should succeed
            audit_allowed = gateway.write_text(
                decision.grant,
                plan_id="PLAN-hostile",
                node_id="NODE-hostile",
                actor="executor",
                relative_path="tests/test_capabilities.py",
                content="test content",
                now=NOW,
            )
            self.assertTrue(audit_allowed.allowed, "Allowed path write should succeed")

    def test_infrastructure_files_rejected(self) -> None:
        """Verify that writes to infrastructure files (pyproject.toml, uv.lock, etc.) are rejected at runtime."""
        blacklisted_files = [
            "pyproject.toml",
            "uv.lock",
            "Makefile",
            "scripts/check.py",
            ".github/workflows/ci.yml",
        ]

        for blacklisted_file in blacklisted_files:
            with self.subTest(file=blacklisted_file):
                request = self._minimal_request(
                    filesystem_write_resources=[blacklisted_file, "tests/test_safe.py"]
                )
                profile = self._development_bounded_profile()
                service = _capability_admission_service(request, profile)

                decision = service.admit(
                    CapabilityRequest(
                        request_id=f"REQ-hostile-{blacklisted_file}",
                        plan_id="PLAN-hostile",
                        node_id="NODE-hostile",
                        requested_by="executor",
                        role="executor",
                        capability="filesystem.write",
                        action="filesystem.write",
                        resources=(blacklisted_file, "tests/test_safe.py"),
                        scope=(),
                        risk_level="R1",
                        expires_at=NOW + timedelta(hours=1),
                    ),
                    now=NOW,
                )

                # Admission should succeed but include denied_resources
                self.assertTrue(decision.allow, f"Admission for {blacklisted_file} should succeed with constraints")
                self.assertIsNotNone(decision.grant)
                assert decision.grant is not None

                # Verify the blacklisted file is in denied_resources
                # Check if the file matches any pattern in denied_resources
                from ahra.capabilities import _resource_allowed
                is_denied = _resource_allowed(blacklisted_file, decision.grant.denied_resources)
                self.assertTrue(is_denied, f"{blacklisted_file} should match a denied_resources pattern")

                # Verify runtime gateway rejects the write
                from ahra.capabilities import LocalRuntimeGateway, InMemoryAuditSink
                import tempfile
                with tempfile.TemporaryDirectory() as temp:
                    gateway = LocalRuntimeGateway(Path(temp), InMemoryAuditSink())
                    audit = gateway.write_text(
                        decision.grant,
                        plan_id="PLAN-hostile",
                        node_id="NODE-hostile",
                        actor="executor",
                        relative_path=blacklisted_file,
                        content="malicious content",
                        now=NOW,
                    )
                    self.assertFalse(audit.allowed, f"Runtime gateway should reject {blacklisted_file}")
                    self.assertEqual(audit.reason_code, "path_blacklisted")


class IsolatedWorkspaceDeletePropagationTests(TestBase):
    """Test that IsolatedGitWorkspaceProvider only propagates deletions for allowed paths."""

    def test_deletion_propagation_for_allowed_paths(self) -> None:
        """Verify that file deletions in allowed paths are propagated back to source."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            # Create a source repo with test files
            source_repo = root / "source"
            source_repo.mkdir()
            self._init_git_repo(source_repo)
            (source_repo / "allowed_file.py").write_text("content", encoding="utf-8")
            (source_repo / "denied_file.py").write_text("content", encoding="utf-8")
            self._git_commit(source_repo, "Add test files")

            # Create isolated workspace provider with specific allowlist
            provider = IsolatedGitWorkspaceProvider(
                worktree_root=root / "worktrees",
                allowed_globs=("allowed_file.py",),
                denied_globs=("denied_file.py",),
            )

            # Prepare execution workspace
            execution_ref = provider.prepare_execution_workspace(
                str(source_repo),
                run_id="RUN-test-delete",
                node_id="NODE-test",
            )

            # Delete both files in the execution workspace
            execution_path = Path(execution_ref)
            (execution_path / "allowed_file.py").unlink()
            (execution_path / "denied_file.py").unlink()

            # Commit changes (this propagates to source)
            provider.commit_all(execution_ref, "Delete files")

            # Clean up
            provider.finalize_execution_workspace(execution_ref)

            # Verify: allowed_file.py should be deleted from source
            self.assertFalse((source_repo / "allowed_file.py").exists(), "Allowed file deletion should propagate")

            # Verify: denied_file.py should still exist in source
            self.assertTrue((source_repo / "denied_file.py").exists(), "Denied file deletion should NOT propagate")

    def test_rename_propagation_respects_allowlist(self) -> None:
        """Verify that renames (delete old + create new) respect the allowlist."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            # Create a source repo
            source_repo = root / "source"
            source_repo.mkdir()
            self._init_git_repo(source_repo)
            (source_repo / "old_name.py").write_text("content", encoding="utf-8")
            self._git_commit(source_repo, "Add test file")

            # Create isolated workspace with allowlist
            provider = IsolatedGitWorkspaceProvider(
                worktree_root=root / "worktrees",
                allowed_globs=("old_name.py", "new_name.py"),
                denied_globs=(),
            )

            execution_ref = provider.prepare_execution_workspace(
                str(source_repo),
                run_id="RUN-test-rename",
                node_id="NODE-test",
            )

            # Rename file (delete old, create new)
            execution_path = Path(execution_ref)
            (execution_path / "old_name.py").unlink()
            (execution_path / "new_name.py").write_text("content", encoding="utf-8")

            # Commit changes
            provider.commit_all(execution_ref, "Rename file")
            provider.finalize_execution_workspace(execution_ref)

            # Verify both operations propagated
            self.assertFalse((source_repo / "old_name.py").exists(), "Old file should be deleted")
            self.assertTrue((source_repo / "new_name.py").exists(), "New file should be created")

    def _init_git_repo(self, repo: Path) -> None:
        """Initialize a git repository."""
        import subprocess
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=repo,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.invalid"],
            cwd=repo,
            check=True,
        )

    def _git_commit(self, repo: Path, message: str) -> None:
        """Commit all changes in the repo."""
        import subprocess
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", message], cwd=repo, check=True)


if __name__ == "__main__":
    unittest.main()
