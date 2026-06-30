from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from string import Template
from typing import Any, Mapping, Protocol

import yaml

from .awkp_state_writer import AwkpTaskStateWriter
from .evidence_gate import inspect_task
from .goal_operations import (
    GoalAwkpBridge,
    GoalAwkpBridgeRequest,
    GoalOperationService,
    load_goal_execution_request,
)


SUPPORTED_API_VERSION = "ahra.dev/v1alpha1"
SUPPORTED_KIND = "WorkflowSequence"
SUPPORTED_SCHEMA_VERSION = "ahra/workflow-sequence-result/0.1"
DEFAULT_PRODUCER_ACTOR = "agent:workflow-sequence-runner"
DEFAULT_VERIFIER_ACTOR = "agent:independent-verifier"


class WorkflowSequenceError(ValueError):
    """Raised when a WorkflowSequence document or execution is invalid."""


@dataclass(frozen=True, slots=True)
class WorkflowSequenceTask:
    task_id: str
    depends_on: tuple[str, ...] = ()
    verification_strategy: str = "simple"
    goal_request: str | None = None
    goal_request_template: str | None = None
    review_report: str | None = None
    review_report_template: str | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any], defaults: Mapping[str, Any] | None = None) -> "WorkflowSequenceTask":
        defaults = defaults or {}
        task_id = str(data.get("taskId") or "")
        if not task_id:
            raise WorkflowSequenceError("WorkflowSequence task requires taskId")
        return cls(
            task_id=task_id,
            depends_on=_string_tuple(data.get("dependsOn", ())),
            verification_strategy=str(data.get("verificationStrategy") or defaults.get("verificationStrategy") or "simple"),
            goal_request=_optional_string(data.get("goalRequest") or defaults.get("goalRequest")),
            goal_request_template=_optional_string(data.get("goalRequestTemplate") or defaults.get("goalRequestTemplate")),
            review_report=_optional_string(data.get("reviewReport") or defaults.get("reviewReport")),
            review_report_template=_optional_string(data.get("reviewReportTemplate") or defaults.get("reviewReportTemplate")),
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "taskId": self.task_id,
            "dependsOn": list(self.depends_on),
            "verificationStrategy": self.verification_strategy,
        }
        if self.goal_request:
            data["goalRequest"] = self.goal_request
        if self.goal_request_template:
            data["goalRequestTemplate"] = self.goal_request_template
        if self.review_report:
            data["reviewReport"] = self.review_report
        if self.review_report_template:
            data["reviewReportTemplate"] = self.review_report_template
        return data


@dataclass(frozen=True, slots=True)
class WorkflowSequence:
    name: str
    sequence_id: str
    tasks: tuple[WorkflowSequenceTask, ...]
    work_root: str = "work"
    producer_actor: str = DEFAULT_PRODUCER_ACTOR
    verifier_actor: str = DEFAULT_VERIFIER_ACTOR
    max_cycles: int = 1
    lease_ttl_seconds: int | None = None

    @classmethod
    def from_file(cls, path: str | Path) -> "WorkflowSequence":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, Mapping):
            raise WorkflowSequenceError(f"WorkflowSequence must be a mapping: {path}")
        return cls.from_mapping(data)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "WorkflowSequence":
        if data.get("apiVersion") != SUPPORTED_API_VERSION or data.get("kind") != SUPPORTED_KIND:
            raise WorkflowSequenceError("expected apiVersion ahra.dev/v1alpha1 and kind WorkflowSequence")
        metadata = _mapping(data.get("metadata"), "metadata")
        spec = _mapping(data.get("spec"), "spec")
        defaults = _mapping(spec.get("taskDefaults") or {}, "spec.taskDefaults")
        tasks = tuple(WorkflowSequenceTask.from_mapping(_mapping(item, "spec.tasks[]"), defaults) for item in spec.get("tasks", ()))
        sequence = cls(
            name=str(metadata.get("name") or ""),
            sequence_id=str(metadata.get("sequenceId") or metadata.get("name") or ""),
            tasks=tasks,
            work_root=str(spec.get("workRoot") or "work"),
            producer_actor=str(spec.get("producerActor") or DEFAULT_PRODUCER_ACTOR),
            verifier_actor=str(spec.get("verifierActor") or DEFAULT_VERIFIER_ACTOR),
            max_cycles=int(spec.get("maxCycles", 1)),
            lease_ttl_seconds=_optional_int(spec.get("leaseTtlSeconds")),
        )
        sequence.ordered_tasks()
        if not sequence.name:
            raise WorkflowSequenceError("metadata.name is required")
        if not sequence.sequence_id:
            raise WorkflowSequenceError("metadata.sequenceId is required")
        if not sequence.tasks:
            raise WorkflowSequenceError("spec.tasks must not be empty")
        if sequence.max_cycles < 1:
            raise WorkflowSequenceError("spec.maxCycles must be positive")
        if sequence.producer_actor == sequence.verifier_actor:
            raise WorkflowSequenceError("producerActor and verifierActor must differ")
        return sequence

    def ordered_tasks(self) -> tuple[WorkflowSequenceTask, ...]:
        by_id: dict[str, WorkflowSequenceTask] = {}
        for task in self.tasks:
            if task.task_id in by_id:
                raise WorkflowSequenceError(f"duplicate taskId: {task.task_id}")
            by_id[task.task_id] = task
        for task in self.tasks:
            unknown = tuple(dep for dep in task.depends_on if dep not in by_id)
            if unknown:
                raise WorkflowSequenceError(f"{task.task_id} depends on unknown tasks: {', '.join(unknown)}")

        ordered: list[WorkflowSequenceTask] = []
        remaining = dict(by_id)
        satisfied: set[str] = set()
        while remaining:
            progressed = False
            for task in self.tasks:
                if task.task_id not in remaining:
                    continue
                if all(dep in satisfied for dep in task.depends_on):
                    ordered.append(task)
                    satisfied.add(task.task_id)
                    del remaining[task.task_id]
                    progressed = True
            if not progressed:
                cycle = ", ".join(sorted(remaining))
                raise WorkflowSequenceError(f"WorkflowSequence dependency cycle: {cycle}")
        return tuple(ordered)

    def to_dict(self) -> dict[str, Any]:
        return {
            "apiVersion": SUPPORTED_API_VERSION,
            "kind": SUPPORTED_KIND,
            "metadata": {"name": self.name, "sequenceId": self.sequence_id},
            "spec": {
                "workRoot": self.work_root,
                "producerActor": self.producer_actor,
                "verifierActor": self.verifier_actor,
                "maxCycles": self.max_cycles,
                "tasks": [task.to_dict() for task in self.tasks],
            },
        }


@dataclass(frozen=True, slots=True)
class WorkflowSequenceClaim:
    state_version: int
    fencing_token: str
    event_id: str | None = None
    reused_existing_lease: bool = False

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "WorkflowSequenceClaim":
        token = str(data.get("fencing_token") or data.get("fencingToken") or "")
        if not token:
            raise WorkflowSequenceError("claimed task has no fencing token")
        return cls(
            state_version=int(data.get("state_version") or data.get("stateVersion")),
            fencing_token=token,
            event_id=str(data["event_id"]) if data.get("event_id") else None,
            reused_existing_lease=bool(data.get("reused_existing_lease", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        data = {
            "stateVersion": self.state_version,
            "fencingToken": self.fencing_token,
            "reusedExistingLease": self.reused_existing_lease,
        }
        if self.event_id:
            data["eventId"] = self.event_id
        return data


@dataclass(frozen=True, slots=True)
class WorkflowSequenceTaskResult:
    task_id: str
    verification_strategy: str
    status: str
    state_before: str | None = None
    state_after: str | None = None
    goal_execution_id: str | None = None
    goal_status: str | None = None
    bridge_terminal_state: str | None = None
    blocker: str | None = None
    goal_request: str | None = None
    review_report: str | None = None
    claim: WorkflowSequenceClaim | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "taskId": self.task_id,
            "verificationStrategy": self.verification_strategy,
            "status": self.status,
        }
        for key, value in (
            ("stateBefore", self.state_before),
            ("stateAfter", self.state_after),
            ("goalExecutionId", self.goal_execution_id),
            ("goalStatus", self.goal_status),
            ("bridgeTerminalState", self.bridge_terminal_state),
            ("blocker", self.blocker),
            ("goalRequest", self.goal_request),
            ("reviewReport", self.review_report),
        ):
            if value is not None:
                data[key] = value
        if self.claim:
            data["claim"] = self.claim.to_dict()
        return data


@dataclass(frozen=True, slots=True)
class WorkflowSequenceResult:
    sequence_id: str
    completed_task_ids: tuple[str, ...]
    task_results: tuple[WorkflowSequenceTaskResult, ...]
    halted: bool = False
    blocker: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schema_version": SUPPORTED_SCHEMA_VERSION,
            "sequenceId": self.sequence_id,
            "completedTaskIds": list(self.completed_task_ids),
            "halted": self.halted,
            "taskResults": [result.to_dict() for result in self.task_results],
        }
        if self.blocker:
            data["blocker"] = self.blocker
        return data


class WorkflowSequenceOperations(Protocol):
    def inspect_task(self, task_id: str) -> Mapping[str, Any]:
        ...

    def claim_task(
        self,
        task_id: str,
        *,
        expected_version: int,
        actor: str,
        lease_ttl_seconds: int | None,
    ) -> Mapping[str, Any]:
        ...

    def start_goal(self, task: WorkflowSequenceTask, request_path: Path) -> Mapping[str, Any]:
        ...

    def bridge_goal(
        self,
        task: WorkflowSequenceTask,
        *,
        goal_result: Mapping[str, Any],
        claim: WorkflowSequenceClaim,
        request_path: Path,
        report_path: Path,
        producer_actor: str,
        verifier_actor: str,
        max_cycles: int,
        lease_ttl_seconds: int | None,
    ) -> Mapping[str, Any]:
        ...


class DefaultWorkflowSequenceOperations:
    def __init__(self, *, work_root: str | Path = "work") -> None:
        self.work_root = Path(work_root)
        self.state_writer = AwkpTaskStateWriter(work_root=self.work_root)
        self.goal_service = GoalOperationService()

    def inspect_task(self, task_id: str) -> Mapping[str, Any]:
        return inspect_task(task_id, work_root=self.work_root)

    def claim_task(
        self,
        task_id: str,
        *,
        expected_version: int,
        actor: str,
        lease_ttl_seconds: int | None,
    ) -> Mapping[str, Any]:
        return asdict(
            self.state_writer.acquire_working(
                task_id,
                expected_version=expected_version,
                actor=actor,
                idempotency_key=f"{task_id}:workflow-sequence:claim:{expected_version}",
                reason="WorkflowSequenceRunner claimed this task for governed GoalExecution.",
                lease_ttl_seconds=lease_ttl_seconds,
            )
        )

    def start_goal(self, task: WorkflowSequenceTask, request_path: Path) -> Mapping[str, Any]:
        return self.goal_service.start(request_path)

    def bridge_goal(
        self,
        task: WorkflowSequenceTask,
        *,
        goal_result: Mapping[str, Any],
        claim: WorkflowSequenceClaim,
        request_path: Path,
        report_path: Path,
        producer_actor: str,
        verifier_actor: str,
        max_cycles: int,
        lease_ttl_seconds: int | None,
    ) -> Mapping[str, Any]:
        if not report_path.is_file():
            raise WorkflowSequenceError(f"{task.task_id} verifier report does not exist: {report_path}")
        request = load_goal_execution_request(request_path)
        goal_execution_id = str(goal_result["goalExecutionId"])
        result = GoalAwkpBridge(work_root=self.work_root).run(
            GoalAwkpBridgeRequest(
                goal_execution_id=goal_execution_id,
                task=task.task_id,
                work_root=self.work_root,
                expected_task_version=claim.state_version,
                producer_actor=producer_actor,
                verifier_actor=verifier_actor,
                fencing_token=claim.fencing_token,
                report_paths=(report_path,),
                db_path=request.store_path,
                artifact_dir=request.artifact_dir,
                max_cycles=max_cycles,
                idempotency_key_prefix=f"{task.task_id}:workflow-sequence:{goal_execution_id}",
                lease_ttl_seconds=lease_ttl_seconds,
                reason=f"WorkflowSequenceRunner submitted {task.verification_strategy} verification for this task.",
            )
        )
        return asdict(result)


class WorkflowSequenceRunner:
    def __init__(
        self,
        sequence: WorkflowSequence,
        *,
        sequence_path: str | Path | None = None,
        operations: WorkflowSequenceOperations | None = None,
        run_root: str | Path | None = None,
    ) -> None:
        self.sequence = sequence
        self.sequence_path = Path(sequence_path) if sequence_path else None
        self.base_dir = self.sequence_path.parent if self.sequence_path else Path.cwd()
        self.work_root = Path(sequence.work_root)
        self.operations = operations or DefaultWorkflowSequenceOperations(work_root=self.work_root)
        self.run_root = Path(run_root) if run_root else Path(".ahra") / "workflow-sequences" / sequence.sequence_id

    def run(self, *, dry_run: bool = False) -> WorkflowSequenceResult:
        ordered = self.sequence.ordered_tasks()
        if dry_run:
            return WorkflowSequenceResult(
                sequence_id=self.sequence.sequence_id,
                completed_task_ids=(),
                task_results=tuple(
                    WorkflowSequenceTaskResult(
                        task_id=task.task_id,
                        verification_strategy=task.verification_strategy,
                        status="dry_run",
                    )
                    for task in ordered
                ),
            )

        completed: list[str] = []
        results: list[WorkflowSequenceTaskResult] = []
        for index, task in enumerate(ordered, 1):
            missing_deps = tuple(dep for dep in task.depends_on if dep not in completed)
            if missing_deps:
                return self._halt(
                    completed,
                    results,
                    task,
                    f"{task.task_id} dependencies are not completed: {', '.join(missing_deps)}",
                )

            try:
                before = self.operations.inspect_task(task.task_id)
                state_doc = _state_doc(before)
                state_before = str(state_doc.get("state") or "")
                if state_before == "completed":
                    results.append(
                        WorkflowSequenceTaskResult(
                            task_id=task.task_id,
                            verification_strategy=task.verification_strategy,
                            status="already_completed",
                            state_before=state_before,
                            state_after=state_before,
                        )
                    )
                    completed.append(task.task_id)
                    continue
                claim = self._claim_or_reuse(task, state_doc)
                request_path = self._goal_request_path(task, index)
                report_path = self._review_report_path(task, index)
                goal = self.operations.start_goal(task, request_path)
                goal_status = str(goal.get("goalStatus") or "")
                goal_execution_id = str(goal.get("goalExecutionId") or "")
                if goal_status != "succeeded":
                    blocker = f"{task.task_id} GoalExecution halted with goalStatus={goal_status or '<missing>'}"
                    results.append(
                        WorkflowSequenceTaskResult(
                            task_id=task.task_id,
                            verification_strategy=task.verification_strategy,
                            status="halted",
                            state_before=state_before,
                            goal_execution_id=goal_execution_id or None,
                            goal_status=goal_status or None,
                            blocker=blocker,
                            goal_request=str(request_path),
                            review_report=str(report_path),
                            claim=claim,
                        )
                    )
                    return WorkflowSequenceResult(
                        sequence_id=self.sequence.sequence_id,
                        completed_task_ids=tuple(completed),
                        task_results=tuple(results),
                        halted=True,
                        blocker=blocker,
                    )

                bridge = self.operations.bridge_goal(
                    task,
                    goal_result=goal,
                    claim=claim,
                    request_path=request_path,
                    report_path=report_path,
                    producer_actor=self.sequence.producer_actor,
                    verifier_actor=self.sequence.verifier_actor,
                    max_cycles=self.sequence.max_cycles,
                    lease_ttl_seconds=self.sequence.lease_ttl_seconds,
                )
                terminal = _bridge_terminal_state(bridge)
                after = self.operations.inspect_task(task.task_id)
                state_after = str(_state_doc(after).get("state") or terminal)
                if terminal != "completed" or state_after != "completed":
                    blocker = f"{task.task_id} bridge ended in {terminal or state_after or '<missing>'}"
                    results.append(
                        WorkflowSequenceTaskResult(
                            task_id=task.task_id,
                            verification_strategy=task.verification_strategy,
                            status="halted",
                            state_before=state_before,
                            state_after=state_after,
                            goal_execution_id=goal_execution_id,
                            goal_status=goal_status,
                            bridge_terminal_state=terminal,
                            blocker=blocker,
                            goal_request=str(request_path),
                            review_report=str(report_path),
                            claim=claim,
                        )
                    )
                    return WorkflowSequenceResult(
                        sequence_id=self.sequence.sequence_id,
                        completed_task_ids=tuple(completed),
                        task_results=tuple(results),
                        halted=True,
                        blocker=blocker,
                    )

                results.append(
                    WorkflowSequenceTaskResult(
                        task_id=task.task_id,
                        verification_strategy=task.verification_strategy,
                        status="completed",
                        state_before=state_before,
                        state_after=state_after,
                        goal_execution_id=goal_execution_id,
                        goal_status=goal_status,
                        bridge_terminal_state=terminal,
                        goal_request=str(request_path),
                        review_report=str(report_path),
                        claim=claim,
                    )
                )
                completed.append(task.task_id)
            except Exception as exc:
                return self._halt(completed, results, task, str(exc))

        return WorkflowSequenceResult(
            sequence_id=self.sequence.sequence_id,
            completed_task_ids=tuple(completed),
            task_results=tuple(results),
        )

    def _claim_or_reuse(self, task: WorkflowSequenceTask, state_doc: Mapping[str, Any]) -> WorkflowSequenceClaim:
        state = str(state_doc.get("state") or "")
        version = int(state_doc.get("state_version", 0))
        if state == "ready":
            return WorkflowSequenceClaim.from_mapping(
                self.operations.claim_task(
                    task.task_id,
                    expected_version=version,
                    actor=self.sequence.producer_actor,
                    lease_ttl_seconds=self.sequence.lease_ttl_seconds,
                )
            )
        if state == "working":
            lease = _mapping(state_doc.get("lease"), "state.lease")
            holder = str(lease.get("holder") or "")
            if holder != self.sequence.producer_actor:
                raise WorkflowSequenceError(f"{task.task_id} is already claimed by {holder or '<missing>'}")
            return WorkflowSequenceClaim(
                state_version=version,
                fencing_token=str(lease.get("fencing_token") or ""),
                reused_existing_lease=True,
            )
        raise WorkflowSequenceError(f"{task.task_id} is in state {state or '<missing>'}; expected ready, working, or completed")

    def _goal_request_path(self, task: WorkflowSequenceTask, index: int) -> Path:
        values = self._template_values(task, index)
        if task.goal_request:
            return self._resolve_rendered_path(task.goal_request, values)
        if task.goal_request_template:
            template_path = self._resolve_rendered_path(task.goal_request_template, values)
            return self._materialize_template(template_path, self.run_root / task.task_id / "goal-run-request.yaml", values)
        return self.work_root / "tasks" / task.task_id / "goal-run-request.yaml"

    def _review_report_path(self, task: WorkflowSequenceTask, index: int) -> Path:
        values = self._template_values(task, index)
        if task.review_report:
            return self._resolve_rendered_path(task.review_report, values)
        if task.review_report_template:
            template_path = self._resolve_rendered_path(task.review_report_template, values)
            return self._materialize_template(template_path, self.run_root / task.task_id / "review-report.json", values)
        filename = f"{task.verification_strategy}-gate-report.json"
        return self.work_root / "tasks" / task.task_id / "evidence" / filename

    def _materialize_template(self, template_path: Path, target_path: Path, values: Mapping[str, str]) -> Path:
        raw = template_path.read_text(encoding="utf-8")
        rendered = Template(raw).safe_substitute(values)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(rendered, encoding="utf-8")
        return target_path

    def _resolve_rendered_path(self, value: str, values: Mapping[str, str]) -> Path:
        rendered = Template(value).safe_substitute(values)
        path = Path(rendered)
        if path.is_absolute():
            return path
        return (self.base_dir / path).resolve()

    def _template_values(self, task: WorkflowSequenceTask, index: int) -> dict[str, str]:
        return {
            "SEQUENCE_ID": self.sequence.sequence_id,
            "SEQUENCE_NAME": self.sequence.name,
            "TASK_ID": task.task_id,
            "TASK_ID_LOWER": task.task_id.lower(),
            "TASK_INDEX": str(index),
            "WORK_ROOT": str(self.work_root),
            "VERIFICATION_STRATEGY": task.verification_strategy,
        }

    def _halt(
        self,
        completed: list[str],
        results: list[WorkflowSequenceTaskResult],
        task: WorkflowSequenceTask,
        blocker: str,
    ) -> WorkflowSequenceResult:
        results.append(
            WorkflowSequenceTaskResult(
                task_id=task.task_id,
                verification_strategy=task.verification_strategy,
                status="halted",
                blocker=blocker,
            )
        )
        return WorkflowSequenceResult(
            sequence_id=self.sequence.sequence_id,
            completed_task_ids=tuple(completed),
            task_results=tuple(results),
            halted=True,
            blocker=blocker,
        )


def load_workflow_sequence(path: str | Path) -> WorkflowSequence:
    return WorkflowSequence.from_file(path)


def run_workflow_sequence(
    path: str | Path,
    *,
    dry_run: bool = False,
    operations: WorkflowSequenceOperations | None = None,
    run_root: str | Path | None = None,
) -> WorkflowSequenceResult:
    sequence = load_workflow_sequence(path)
    return WorkflowSequenceRunner(sequence, sequence_path=path, operations=operations, run_root=run_root).run(dry_run=dry_run)


def _state_doc(inspected: Mapping[str, Any]) -> Mapping[str, Any]:
    state = inspected.get("state.json")
    if not isinstance(state, Mapping):
        raise WorkflowSequenceError("task inspection returned no state.json")
    return state


def _bridge_terminal_state(bridge: Mapping[str, Any]) -> str:
    orchestration = bridge.get("orchestration")
    if isinstance(orchestration, Mapping):
        return str(orchestration.get("terminal_state") or orchestration.get("terminalState") or "")
    return str(bridge.get("terminal_state") or bridge.get("terminalState") or "")


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    raise WorkflowSequenceError(f"{field} must be a mapping")


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise WorkflowSequenceError("expected a list of strings")
    return tuple(str(item) for item in value)


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def result_to_json(result: WorkflowSequenceResult) -> str:
    return json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
