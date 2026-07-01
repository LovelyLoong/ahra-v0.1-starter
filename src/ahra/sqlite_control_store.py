from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from .domain import Lease, utc_now
from .node_executor import NodeExecutionResult, NodeExecutionStatus, NodeExecutionUsage
from .plan_execution import (
    GoalExecutionRecord,
    GoalExecutionStatus,
    NodeRunRecord,
    NodeRunStatus,
    PlanCheckpointRecord,
    PlanExecutionRecord,
    PlanExecutionStatus,
    PlanVersionConflictError,
    ReconcilerFinding,
)


SQLITE_CONTROL_SCHEMA_VERSION = "ahra/sqlite-control-store/0.1"


class SQLiteControlStoreError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    idempotency_key: str
    plan_execution_id: str
    node_run_id: str
    result: NodeExecutionResult
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "idempotency_key": self.idempotency_key,
            "plan_execution_id": self.plan_execution_id,
            "node_run_id": self.node_run_id,
            "result": self.result.to_dict(),
            "created_at": _iso(self.created_at),
        }


@dataclass(frozen=True, slots=True)
class SQLiteRecoveryReport:
    schema_version: str
    store_ref: str
    findings: tuple[ReconcilerFinding, ...]
    recovered_node_run_refs: tuple[str, ...]
    requeued_node_run_refs: tuple[str, ...]
    failed_node_run_refs: tuple[str, ...]
    events: tuple[Mapping[str, Any], ...]
    metrics: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "store_ref": self.store_ref,
            "findings": [finding.to_dict() for finding in self.findings],
            "recovered_node_run_refs": list(self.recovered_node_run_refs),
            "requeued_node_run_refs": list(self.requeued_node_run_refs),
            "failed_node_run_refs": list(self.failed_node_run_refs),
            "events": [dict(event) for event in self.events],
            "metrics": dict(self.metrics),
        }


class SQLiteControlStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        migrate_sqlite_control_store(self.path)

    def create_goal_execution(self, goal_execution: GoalExecutionRecord) -> None:
        with self._connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO goal_executions(goal_execution_id, status, status_version, data_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        goal_execution.goal_execution_id,
                        goal_execution.status.value,
                        goal_execution.status_version,
                        _json(goal_execution.to_dict()),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise PlanVersionConflictError(
                    f"goal execution already exists: {goal_execution.goal_execution_id}"
                ) from exc

    def get_goal_execution(self, goal_execution_id: str) -> GoalExecutionRecord:
        row = self._fetch_one(
            "SELECT data_json FROM goal_executions WHERE goal_execution_id = ?",
            (goal_execution_id,),
        )
        if row is None:
            raise KeyError(goal_execution_id)
        return _goal_execution_from_dict(_loads(row["data_json"]))

    def compare_and_swap_goal_execution(
        self,
        goal_execution: GoalExecutionRecord,
        expected_version: int,
    ) -> GoalExecutionRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status_version FROM goal_executions WHERE goal_execution_id = ?",
                (goal_execution.goal_execution_id,),
            ).fetchone()
            if row is None:
                raise KeyError(goal_execution.goal_execution_id)
            if int(row["status_version"]) != expected_version:
                raise PlanVersionConflictError(
                    f"expected goal execution version {expected_version}, current {row['status_version']}"
                )
            if goal_execution.status_version != expected_version + 1:
                raise PlanVersionConflictError("goal execution status_version must increment exactly once")
            connection.execute(
                """
                UPDATE goal_executions
                SET status = ?, status_version = ?, data_json = ?
                WHERE goal_execution_id = ? AND status_version = ?
                """,
                (
                    goal_execution.status.value,
                    goal_execution.status_version,
                    _json(goal_execution.to_dict()),
                    goal_execution.goal_execution_id,
                    expected_version,
                ),
            )
        return self.get_goal_execution(goal_execution.goal_execution_id)

    def create_execution(
        self,
        execution: PlanExecutionRecord,
        node_runs: tuple[NodeRunRecord, ...],
    ) -> None:
        node_run_ids = [node.node_run_id for node in node_runs]
        if len(set(node_run_ids)) != len(node_run_ids):
            raise PlanVersionConflictError("node run ids must be unique within a PlanExecution")
        with self._connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO plan_executions(
                        plan_execution_id, goal_execution_ref, status, status_version, data_json
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        execution.plan_execution_id,
                        execution.goal_execution_ref,
                        execution.status.value,
                        execution.status_version,
                        _json(execution.to_dict()),
                    ),
                )
                for node in node_runs:
                    connection.execute(
                        """
                        INSERT INTO node_runs(
                            node_run_id, plan_execution_id, node_id, status, status_version, lease_expires_at, data_json
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            node.node_run_id,
                            node.plan_execution_id,
                            node.node_id,
                            node.status.value,
                            node.status_version,
                            _iso(node.lease.expires_at) if node.lease else None,
                            _json(node.to_dict()),
                        ),
                    )
            except sqlite3.IntegrityError as exc:
                raise PlanVersionConflictError("plan execution or node run already exists") from exc

    def get_execution(self, plan_execution_id: str) -> PlanExecutionRecord:
        row = self._fetch_one(
            "SELECT data_json FROM plan_executions WHERE plan_execution_id = ?",
            (plan_execution_id,),
        )
        if row is None:
            raise KeyError(plan_execution_id)
        return _plan_execution_from_dict(_loads(row["data_json"]))

    def compare_and_swap_execution(
        self,
        execution: PlanExecutionRecord,
        expected_version: int,
    ) -> PlanExecutionRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status_version FROM plan_executions WHERE plan_execution_id = ?",
                (execution.plan_execution_id,),
            ).fetchone()
            if row is None:
                raise KeyError(execution.plan_execution_id)
            if int(row["status_version"]) != expected_version:
                raise PlanVersionConflictError(
                    f"expected execution version {expected_version}, current {row['status_version']}"
                )
            if execution.status_version != expected_version + 1:
                raise PlanVersionConflictError("execution status_version must increment exactly once")
            cursor = connection.execute(
                """
                UPDATE plan_executions
                SET goal_execution_ref = ?, status = ?, status_version = ?, data_json = ?
                WHERE plan_execution_id = ? AND status_version = ?
                """,
                (
                    execution.goal_execution_ref,
                    execution.status.value,
                    execution.status_version,
                    _json(execution.to_dict()),
                    execution.plan_execution_id,
                    expected_version,
                ),
            )
            if cursor.rowcount != 1:
                raise PlanVersionConflictError("plan execution CAS update failed")
        return self.get_execution(execution.plan_execution_id)

    def put_node_run(self, node_run: NodeRunRecord) -> None:
        with self._connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO node_runs(
                        node_run_id, plan_execution_id, node_id, status, status_version, lease_expires_at, data_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        node_run.node_run_id,
                        node_run.plan_execution_id,
                        node_run.node_id,
                        node_run.status.value,
                        node_run.status_version,
                        _iso(node_run.lease.expires_at) if node_run.lease else None,
                        _json(node_run.to_dict()),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise PlanVersionConflictError(f"node run already exists: {node_run.node_run_id}") from exc

    def get_node_run(self, node_run_id: str) -> NodeRunRecord:
        row = self._fetch_one("SELECT data_json FROM node_runs WHERE node_run_id = ?", (node_run_id,))
        if row is None:
            raise KeyError(node_run_id)
        return _node_run_from_dict(_loads(row["data_json"]))

    def compare_and_swap_node(
        self,
        node_run: NodeRunRecord,
        expected_version: int,
    ) -> NodeRunRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status_version FROM node_runs WHERE node_run_id = ?",
                (node_run.node_run_id,),
            ).fetchone()
            if row is None:
                raise KeyError(node_run.node_run_id)
            if int(row["status_version"]) != expected_version:
                raise PlanVersionConflictError(
                    f"expected node version {expected_version}, current {row['status_version']}"
                )
            if node_run.status_version != expected_version + 1:
                raise PlanVersionConflictError("node status_version must increment exactly once")
            cursor = connection.execute(
                """
                UPDATE node_runs
                SET status = ?, status_version = ?, lease_expires_at = ?, data_json = ?
                WHERE node_run_id = ? AND status_version = ?
                """,
                (
                    node_run.status.value,
                    node_run.status_version,
                    _iso(node_run.lease.expires_at) if node_run.lease else None,
                    _json(node_run.to_dict()),
                    node_run.node_run_id,
                    expected_version,
                ),
            )
            if cursor.rowcount != 1:
                raise PlanVersionConflictError("node run CAS update failed")
        return self.get_node_run(node_run.node_run_id)

    def list_node_runs(self, plan_execution_id: str) -> tuple[NodeRunRecord, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT data_json FROM node_runs
                WHERE plan_execution_id = ?
                ORDER BY node_id, json_extract(data_json, '$.attempt')
                """,
                (plan_execution_id,),
            ).fetchall()
        return tuple(_node_run_from_dict(_loads(row["data_json"])) for row in rows)

    def list_all_node_runs(self) -> tuple[NodeRunRecord, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT data_json FROM node_runs ORDER BY plan_execution_id, node_id, json_extract(data_json, '$.attempt')"
            ).fetchall()
        return tuple(_node_run_from_dict(_loads(row["data_json"])) for row in rows)

    def list_executions(self) -> tuple[PlanExecutionRecord, ...]:
        with self._connect() as connection:
            rows = connection.execute("SELECT data_json FROM plan_executions ORDER BY plan_execution_id").fetchall()
        return tuple(_plan_execution_from_dict(_loads(row["data_json"])) for row in rows)

    def put_checkpoint(self, checkpoint: PlanCheckpointRecord) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO checkpoints(checkpoint_id, plan_execution_id, data_json)
                VALUES (?, ?, ?)
                ON CONFLICT(checkpoint_id) DO UPDATE SET data_json = excluded.data_json
                """,
                (checkpoint.checkpoint_id, checkpoint.plan_execution_id, _json(checkpoint.to_dict())),
            )

    def get_checkpoint(self, checkpoint_ref: str) -> PlanCheckpointRecord:
        checkpoint_id = checkpoint_ref.removeprefix("checkpoint://")
        row = self._fetch_one("SELECT data_json FROM checkpoints WHERE checkpoint_id = ?", (checkpoint_id,))
        if row is None:
            raise KeyError(checkpoint_ref)
        return _checkpoint_from_dict(_loads(row["data_json"]))

    def record_idempotency_result(
        self,
        *,
        idempotency_key: str,
        plan_execution_id: str,
        node_run_id: str,
        result: NodeExecutionResult,
        now: datetime | None = None,
    ) -> IdempotencyRecord:
        now = now or utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO idempotency_records(
                    idempotency_key, plan_execution_id, node_run_id, result_json, artifact_refs_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(idempotency_key) DO NOTHING
                """,
                (
                    idempotency_key,
                    plan_execution_id,
                    node_run_id,
                    _json(result.to_dict()),
                    _json(list(result.artifact_refs)),
                    _iso(now),
                ),
            )
        existing = self.get_idempotency_record(idempotency_key)
        if existing is None:
            raise SQLiteControlStoreError(f"idempotency record was not persisted: {idempotency_key}")
        return existing

    def get_idempotency_record(self, idempotency_key: str) -> IdempotencyRecord | None:
        row = self._fetch_one(
            "SELECT * FROM idempotency_records WHERE idempotency_key = ?",
            (idempotency_key,),
        )
        return _idempotency_record_from_row(row) if row else None

    def get_idempotency_record_for_node(self, node_run_id: str) -> IdempotencyRecord | None:
        row = self._fetch_one(
            """
            SELECT * FROM idempotency_records
            WHERE node_run_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (node_run_id,),
        )
        return _idempotency_record_from_row(row) if row else None

    def list_idempotency_records(self) -> tuple[IdempotencyRecord, ...]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM idempotency_records ORDER BY idempotency_key").fetchall()
        return tuple(_idempotency_record_from_row(row) for row in rows)

    def append_recovery_event(
        self,
        *,
        event_type: str,
        idempotency_key: str,
        refs: tuple[str, ...],
        reason: str,
        now: datetime | None = None,
    ) -> Mapping[str, Any]:
        now = now or utc_now()
        event = {
            "schema_version": SQLITE_CONTROL_SCHEMA_VERSION,
            "event_id": "SQLEVT-" + _stable_suffix(
                {
                    "eventType": event_type,
                    "idempotencyKey": idempotency_key,
                    "refs": list(refs),
                }
            ),
            "idempotency_key": idempotency_key,
            "event_type": event_type,
            "occurred_at": _iso(now),
            "reason": reason,
            "refs": list(refs),
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO recovery_events(event_id, idempotency_key, event_type, occurred_at, data_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(idempotency_key) DO NOTHING
                """,
                (
                    event["event_id"],
                    event["idempotency_key"],
                    event["event_type"],
                    event["occurred_at"],
                    _json(event),
                ),
            )
        return event

    def list_recovery_events(self) -> tuple[Mapping[str, Any], ...]:
        with self._connect() as connection:
            rows = connection.execute("SELECT data_json FROM recovery_events ORDER BY occurred_at, event_id").fetchall()
        return tuple(_loads(row["data_json"]) for row in rows)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _fetch_one(self, sql: str, params: tuple[Any, ...]) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute(sql, params).fetchone()


def migrate_sqlite_control_store(path: Path | str) -> None:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS goal_executions (
                goal_execution_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                status_version INTEGER NOT NULL,
                data_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS plan_executions (
                plan_execution_id TEXT PRIMARY KEY,
                goal_execution_ref TEXT,
                status TEXT NOT NULL,
                status_version INTEGER NOT NULL,
                data_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS node_runs (
                node_run_id TEXT PRIMARY KEY,
                plan_execution_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                status TEXT NOT NULL,
                status_version INTEGER NOT NULL,
                lease_expires_at TEXT,
                data_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_node_runs_plan_execution
                ON node_runs(plan_execution_id, node_id);
            CREATE TABLE IF NOT EXISTS checkpoints (
                checkpoint_id TEXT PRIMARY KEY,
                plan_execution_id TEXT NOT NULL,
                data_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS idempotency_records (
                idempotency_key TEXT PRIMARY KEY,
                plan_execution_id TEXT NOT NULL,
                node_run_id TEXT NOT NULL,
                result_json TEXT NOT NULL,
                artifact_refs_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_idempotency_node
                ON idempotency_records(node_run_id);
            CREATE TABLE IF NOT EXISTS recovery_events (
                event_id TEXT PRIMARY KEY,
                idempotency_key TEXT NOT NULL UNIQUE,
                event_type TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                data_json TEXT NOT NULL
            );
            """
        )
        row = connection.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
        if row is None:
            connection.execute(
                "INSERT INTO meta(key, value) VALUES ('schema_version', ?)",
                (SQLITE_CONTROL_SCHEMA_VERSION,),
            )
        elif row["value"] != SQLITE_CONTROL_SCHEMA_VERSION:
            raise SQLiteControlStoreError(
                f"unsupported SQLite control store schema {row['value']}; expected {SQLITE_CONTROL_SCHEMA_VERSION}"
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def recover_sqlite_control_plane(
    store: SQLiteControlStore,
    *,
    now: datetime | None = None,
) -> SQLiteRecoveryReport:
    now = now or utc_now()
    findings: list[ReconcilerFinding] = []
    recovered: list[str] = []
    requeued: list[str] = []
    failed: list[str] = []

    for node in store.list_all_node_runs():
        if node.status.terminal:
            continue
        lease_expired = node.lease is not None and not node.lease.active_at(now)
        if lease_expired:
            findings.append(
                ReconcilerFinding(
                    code="expired-node-lease",
                    severity="error" if node.status == NodeRunStatus.RUNNING else "warning",
                    message=(
                        f"Running NodeRun lease expired and must converge to terminal failed: {node.node_run_id}."
                        if node.status == NodeRunStatus.RUNNING
                        else f"NodeRun lease expired for {node.node_run_id}."
                    ),
                    refs=(node.plan_execution_id, node.node_run_id),
                )
            )
        idempotency = store.get_idempotency_record_for_node(node.node_run_id)
        if idempotency and node.status != NodeRunStatus.SUCCEEDED:
            if node.lease and node.lease.active_at(now):
                findings.append(
                    ReconcilerFinding(
                        code="active-node-lease-with-idempotency",
                        severity="warning",
                        message=f"NodeRun has a durable idempotency record but still has an active lease: {node.node_run_id}.",
                        refs=(node.plan_execution_id, node.node_run_id, idempotency.idempotency_key),
                    )
                )
                continue
            result = idempotency.result
            recovered_node = replace(
                node,
                status=NodeRunStatus.RUNNING,
                status_version=node.status_version + 1,
                lease=None,
                executor_release=result.executor_release or node.executor_release,
                artifact_refs=_merge_refs(node.artifact_refs, result.artifact_refs),
                evidence_refs=_merge_refs(node.evidence_refs, result.evidence_refs),
                terminal_failure_refs=_merge_refs(node.terminal_failure_refs, result.terminal_failure_refs),
                usage=result.usage.to_dict() if result.usage else node.usage,
                failure_class=None,
                message="Recovered committed executor result from durable idempotency record; scheduler must finish declared gates.",
                updated_at=now,
            )
            store.compare_and_swap_node(recovered_node, node.status_version)
            store.append_recovery_event(
                event_type="node_executor_result_recovered",
                idempotency_key=f"recover:{node.node_run_id}:{node.status_version}",
                refs=(node.plan_execution_id, node.node_run_id, idempotency.idempotency_key),
                reason="Recovered committed executor result from durable idempotency record after process exit.",
                now=now,
            )
            recovered.append(node.node_run_id)
            continue
        if lease_expired and node.status in {NodeRunStatus.READY, NodeRunStatus.ADMITTED}:
            requeued_node = replace(
                node,
                status=NodeRunStatus.PENDING,
                status_version=node.status_version + 1,
                lease=None,
                message="Expired pre-effect lease cleared for scheduler retry.",
                updated_at=now,
            )
            store.compare_and_swap_node(requeued_node, node.status_version)
            store.append_recovery_event(
                event_type="node_requeued_after_expired_lease",
                idempotency_key=f"requeue:{node.node_run_id}:{node.status_version}",
                refs=(node.plan_execution_id, node.node_run_id),
                reason="Recovered pre-effect NodeRun by clearing expired lease and returning to pending.",
                now=now,
            )
            requeued.append(node.node_run_id)
        elif lease_expired and node.status == NodeRunStatus.RUNNING:
            failed_node = replace(
                node,
                status=NodeRunStatus.FAILED,
                status_version=node.status_version + 1,
                lease=None,
                terminal_failure_refs=_merge_refs(node.terminal_failure_refs, (f"LEASE-{node.node_run_id}",)),
                failure_class="node_lease_expired",
                message="Running NodeRun lease expired before the executor produced a durable idempotency result.",
                updated_at=now,
            )
            store.compare_and_swap_node(failed_node, node.status_version)
            store.append_recovery_event(
                event_type="node_failed_expired_lease",
                idempotency_key=f"fail:{node.node_run_id}:{node.status_version}",
                refs=(node.plan_execution_id, node.node_run_id),
                reason="Failed running NodeRun after expired lease without a durable idempotency record.",
                now=now,
            )
            failed.append(node.node_run_id)

    for record in store.list_idempotency_records():
        for ref in record.result.artifact_refs:
            if not ref.startswith("file://"):
                continue
            path = Path(ref.removeprefix("file://"))
            if not path.exists():
                findings.append(
                    ReconcilerFinding(
                        code="missing-artifact-file",
                        severity="error",
                        message=f"Artifact file referenced by idempotency record is missing: {ref}",
                        refs=(record.node_run_id, ref),
                    )
                )

    events = store.list_recovery_events()
    metrics = {
        "recoveredNodeRunCount": len(recovered),
        "requeuedNodeRunCount": len(requeued),
        "failedNodeRunCount": len(failed),
        "findingCount": len(findings),
        "findingCountByCode": _finding_counts(findings),
        "idempotencyRecordCount": len(store.list_idempotency_records()),
    }
    return SQLiteRecoveryReport(
        schema_version="ahra/sqlite-recovery-report/0.1",
        store_ref=f"sqlite://{store.path}",
        findings=tuple(findings),
        recovered_node_run_refs=tuple(recovered),
        requeued_node_run_refs=tuple(requeued),
        failed_node_run_refs=tuple(failed),
        events=events,
        metrics=metrics,
    )


def _idempotency_record_from_row(row: sqlite3.Row) -> IdempotencyRecord:
    return IdempotencyRecord(
        idempotency_key=str(row["idempotency_key"]),
        plan_execution_id=str(row["plan_execution_id"]),
        node_run_id=str(row["node_run_id"]),
        result=_node_execution_result_from_dict(_loads(row["result_json"])),
        created_at=_parse_datetime(row["created_at"]) or utc_now(),
    )


def _node_execution_result_from_dict(data: Mapping[str, Any]) -> NodeExecutionResult:
    metadata = dict(data["metadata"])
    spec = dict(data["spec"])
    usage_data = spec.get("usage")
    usage = None
    if usage_data:
        usage = NodeExecutionUsage(
            model_calls=int(usage_data.get("modelCalls", 0)),
            tool_calls=int(usage_data.get("toolCalls", 0)),
            spawned_nodes=int(usage_data.get("spawnedNodes", 0)),
            cost_usd=usage_data.get("costUsd"),
        )
    return NodeExecutionResult(
        node_run_id=str(metadata["nodeRunId"]),
        plan_id=str(metadata["planId"]),
        node_id=str(metadata["nodeId"]),
        node_type=str(spec["nodeType"]),
        executor_release=str(metadata["executorRelease"]),
        status=NodeExecutionStatus(str(spec["status"])),
        artifact_refs=tuple(str(ref) for ref in spec.get("artifactRefs", ())),
        evidence_refs=tuple(str(ref) for ref in spec.get("evidenceRefs", ())),
        gate_refs=tuple(str(ref) for ref in spec.get("gateRefs", ())),
        terminal_failure_refs=tuple(str(ref) for ref in spec.get("terminalFailureRefs", ())),
        task_completed_state_update_attempted=bool(spec.get("taskCompletedStateUpdateAttempted", False)),
        usage=usage,
        message=str(spec.get("message", "")),
        details=dict(spec.get("details", {})),
    )


def _goal_execution_from_dict(data: Mapping[str, Any]) -> GoalExecutionRecord:
    return GoalExecutionRecord(
        goal_execution_id=str(data["goal_execution_id"]),
        goal_ref=str(data["goal_ref"]),
        goal_digest=str(data["goal_digest"]),
        claim_graph_ref=str(data["claim_graph_ref"]) if data.get("claim_graph_ref") else None,
        claim_graph_digest=str(data["claim_graph_digest"]),
        status=GoalExecutionStatus(str(data["status"])),
        status_version=int(data["status_version"]),
        active_plan_execution_ref=str(data["active_plan_execution_ref"]) if data.get("active_plan_execution_ref") else None,
        plan_execution_refs=tuple(str(item) for item in data.get("plan_execution_refs", ())),
        open_defect_refs=tuple(str(item) for item in data.get("open_defect_refs", ())),
        resolved_defect_refs=tuple(str(item) for item in data.get("resolved_defect_refs", ())),
        repair_cycle=int(data.get("repair_cycle", 0)),
        max_repair_cycles=int(data["max_repair_cycles"]),
        budget_summary=dict(data.get("budget_summary", {})),
        usage=dict(data.get("usage", {})),
        workspace_ref=str(data["workspace_ref"]) if data.get("workspace_ref") else None,
        checkpoint_ref=str(data["checkpoint_ref"]) if data.get("checkpoint_ref") else None,
        artifact_refs=tuple(str(item) for item in data.get("artifact_refs", ())),
        evidence_refs=tuple(str(item) for item in data.get("evidence_refs", ())),
        approval_refs=tuple(str(item) for item in data.get("approval_refs", ())),
        failure_class=str(data["failure_class"]) if data.get("failure_class") else None,
        message=str(data.get("message", "")),
        created_at=_parse_datetime(data.get("created_at")) or utc_now(),
        updated_at=_parse_datetime(data.get("updated_at")) or utc_now(),
    )


def _plan_execution_from_dict(data: Mapping[str, Any]) -> PlanExecutionRecord:
    return PlanExecutionRecord(
        plan_execution_id=str(data["plan_execution_id"]),
        plan_id=str(data["plan_id"]),
        plan_version=int(data["plan_version"]),
        plan_digest=str(data["plan_digest"]),
        goal_ref=str(data["goal_ref"]),
        goal_execution_ref=str(data["goal_execution_ref"]) if data.get("goal_execution_ref") else None,
        parent_plan_execution_ref=str(data["parent_plan_execution_ref"]) if data.get("parent_plan_execution_ref") else None,
        parent_plan_digest=str(data["parent_plan_digest"]) if data.get("parent_plan_digest") else None,
        reused_node_refs=tuple(str(item) for item in data.get("reused_node_refs", ())),
        reused_evidence_refs=tuple(str(item) for item in data.get("reused_evidence_refs", ())),
        validation_report_ref=str(data["validation_report_ref"]),
        validation_report_digest=str(data["validation_report_digest"]),
        status=PlanExecutionStatus(str(data["status"])),
        status_version=int(data["status_version"]),
        max_concurrency=int(data["max_concurrency"]),
        budget_summary=dict(data.get("budget_summary", {})),
        node_run_refs=tuple(str(item) for item in data.get("node_run_refs", ())),
        task_ref=str(data["task_ref"]) if data.get("task_ref") else None,
        lease=_lease_from_dict(data.get("lease")),
        checkpoint_ref=str(data["checkpoint_ref"]) if data.get("checkpoint_ref") else None,
        artifact_refs=tuple(str(item) for item in data.get("artifact_refs", ())),
        evidence_refs=tuple(str(item) for item in data.get("evidence_refs", ())),
        trace_refs=tuple(str(item) for item in data.get("trace_refs", ())),
        handoff_refs=tuple(str(item) for item in data.get("handoff_refs", ())),
        cancel_requested=bool(data.get("cancel_requested", False)),
        deadline_at=_parse_datetime(data.get("deadline_at")),
        failure_class=str(data["failure_class"]) if data.get("failure_class") else None,
        message=str(data.get("message", "")),
        created_at=_parse_datetime(data.get("created_at")) or utc_now(),
        updated_at=_parse_datetime(data.get("updated_at")) or utc_now(),
    )


def _node_run_from_dict(data: Mapping[str, Any]) -> NodeRunRecord:
    return NodeRunRecord(
        node_run_id=str(data["node_run_id"]),
        plan_execution_id=str(data["plan_execution_id"]),
        plan_id=str(data["plan_id"]),
        plan_digest=str(data["plan_digest"]),
        node_id=str(data["node_id"]),
        node_type=str(data["node_type"]),
        attempt=int(data["attempt"]),
        status=NodeRunStatus(str(data["status"])),
        status_version=int(data["status_version"]),
        dependency_node_refs=tuple(str(item) for item in data.get("dependency_node_refs", ())),
        gate_refs=tuple(str(item) for item in data.get("gate_refs", ())),
        budget=dict(data.get("budget", {})),
        usage=dict(data.get("usage", {})),
        artifact_refs=tuple(str(item) for item in data.get("artifact_refs", ())),
        evidence_refs=tuple(str(item) for item in data.get("evidence_refs", ())),
        terminal_failure_refs=tuple(str(item) for item in data.get("terminal_failure_refs", ())),
        admission_decision_refs=tuple(str(item) for item in data.get("admission_decision_refs", ())),
        capability_grant_refs=tuple(str(item) for item in data.get("capability_grant_refs", ())),
        capability_grant_digests=tuple(str(item) for item in data.get("capability_grant_digests", ())),
        executor_release=str(data["executor_release"]) if data.get("executor_release") else None,
        lease=_lease_from_dict(data.get("lease")),
        failure_class=str(data["failure_class"]) if data.get("failure_class") else None,
        message=str(data.get("message", "")),
        created_at=_parse_datetime(data.get("created_at")) or utc_now(),
        updated_at=_parse_datetime(data.get("updated_at")) or utc_now(),
    )


def _checkpoint_from_dict(data: Mapping[str, Any]) -> PlanCheckpointRecord:
    return PlanCheckpointRecord(
        checkpoint_id=str(data["checkpoint_id"]),
        plan_execution_id=str(data["plan_execution_id"]),
        plan_id=str(data["plan_id"]),
        plan_digest=str(data["plan_digest"]),
        plan_status=PlanExecutionStatus(str(data["plan_status"])),
        node_statuses={str(key): str(value) for key, value in dict(data.get("node_statuses", {})).items()},
        node_budgets={str(key): dict(value) for key, value in dict(data.get("node_budgets", {})).items()},
        node_usage={str(key): dict(value) for key, value in dict(data.get("node_usage", {})).items()},
        artifact_refs=tuple(str(item) for item in data.get("artifact_refs", ())),
        evidence_refs=tuple(str(item) for item in data.get("evidence_refs", ())),
        created_at=_parse_datetime(data.get("created_at")) or utc_now(),
    )


def _lease_from_dict(data: Any) -> Lease | None:
    if not data:
        return None
    return Lease(
        holder=str(data["holder"]),
        fencing_token=int(data["fencing_token"]),
        heartbeat_at=_parse_datetime(data["heartbeat_at"]) or utc_now(),
        expires_at=_parse_datetime(data["expires_at"]) or utc_now(),
    )


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text).astimezone(UTC)


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _loads(value: str) -> Any:
    return json.loads(value)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _stable_suffix(payload: Mapping[str, Any]) -> str:
    import hashlib

    return hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()[:16]


def _merge_refs(existing: tuple[str, ...], new_refs: tuple[str, ...]) -> tuple[str, ...]:
    result = list(existing)
    for ref in new_refs:
        if ref not in result:
            result.append(ref)
    return tuple(result)


def _finding_counts(findings: list[ReconcilerFinding]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.code] = counts.get(finding.code, 0) + 1
    return counts
