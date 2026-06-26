from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from ahra.domain import utc_now
from ahra.node_executor import NodeExecutionResult, NodeExecutionStatus, NodeExecutionUsage
from ahra.plan_execution import (
    NodeRunStatus,
    PlanExecutionService,
    PlanLeaseConflictError,
    PlanVersionConflictError,
)
from ahra.sqlite_control_store import (
    SQLiteControlStore,
    SQLiteControlStoreError,
    migrate_sqlite_control_store,
    recover_sqlite_control_plane,
)
from ahra.sqlite_recovery_fixture import (
    GOAL_EXECUTION_ID,
    compiled_recovery_plan,
    create_recovery_execution,
)


ROOT = Path(__file__).resolve().parents[1]


class SQLiteControlStoreTests(unittest.TestCase):
    def test_migration_round_trip_and_cas_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "control.sqlite"
            store = SQLiteControlStore(db_path)
            plan, report = compiled_recovery_plan()
            service = PlanExecutionService(store)
            goal = service.create_goal_execution(
                goal_ref=plan.goal_ref,
                goal_digest=plan.goal_digest,
                claim_graph_digest=plan.claim_graph_digest,
                goal_execution_id=GOAL_EXECUTION_ID,
            )
            execution = service.start_execution(
                plan,
                report,
                goal_execution_ref=goal.goal_execution_id,
                task_ref="TASK-0037",
            )

            reopened = SQLiteControlStore(db_path)
            self.assertEqual(reopened.get_execution(execution.plan_execution_id).plan_digest, plan.digest())
            self.assertEqual(reopened.get_goal_execution(goal.goal_execution_id).goal_digest, plan.goal_digest)
            self.assertEqual(len(reopened.list_node_runs(execution.plan_execution_id)), 2)

            current = reopened.get_execution(execution.plan_execution_id)
            with self.assertRaises(PlanVersionConflictError):
                reopened.compare_and_swap_execution(current, expected_version=current.status_version + 99)

    def test_schema_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "control.sqlite"
            migrate_sqlite_control_store(db_path)
            connection = sqlite3.connect(db_path)
            try:
                connection.execute(
                    "UPDATE meta SET value = ? WHERE key = 'schema_version'",
                    ("ahra/sqlite-control-store/incompatible",),
                )
                connection.commit()
            finally:
                connection.close()

            with self.assertRaisesRegex(SQLiteControlStoreError, "unsupported SQLite control store schema"):
                SQLiteControlStore(db_path)

    def test_create_execution_rolls_back_partial_insert_on_node_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = SQLiteControlStore(Path(temp) / "control.sqlite")
            plan, plan_execution_id = create_recovery_execution(store, Path(temp) / "workspace")
            existing = store.get_execution(plan_execution_id)
            duplicate_nodes = store.list_node_runs(plan_execution_id)
            partial = replace(
                existing,
                plan_execution_id="PEXEC-partial-rollback",
                node_run_refs=tuple(node.node_run_id for node in duplicate_nodes),
            )

            with self.assertRaises(PlanVersionConflictError):
                store.create_execution(partial, duplicate_nodes)
            with self.assertRaises(KeyError):
                store.get_execution("PEXEC-partial-rollback")
            self.assertEqual(plan.goal_ref, "GOAL-sqlite-recovery")

    def test_expired_lease_requeues_pre_effect_node_and_rejects_stale_fencing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = SQLiteControlStore(Path(temp) / "control.sqlite")
            plan, plan_execution_id = create_recovery_execution(store, Path(temp) / "workspace")
            service = PlanExecutionService(store)
            node = [item for item in store.list_node_runs(plan_execution_id) if item.node_id == "NODE-effect"][0]
            node = service.transition_node(node.node_run_id, NodeRunStatus.READY, expected_version=node.status_version)
            node = service.transition_node(node.node_run_id, NodeRunStatus.ADMITTED, expected_version=node.status_version)
            old_now = utc_now()
            leased = service.acquire_node_lease(
                node.node_run_id,
                holder="worker:one",
                ttl_seconds=1,
                expected_version=node.status_version,
                now=old_now,
            )

            with self.assertRaisesRegex(PlanLeaseConflictError, "fencing"):
                service.transition_node(
                    leased.node_run_id,
                    NodeRunStatus.RUNNING,
                    expected_version=leased.status_version,
                    holder="worker:one",
                    fencing_token=999,
                    now=old_now,
                )

            report = recover_sqlite_control_plane(store, now=old_now + timedelta(seconds=2))
            recovered = store.get_node_run(leased.node_run_id)

            self.assertEqual(plan.goal_ref, "GOAL-sqlite-recovery")
            self.assertEqual(recovered.status, NodeRunStatus.PENDING)
            self.assertIsNone(recovered.lease)
            self.assertIn(leased.node_run_id, report.requeued_node_run_refs)
            self.assertIn("expired-node-lease", {finding.code for finding in report.findings})

    def test_missing_artifact_file_referenced_by_idempotency_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = SQLiteControlStore(Path(temp) / "control.sqlite")
            _plan, plan_execution_id = create_recovery_execution(store, Path(temp) / "workspace")
            node = [item for item in store.list_node_runs(plan_execution_id) if item.node_id == "NODE-effect"][0]
            missing = Path(temp) / "workspace" / "missing.txt"
            result = NodeExecutionResult(
                node_run_id=node.node_run_id,
                plan_id=node.plan_id,
                node_id=node.node_id,
                node_type=node.node_type,
                executor_release="sqlite-recovery-executor@sha256:" + "9" * 64,
                status=NodeExecutionStatus.ACCEPTED,
                artifact_refs=(f"file://{missing}",),
                evidence_refs=("EVD-missing-artifact",),
                gate_refs=node.gate_refs,
                usage=NodeExecutionUsage(model_calls=1, tool_calls=1, spawned_nodes=0, cost_usd=0.0),
            )
            store.record_idempotency_result(
                idempotency_key=f"IDEMP-{node.node_run_id}",
                plan_execution_id=plan_execution_id,
                node_run_id=node.node_run_id,
                result=result,
            )

            report = recover_sqlite_control_plane(store, now=utc_now() + timedelta(hours=1))

            self.assertIn("missing-artifact-file", {finding.code for finding in report.findings})

    def test_subprocess_crash_after_effect_resume_does_not_duplicate_side_effect(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "control.sqlite"
            workspace = Path(temp) / "workspace"
            report_path = Path(temp) / "resume-report.json"

            crash = _run_fixture(db_path, workspace, "crash-after-idempotency")
            self.assertEqual(crash.returncode, 97, crash.stderr)

            resume = _run_fixture(db_path, workspace, "resume", report_path=report_path)
            self.assertEqual(resume.returncode, 0, resume.stderr)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            metrics = report["metrics"]
            effect_node = _node_by_id(report, "NODE-effect")

            self.assertTrue(metrics["crashRecoverySucceeded"])
            self.assertEqual(metrics["resumeExecutorCallCount"], 0)
            self.assertEqual(metrics["sideEffectLineCount"], 1)
            self.assertEqual(metrics["duplicateEffectCount"], 0)
            self.assertTrue(metrics["checkpointLoadSuccess"])
            self.assertGreaterEqual(metrics["persistedEvidenceRefCount"], 2)
            self.assertEqual(effect_node["status"], NodeRunStatus.SUCCEEDED.value)
            self.assertTrue(effect_node["admission_decision_refs"])
            self.assertTrue(effect_node["capability_grant_refs"])
            self.assertTrue(effect_node["evidence_refs"])
            self.assertGreaterEqual(report["recoveryReport"]["metrics"]["recoveredNodeRunCount"], 1)

            second = _run_fixture(db_path, workspace, "resume", report_path=Path(temp) / "resume-report-2.json")
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(len((workspace / "effect.txt").read_text(encoding="utf-8").splitlines()), 1)

    def test_subprocess_stop_after_terminal_resume_skips_completed_node(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "control.sqlite"
            workspace = Path(temp) / "workspace"
            report_path = Path(temp) / "resume-report.json"

            stopped = _run_fixture(db_path, workspace, "stop-after-terminal")
            self.assertEqual(stopped.returncode, 75, stopped.stderr)

            resume = _run_fixture(db_path, workspace, "resume", report_path=report_path)
            self.assertEqual(resume.returncode, 0, resume.stderr)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            metrics = report["metrics"]
            effect_node = _node_by_id(report, "NODE-effect")

            self.assertTrue(metrics["crashRecoverySucceeded"])
            self.assertEqual(metrics["resumeExecutorCallCount"], 0)
            self.assertEqual(metrics["sideEffectLineCount"], 1)
            self.assertEqual(metrics["duplicateEffectCount"], 0)
            self.assertEqual(report["recoveryReport"]["metrics"]["recoveredNodeRunCount"], 0)
            self.assertEqual(effect_node["status"], NodeRunStatus.SUCCEEDED.value)


def _run_fixture(
    db_path: Path,
    workspace: Path,
    phase: str,
    *,
    report_path: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        "-B",
        "-m",
        "ahra.sqlite_recovery_fixture",
        "--db",
        str(db_path),
        "--workspace",
        str(workspace),
        "--phase",
        phase,
    ]
    if report_path is not None:
        command.extend(["--report", str(report_path)])
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _node_by_id(report: dict[str, object], node_id: str) -> dict[str, object]:
    for item in report["nodeRuns"]:  # type: ignore[index]
        if isinstance(item, dict) and item.get("node_id") == node_id:
            return item
    raise AssertionError(f"missing node {node_id}")


if __name__ == "__main__":
    unittest.main()
