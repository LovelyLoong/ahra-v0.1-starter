from __future__ import annotations

import unittest
from datetime import timedelta

from ahra.domain import Budget, RunStatus, utc_now
from ahra.orchestrator import (
    InMemoryRunStore,
    InvalidTransitionError,
    LeaseConflictError,
    RunService,
    VersionConflictError,
)


class RunServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = RunService(InMemoryRunStore())
        self.run = self.service.create_run(
            task_id="TASK-1",
            context_id="CTX-1",
            attempt=1,
            agent_release="agent@sha256:test",
            budget=Budget(1.0, 10, 20, utc_now() + timedelta(minutes=10)),
        )

    def test_valid_lifecycle_and_lease(self) -> None:
        run = self.service.transition(self.run.run_id, RunStatus.ADMITTED, expected_version=0)
        run = self.service.transition(run.run_id, RunStatus.QUEUED, expected_version=1)
        run = self.service.acquire_lease(
            run.run_id, holder="worker:1", ttl_seconds=60, expected_version=2
        )
        self.assertEqual(run.lease.fencing_token, 1)
        run = self.service.transition(run.run_id, RunStatus.PROVISIONING, expected_version=3)
        run = self.service.transition(run.run_id, RunStatus.RUNNING, expected_version=4)
        run = self.service.transition(run.run_id, RunStatus.VERIFYING, expected_version=5)
        run = self.service.transition(run.run_id, RunStatus.SUCCEEDED, expected_version=6)
        self.assertTrue(run.status.terminal)
        self.assertIsNone(run.lease)

    def test_cas_rejects_stale_writer(self) -> None:
        self.service.transition(self.run.run_id, RunStatus.ADMITTED, expected_version=0)
        with self.assertRaises(VersionConflictError):
            self.service.transition(self.run.run_id, RunStatus.CANCELED, expected_version=0)

    def test_illegal_transition_is_rejected(self) -> None:
        with self.assertRaises(InvalidTransitionError):
            self.service.transition(self.run.run_id, RunStatus.SUCCEEDED, expected_version=0)

    def test_fencing_token_rejects_stale_worker(self) -> None:
        run = self.service.transition(self.run.run_id, RunStatus.ADMITTED, expected_version=0)
        run = self.service.transition(run.run_id, RunStatus.QUEUED, expected_version=1)
        run = self.service.acquire_lease(
            run.run_id, holder="worker:1", ttl_seconds=60, expected_version=2
        )
        with self.assertRaises(LeaseConflictError):
            self.service.heartbeat(
                run.run_id,
                holder="worker:1",
                fencing_token=999,
                ttl_seconds=60,
                expected_version=3,
            )


if __name__ == "__main__":
    unittest.main()
