from __future__ import annotations

import unittest

from ahra.domain import MemoryKind, MemoryScope, MemoryStatus
from ahra.memory import InMemoryMemoryStore, InvalidMemoryTransition, MemoryService


class MemoryServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = MemoryService(InMemoryMemoryStore())

    def test_model_write_is_candidate_until_promoted(self) -> None:
        item = self.service.propose(
            kind=MemoryKind.SEMANTIC,
            scope=MemoryScope(tenant_id="TEN-1", project_id="PRJ-1"),
            statement="Evidence is required for completion.",
            source_refs=("TASK-1#event-2",),
            created_by="agent@sha256:test",
            confidence=0.9,
            sensitivity="internal",
            retention_policy="project-governed",
            tags=("evidence",),
        )
        self.assertEqual(item.status, MemoryStatus.CANDIDATE)
        self.assertEqual(
            self.service.retrieve(
                tenant_id="TEN-1", project_id="PRJ-1", query="Evidence"
            ),
            [],
        )
        active = self.service.promote(item.memory_id, verifier="human:reviewer")
        self.assertEqual(active.status, MemoryStatus.ACTIVE)
        found = self.service.retrieve(
            tenant_id="TEN-1", project_id="PRJ-1", query="Evidence"
        )
        self.assertEqual([x.memory_id for x in found], [item.memory_id])

    def test_active_memory_cannot_be_promoted_again(self) -> None:
        item = self.service.propose(
            kind=MemoryKind.SEMANTIC,
            scope=MemoryScope(tenant_id="TEN-1"),
            statement="A fact",
            source_refs=("SRC-1",),
            created_by="agent@test",
            confidence=0.5,
            sensitivity="internal",
            retention_policy="short",
        )
        self.service.promote(item.memory_id, verifier="reviewer")
        with self.assertRaises(InvalidMemoryTransition):
            self.service.promote(item.memory_id, verifier="reviewer")


if __name__ == "__main__":
    unittest.main()
