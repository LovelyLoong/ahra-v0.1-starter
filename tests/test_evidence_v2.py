from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ahra.evidence_v2 import (
    DigestRef,
    EvidenceEnvironment,
    EvidenceInvalidationTrigger,
    EvidenceRegistry,
    EvidenceResult,
    EvidenceV2,
    EvidenceValidityState,
    GateRunV2,
    adapt_legacy_evidence_manifest,
    canonical_fingerprint,
    make_status_event,
)


ROOT = Path(__file__).resolve().parents[1]
D1 = "sha256:" + "1" * 64
D2 = "sha256:" + "2" * 64
D3 = "sha256:" + "3" * 64
D4 = "sha256:" + "4" * 64
D5 = "sha256:" + "5" * 64
D6 = "sha256:" + "6" * 64
D7 = "sha256:" + "7" * 64
D8 = "sha256:" + "8" * 64
D9 = "sha256:" + "9" * 64


class EvidenceV2Tests(unittest.TestCase):
    def test_canonical_fingerprint_is_stable_for_map_ordering(self) -> None:
        left = {"b": [2, 1], "a": {"d": D4, "c": D3}}
        right = {"a": {"c": D3, "d": D4}, "b": [2, 1]}

        self.assertEqual(canonical_fingerprint(left), canonical_fingerprint(right))

    def test_direct_subject_digest_change_marks_stale(self) -> None:
        evidence = _evidence()
        trigger = EvidenceInvalidationTrigger(changed_refs={"ART-cli": D9})

        inspected = EvidenceRegistry((evidence,)).inspect("EVD-direct", trigger)

        self.assertEqual(inspected.state, EvidenceValidityState.STALE)
        self.assertIn("digest_changed:ART-cli", inspected.reasons)

    def test_transitive_evidence_dependency_marks_downstream_stale(self) -> None:
        upstream = _evidence(evidence_id="EVD-upstream", subject_ref="ART-cli")
        downstream = _evidence(
            evidence_id="EVD-downstream",
            subject_ref="ART-report",
            dependencies=(DigestRef("EVD-upstream", upstream.fingerprint()),),
        )
        trigger = EvidenceInvalidationTrigger(changed_refs={"ART-cli": D9})

        inspected = EvidenceRegistry((upstream, downstream)).inspect_all(trigger)

        self.assertEqual(inspected["EVD-upstream"].state, EvidenceValidityState.STALE)
        self.assertEqual(inspected["EVD-downstream"].state, EvidenceValidityState.STALE)
        self.assertIn("dependency_evidence_not_current:EVD-upstream", inspected["EVD-downstream"].reasons)

    def test_unrelated_artifact_change_does_not_invalidate_complete_evidence(self) -> None:
        evidence = _evidence()
        trigger = EvidenceInvalidationTrigger(changed_refs={"ART-unrelated": D9})

        inspected = EvidenceRegistry((evidence,)).inspect("EVD-direct", trigger)

        self.assertTrue(inspected.current)
        self.assertEqual(inspected.state, EvidenceValidityState.CURRENT)

    def test_incomplete_dependency_scope_invalidates_conservatively(self) -> None:
        evidence = _evidence(dependency_scope_complete=False)
        trigger = EvidenceInvalidationTrigger(changed_refs={"ART-unrelated": D9})

        inspected = EvidenceRegistry((evidence,)).inspect("EVD-direct", trigger)

        self.assertEqual(inspected.state, EvidenceValidityState.STALE)
        self.assertIn("dependency_scope_incomplete", inspected.reasons)

    def test_policy_gate_runtime_test_and_verifier_changes_mark_stale(self) -> None:
        evidence = _evidence()
        triggers = [
            EvidenceInvalidationTrigger(policy_digest=D9),
            EvidenceInvalidationTrigger(changed_gate_refs=frozenset({"GATE-unit"})),
            EvidenceInvalidationTrigger(runtime_profile_digest=D9),
            EvidenceInvalidationTrigger(test_definition_digest=D9),
            EvidenceInvalidationTrigger(verifier_release_digest=D9),
        ]

        for trigger in triggers:
            with self.subTest(trigger=trigger):
                inspected = EvidenceRegistry((evidence,)).inspect("EVD-direct", trigger)
                self.assertEqual(inspected.state, EvidenceValidityState.STALE)

    def test_ttl_revocation_and_contradiction_are_distinct(self) -> None:
        now = datetime(2026, 6, 25, tzinfo=UTC)
        expired = _evidence(valid_until=now - timedelta(seconds=1))
        registry = EvidenceRegistry((expired,))

        self.assertEqual(
            registry.inspect("EVD-direct", EvidenceInvalidationTrigger(now=now)).state,
            EvidenceValidityState.EXPIRED,
        )
        self.assertEqual(
            registry.inspect(
                "EVD-direct",
                EvidenceInvalidationTrigger(revoked_evidence_refs=frozenset({"EVD-direct"})),
            ).state,
            EvidenceValidityState.REVOKED,
        )
        self.assertEqual(
            registry.inspect(
                "EVD-direct",
                EvidenceInvalidationTrigger(contradicted_evidence_refs=frozenset({"EVD-direct"})),
            ).state,
            EvidenceValidityState.CONTRADICTED,
        )

    def test_status_event_records_supersession_without_mutating_evidence(self) -> None:
        event = make_status_event(
            event_id="EVT-EVD-direct-stale",
            evidence_ref="EVD-direct",
            from_state=EvidenceValidityState.CURRENT,
            to_state=EvidenceValidityState.STALE,
            reason="subject digest changed",
            occurred_at=datetime(2026, 6, 25, tzinfo=UTC),
            superseded_by="EVD-rerun",
        ).to_dict()

        self.assertEqual(event["spec"]["fromState"], "current")
        self.assertEqual(event["spec"]["toState"], "stale")
        self.assertEqual(event["spec"]["supersededBy"], "EVD-rerun")

    def test_legacy_manifest_adapter_labels_records_as_partial(self) -> None:
        manifest = json.loads((ROOT / "work/tasks/TASK-0023/evidence-manifest.json").read_text(encoding="utf-8"))

        legacy = adapt_legacy_evidence_manifest(manifest)

        self.assertGreater(len(legacy), 0)
        self.assertEqual(legacy[0].status, "legacy_partial")
        self.assertIn("lacks full v2 fingerprint bindings", legacy[0].reason)

    def test_example_document_can_round_trip_to_evidence_object(self) -> None:
        data = json.loads((ROOT / "examples/records/evidence-v2.json").read_text(encoding="utf-8"))

        evidence = EvidenceV2.from_mapping(data)

        self.assertEqual(evidence.evidence_id, "EVD-doc-staleness-unit")
        self.assertTrue(evidence.fingerprint().startswith("sha256:"))

    def test_gate_run_document_binds_digests_and_validity(self) -> None:
        data = json.loads((ROOT / "examples/records/gate-run-v2.json").read_text(encoding="utf-8"))

        gate_run = GateRunV2.from_mapping(data)

        self.assertEqual(gate_run.gate_run_id, "GATERUN-doc-staleness-unit")
        self.assertEqual(gate_run.validity_state, EvidenceValidityState.CURRENT)
        self.assertEqual(gate_run.subjects[0].digest, D2)
        self.assertEqual(gate_run.dependencies[0].digest, D3)
        self.assertEqual(gate_run.environment.policy_digest, D5)
        self.assertTrue(gate_run.fingerprint().startswith("sha256:"))
        self.assertEqual(gate_run.stored_fingerprint, gate_run.fingerprint())


def _evidence(
    *,
    evidence_id: str = "EVD-direct",
    subject_ref: str = "ART-cli",
    dependencies: tuple[DigestRef, ...] = (DigestRef("ART-schema", D3),),
    dependency_scope_complete: bool = True,
    valid_until: datetime | None = None,
) -> EvidenceV2:
    return EvidenceV2(
        evidence_id=evidence_id,
        claim_refs=("CLAIM-cli-detects-stale-docs",),
        gate_ref="GATE-unit@sha256:" + "1" * 64,
        gate_definition_digest=D1,
        gate_run_id="GATERUN-unit",
        result=EvidenceResult.PASSED,
        confidence="verified",
        subjects=(DigestRef(subject_ref, D2),),
        dependencies=dependencies,
        environment=EvidenceEnvironment(
            runtime_profile_digest=D4,
            policy_digest=D5,
            verifier_release_digest=D6,
            test_definition_digest=D7,
            relevant_environment_digest=D8,
        ),
        valid_until=valid_until,
        dependency_scope_complete=dependency_scope_complete,
    )


if __name__ == "__main__":
    unittest.main()
