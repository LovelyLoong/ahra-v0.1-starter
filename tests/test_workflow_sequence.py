from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Mapping

import yaml

from ahra import cli
from ahra.awkp_task_creator import AwkpTaskCreateRequest, AwkpTaskCreator
from ahra.validation import validate_document
from ahra.workflow_sequence import (
    DefaultWorkflowSequenceOperations,
    WorkflowSequence,
    WorkflowSequenceClaim,
    WorkflowSequenceError,
    WorkflowSequenceRunner,
    WorkflowSequenceTask,
)
from tests.phase1_helpers import aligned_approved_request, first_kernel_evidence_ref, write_gate_report, write_request


ROOT = Path(__file__).resolve().parents[1]


class FakeWorkflowSequenceOperations:
    def __init__(self, *, fail_task: str | None = None, fail_phase: str = "goal") -> None:
        self.fail_task = fail_task
        self.fail_phase = fail_phase
        self.states = {
            "TASK-1000": {"state": "ready", "state_version": 0, "lease": None},
            "TASK-1001": {"state": "ready", "state_version": 0, "lease": None},
        }
        self.calls: list[tuple[str, str]] = []

    def inspect_task(self, task_id: str) -> Mapping[str, Any]:
        self.calls.append(("inspect", task_id))
        return {"state.json": {"task_id": task_id, **self.states[task_id]}}

    def claim_task(
        self,
        task_id: str,
        *,
        expected_version: int,
        actor: str,
        lease_ttl_seconds: int | None,
    ) -> Mapping[str, Any]:
        self.calls.append(("claim", task_id))
        self.assert_state(task_id, "ready", expected_version)
        token = f"FENCE-{task_id}"
        self.states[task_id] = {
            "state": "working",
            "state_version": expected_version + 1,
            "lease": {"holder": actor, "fencing_token": token},
        }
        return {"state_version": expected_version + 1, "fencing_token": token, "event_id": f"EVT-{task_id}-CLAIM"}

    def start_goal(self, task: WorkflowSequenceTask, request_path: Path) -> Mapping[str, Any]:
        self.calls.append(("start_goal", task.task_id))
        if self.fail_task == task.task_id and self.fail_phase == "goal":
            return {"goalExecutionId": f"GEXEC-{task.task_id}", "goalStatus": "failed"}
        return {"goalExecutionId": f"GEXEC-{task.task_id}", "goalStatus": "succeeded"}

    def bridge_goal(
        self,
        task: WorkflowSequenceTask,
        *,
        goal_result: Mapping[str, Any],
        claim: Any,
        request_path: Path,
        report_path: Path,
        producer_actor: str,
        verifier_actor: str,
        max_cycles: int,
        lease_ttl_seconds: int | None,
    ) -> Mapping[str, Any]:
        self.calls.append(("bridge_goal", task.task_id))
        if self.fail_task == task.task_id and self.fail_phase == "bridge":
            self.states[task.task_id] = {
                "state": "changes_requested",
                "state_version": claim.state_version + 1,
                "lease": None,
            }
            return {"orchestration": {"terminal_state": "changes_requested"}}
        self.states[task.task_id] = {
            "state": "completed",
            "state_version": claim.state_version + 1,
            "lease": None,
        }
        return {"orchestration": {"terminal_state": "completed"}}

    def assert_state(self, task_id: str, expected_state: str, expected_version: int) -> None:
        state = self.states[task_id]
        if state["state"] != expected_state or state["state_version"] != expected_version:
            raise AssertionError(f"unexpected state for {task_id}: {state}")


class ReportWritingWorkflowSequenceOperations(DefaultWorkflowSequenceOperations):
    def __init__(self, *, root: Path, report_path: Path) -> None:
        super().__init__(work_root=root / "work")
        self.root = root
        self.report_path = report_path

    def start_goal(self, task: WorkflowSequenceTask, request_path: Path) -> Mapping[str, Any]:
        result = super().start_goal(task, request_path)
        evidence_ref = first_kernel_evidence_ref(self.root / ".ahra" / "artifacts")
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        write_gate_report(self.report_path, task.task_id, evidence_ref, "agent:verifier")
        return result


class WorkflowSequenceTests(unittest.TestCase):
    def test_phase1_example_validates_against_schema(self) -> None:
        errors = validate_document(
            ROOT / "examples" / "workflows" / "phase1-sequence.yaml",
            ROOT / "contracts" / "schemas" / "workflow-sequence.schema.json",
        )
        self.assertEqual(errors, [])

        sequence = WorkflowSequence.from_file(ROOT / "examples" / "workflows" / "phase1-sequence.yaml")
        self.assertEqual([task.task_id for task in sequence.ordered_tasks()][0], "TASK-0062")
        self.assertEqual(sequence.ordered_tasks()[-1].task_id, "TASK-0069")
        self.assertEqual(sequence.ordered_tasks()[-1].verification_strategy, "comprehensive")

    def test_runner_executes_two_tasks_in_dependency_order(self) -> None:
        sequence = WorkflowSequence.from_mapping(_sequence_mapping())
        fake = FakeWorkflowSequenceOperations()

        result = WorkflowSequenceRunner(sequence, operations=fake).run()

        self.assertFalse(result.halted)
        self.assertEqual(result.completed_task_ids, ("TASK-1000", "TASK-1001"))
        self.assertEqual([item.status for item in result.task_results], ["completed", "completed"])
        self.assertEqual(
            [call for call in fake.calls if call[0] in {"claim", "start_goal", "bridge_goal"}],
            [
                ("claim", "TASK-1000"),
                ("start_goal", "TASK-1000"),
                ("bridge_goal", "TASK-1000"),
                ("claim", "TASK-1001"),
                ("start_goal", "TASK-1001"),
                ("bridge_goal", "TASK-1001"),
            ],
        )

    def test_runner_executes_real_claim_goal_bridge_completion_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            work_root = root / "work"
            task_id = "TASK-1000"
            request_path = write_request(root / "requests" / f"{task_id}.yaml", aligned_approved_request(root))
            report_path = root / "reports" / f"{task_id}.json"
            AwkpTaskCreator().create(
                AwkpTaskCreateRequest(
                    task_id=task_id,
                    title="WorkflowSequence integration task",
                    description="Temporary task proving the real WorkflowSequence claim-goal-bridge path.",
                    context_id="CTX-workflow-sequence-test",
                    acceptance_criteria=("The GoalExecution evidence is accepted by EvidenceGate.",),
                    work_root=work_root,
                    actor="agent:test",
                    output_contract_kinds=("verification_summary",),
                )
            )
            sequence = WorkflowSequence.from_mapping(
                _sequence_mapping(
                    work_root=str(work_root),
                    task_defaults={"goalRequest": str(request_path), "reviewReport": str(report_path)},
                    tasks=({"taskId": task_id, "verificationStrategy": "simple"},),
                )
            )

            result = WorkflowSequenceRunner(
                sequence,
                sequence_path=root / "sequence.yaml",
                operations=ReportWritingWorkflowSequenceOperations(root=root, report_path=report_path),
            ).run()

            state = json.loads((work_root / "tasks" / task_id / "state.json").read_text(encoding="utf-8"))
            self.assertFalse(result.halted)
            self.assertEqual(result.completed_task_ids, (task_id,))
            self.assertEqual(result.task_results[0].bridge_terminal_state, "completed")
            self.assertEqual(state["state"], "completed")

    def test_runner_halts_on_failed_task_without_continuing(self) -> None:
        sequence = WorkflowSequence.from_mapping(_sequence_mapping())
        fake = FakeWorkflowSequenceOperations(fail_task="TASK-1001", fail_phase="goal")

        result = WorkflowSequenceRunner(sequence, operations=fake).run()

        self.assertTrue(result.halted)
        self.assertEqual(result.completed_task_ids, ("TASK-1000",))
        self.assertIn("TASK-1001 GoalExecution halted", result.blocker or "")
        self.assertNotIn(("bridge_goal", "TASK-1001"), fake.calls)

    def test_default_operations_fail_closed_when_verifier_report_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            operations = DefaultWorkflowSequenceOperations(work_root=Path(temp) / "work")

            with self.assertRaisesRegex(WorkflowSequenceError, "verifier report does not exist"):
                operations.bridge_goal(
                    WorkflowSequenceTask("TASK-1000"),
                    goal_result={"goalExecutionId": "GEXEC-missing-report"},
                    claim=WorkflowSequenceClaim(state_version=1, fencing_token="FENCE-test"),
                    request_path=Path(temp) / "request.yaml",
                    report_path=Path(temp) / "missing-report.json",
                    producer_actor="agent:producer",
                    verifier_actor="agent:verifier",
                    max_cycles=1,
                    lease_ttl_seconds=None,
                )

    def test_cli_workflow_sequence_run_invokes_runner_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            sequence_path = Path(temp) / "sequence.yaml"
            sequence_path.write_text(yaml.safe_dump(_sequence_mapping(), sort_keys=False), encoding="utf-8")

            code, payload = _run_cli(["workflow-sequence", "run", str(sequence_path), "--dry-run"])

        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["result"]["halted"])
        self.assertEqual(
            [item["taskId"] for item in payload["result"]["taskResults"]],
            ["TASK-1000", "TASK-1001"],
        )


def _sequence_mapping(
    *,
    work_root: str = "work",
    task_defaults: Mapping[str, Any] | None = None,
    tasks: tuple[Mapping[str, Any], ...] | None = None,
) -> dict[str, Any]:
    return {
        "apiVersion": "ahra.dev/v1alpha1",
        "kind": "WorkflowSequence",
        "metadata": {"name": "test-sequence", "sequenceId": "WSEQ-TEST-SEQUENCE"},
        "spec": {
            "workRoot": work_root,
            "producerActor": "agent:producer",
            "verifierActor": "agent:verifier",
            "taskDefaults": dict(task_defaults or {
                "goalRequest": "requests/${TASK_ID}.yaml",
                "reviewReport": "reports/${TASK_ID}.json",
            }),
            "tasks": list(tasks or (
                {"taskId": "TASK-1000", "verificationStrategy": "simple"},
                {"taskId": "TASK-1001", "dependsOn": ["TASK-1000"], "verificationStrategy": "comprehensive"},
            )),
        },
    }


def _run_cli(argv: list[str]) -> tuple[int, dict[str, Any]]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = cli.main(argv)
    payload = json.loads(stdout.getvalue() or stderr.getvalue())
    return code, payload


if __name__ == "__main__":
    unittest.main()
