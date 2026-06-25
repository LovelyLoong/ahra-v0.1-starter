from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

from ahra.adapters.codex_sdk import CodexSDKDriver
from ahra.dynamic_fixture import write_dynamic_repair_fixture_report
from ahra.evidence_gate import EvidenceGateError, evaluate_task_gate, inspect_task
from ahra.ports import AgentDriverRegistry, AgentRole, AgentRunRequest, AgentRunResult
from ahra.reference_runner.invocation import (
    load_workflow_resume_request,
    load_workflow_run_request,
    resume_workflow,
    run_workflow,
    validate_workflow_resume_request,
    validate_workflow_run_request,
)
from ahra.reference_runner.models import (
    CriterionAssessment,
    GoalReviewResult,
    NextStepDecision,
    PlanAction,
    ReviewResult,
    ReviewVerdict,
    WorkReport,
    to_jsonable,
)


class FixtureDriver:
    """In-process fixture driver for CLI smoke tests only."""

    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        if request.role == AgentRole.EXECUTOR:
            workspace = Path(str(request.workspace_ref))
            task = request.payload["task"]
            value = _requested_value(task)
            target = workspace / "value.py"
            if target.exists() or value is not None:
                target.write_text(f"VALUE = {value or 2}\n", encoding="utf-8")
            return AgentRunResult(
                output=WorkReport(
                    summary="Fixture driver applied deterministic test change.",
                    changed_files=("value.py",) if target.exists() else (),
                    verification_commands_run=(),
                    known_risks=("Fixture driver is not a production driver.",),
                )
            )
        if request.role == AgentRole.TASK_REVIEWER:
            task = request.payload["task"]
            return AgentRunResult(
                output=ReviewResult(
                    verdict=ReviewVerdict.PASS,
                    summary="Fixture reviewer accepted deterministic smoke output.",
                    criteria=tuple(
                        CriterionAssessment(
                            criterion=criterion,
                            passed=True,
                            evidence="Fixture smoke test criterion accepted.",
                        )
                        for criterion in task.acceptance_criteria
                    ),
                    confidence=1.0,
                )
            )
        if request.role == AgentRole.GOAL_REVIEWER:
            goal = request.payload["goal"]
            return AgentRunResult(
                output=GoalReviewResult(
                    verdict=ReviewVerdict.PASS,
                    summary="Fixture goal reviewer accepted deterministic smoke output.",
                    satisfied_criteria=goal.success_criteria,
                    confidence=1.0,
                )
            )
        if request.role == AgentRole.PLANNER:
            return AgentRunResult(
                output=NextStepDecision(
                    action=PlanAction.ESCALATE,
                    rationale="Fixture driver does not propose follow-up work.",
                )
            )
        raise ValueError(f"unsupported fixture driver role: {request.role}")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        result = _dispatch(args)
    except (EvidenceGateError, ValueError, OSError, RuntimeError) as exc:
        _print({"ok": False, "error": str(exc)}, stream=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - CLI must fail closed with a structured error.
        _print({"ok": False, "error": repr(exc)}, stream=sys.stderr)
        return 2
    _print({"ok": True, "result": result})
    return 0


def _dispatch(args: argparse.Namespace) -> Any:
    if args.group == "workflow":
        return _workflow_command(args)
    if args.group == "task":
        return _task_command(args)
    if args.group == "fixture":
        return _fixture_command(args)
    if args.group == "evidence-gate":
        return _evidence_gate_command(args)
    if args.group == "doctor":
        return _doctor_command(args)
    raise ValueError(f"unknown command group: {args.group}")


def _workflow_command(args: argparse.Namespace) -> Any:
    if args.workflow_command == "validate":
        return _validate_workflow_request(Path(args.request))
    if args.workflow_command == "start":
        request = load_workflow_run_request(Path(args.request))
        drivers = _driver_registry(enable_fixture_driver=args.enable_fixture_driver)
        envelope = asyncio.run(run_workflow(request, drivers=drivers))
        return _ensure_successful_envelope(envelope)
    if args.workflow_command == "resume":
        request = load_workflow_resume_request(Path(args.request))
        drivers = _driver_registry(enable_fixture_driver=args.enable_fixture_driver)
        envelope = asyncio.run(resume_workflow(request, drivers=drivers))
        return _ensure_successful_envelope(envelope)
    if args.workflow_command == "inspect":
        return _inspect_workflow(Path(args.artifact_dir))
    raise ValueError(f"unknown workflow command: {args.workflow_command}")


def _task_command(args: argparse.Namespace) -> Any:
    if args.task_command == "inspect":
        return inspect_task(args.task, work_root=args.work_root)
    raise ValueError(f"unknown task command: {args.task_command}")


def _fixture_command(args: argparse.Namespace) -> Any:
    if args.fixture_command == "dynamic-repair":
        report = write_dynamic_repair_fixture_report(Path(args.fixture), Path(args.report))
        return {
            "schema_version": report["schema_version"],
            "report": str(Path(args.report)),
            "goal": report["goal"],
            "selectedFewerThanFull": report["verification"]["selectedFewerThanFull"],
            "finalCompletionAccepted": report["verification"]["finalCompletionAccepted"],
            "unauthorizedWriteAllowed": report["security"]["unauthorizedWriteAllowed"],
            "terminalStatusAfterResume": report["resume"]["terminalStatusAfterResume"],
        }
    raise ValueError(f"unknown fixture command: {args.fixture_command}")


def _evidence_gate_command(args: argparse.Namespace) -> Any:
    if args.evidence_gate_command != "evaluate":
        raise ValueError(f"unknown evidence-gate command: {args.evidence_gate_command}")
    return evaluate_task_gate(
        args.task,
        work_root=args.work_root,
        expected_version=args.expected_version,
        report_path=args.report,
        actor=args.actor,
        decision=args.decision,
        dry_run=args.dry_run,
    ).to_dict()


def _doctor_command(args: argparse.Namespace) -> Any:
    commands = [
        [sys.executable, "-B", "scripts/check.py"],
        [sys.executable, "-B", "scripts/lint_awkp.py"],
        ["git", "diff", "--check"],
    ]
    if args.dry_run:
        return {"commands": commands}
    results = []
    for command in commands:
        completed = subprocess.run(command, check=False, text=True, capture_output=True)
        results.append(
            {
                "command": command,
                "exit_code": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
        )
    return {"passed": all(item["exit_code"] == 0 for item in results), "commands": results}


def _validate_workflow_request(path: Path) -> dict[str, Any]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"workflow request must be an object: {path}")
    kind = document.get("kind")
    if kind == "WorkflowRunRequest":
        request = load_workflow_run_request(path)
        validate_workflow_run_request(request)
        return {
            "kind": kind,
            "name": request.name,
            "module_id": request.module_id,
            "driver_ref": request.driver_ref,
            "artifact_dir": request.artifact_dir,
        }
    if kind == "WorkflowResumeRequest":
        request = load_workflow_resume_request(path)
        validate_workflow_resume_request(request)
        return {
            "kind": kind,
            "name": request.name,
            "run_id": request.run_id,
            "module_id": request.module_id,
            "driver_ref": request.driver_ref,
            "artifact_dir": request.artifact_dir,
        }
    raise ValueError(f"unsupported workflow request kind: {kind!r}")


def _inspect_workflow(artifact_dir: Path) -> dict[str, Any]:
    if not artifact_dir.exists():
        raise ValueError(f"workflow artifact directory does not exist: {artifact_dir}")
    if not artifact_dir.is_dir():
        raise ValueError(f"workflow artifact path is not a directory: {artifact_dir}")
    result: dict[str, Any] = {"artifact_dir": str(artifact_dir.resolve())}
    for name in [
        "workflow-run-request.json",
        "workflow-run-result.json",
        "workflow-resume-request.json",
        "workflow-resume-result.json",
        "artifact-manifest.json",
        "evidence-manifest.json",
        "workspace.json",
    ]:
        path = artifact_dir / name
        result[name] = _load_json(path) if path.exists() else None
    events_path = artifact_dir / "events.jsonl"
    if events_path.exists():
        events = [
            json.loads(line)
            for line in events_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        result["events"] = events
        result["timeline"] = _workflow_timeline(events)
        result["runtime_status"] = _workflow_runtime_status(result, events)
    return result


def _driver_registry(*, enable_fixture_driver: bool) -> AgentDriverRegistry:
    registry = AgentDriverRegistry()
    registry.register("codex-python-sdk", CodexSDKDriver())
    if enable_fixture_driver:
        registry.register("fake-reference", FixtureDriver())
    return registry


def _ensure_successful_envelope(envelope: Any) -> dict[str, Any]:
    summary = _envelope_summary(envelope)
    if str(envelope.status) in {"error", "rejected", "blocked"}:
        raise RuntimeError(
            "workflow finished in a failure state: "
            f"{envelope.status}; artifact_dir={envelope.artifact_dir}"
        )
    return summary

def _envelope_summary(envelope: Any) -> dict[str, Any]:
    return {
        "run_id": envelope.run_id,
        "module_id": envelope.module_id,
        "driver_ref": envelope.driver_ref,
        "status": str(envelope.status),
        "artifact_dir": envelope.artifact_dir,
        "result": to_jsonable(envelope.result),
    }


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _workflow_timeline(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    timeline = []
    for event in events:
        event_type = str(event.get("type") or "").removeprefix("dev.ahra.workflow.")
        if event_type.endswith(".v1"):
            event_type = event_type[:-3]
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        if event_type in {
            "task_started",
            "attempt_started",
            "executor_started",
            "agent_heartbeat",
            "executor_finished",
            "deterministic_gate_started",
            "deterministic_gate_finished",
            "checks_started",
            "checks_finished",
            "reviewer_started",
            "reviewer_output_invalid",
            "reviewer_finished",
            "commit_started",
            "commit_finished",
            "awkp_task_claimed",
            "source_workspace_integrated",
            "task_accepted",
            "task_rejected",
            "attempt_error",
            "scheduler_decision_recorded",
            "terminal_failure_recorded",
        }:
            timeline.append(
                {
                    "time": event.get("time"),
                    "step": event_type,
                    "task_id": data.get("task_id"),
                    "attempt": data.get("attempt"),
                    "review_attempt": data.get("review_attempt"),
                    "status": data.get("status") or data.get("review_verdict") or data.get("verdict"),
                    "retryable": data.get("retryable"),
                    "phase": data.get("phase"),
                    "idle_seconds": data.get("idle_seconds"),
                }
            )
    return timeline


def _workflow_runtime_status(result: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    run_result = result.get("workflow-run-result.json")
    if isinstance(run_result, dict):
        return {"state": str(run_result.get("status") or "finished")}
    if not events:
        return {"state": "empty"}
    last = events[-1]
    event_type = str(last.get("type") or "").removeprefix("dev.ahra.workflow.")
    if event_type.endswith(".v1"):
        event_type = event_type[:-3]
    data = last.get("data") if isinstance(last.get("data"), dict) else {}
    state = "incomplete"
    if event_type in {"executor_started", "agent_heartbeat", "attempt_started"}:
        state = "running_or_interrupted"
    if event_type in {"attempt_error", "terminal_failure_recorded", "task_rejected"}:
        state = "failed_without_result_artifact"
    return {
        "state": state,
        "last_event": event_type,
        "last_event_time": last.get("time"),
        "phase": data.get("phase"),
        "attempt": data.get("attempt"),
        "idle_seconds": data.get("idle_seconds"),
    }


def _requested_value(task: Any) -> int | None:
    text = " ".join([task.id, task.title, task.objective, *task.acceptance_criteria])
    if "3" in text:
        return 3
    if "2" in text:
        return 2
    return None


def _print(payload: dict[str, Any], *, stream: Any | None = None) -> None:
    stream = stream or sys.stdout
    print(json.dumps(payload, ensure_ascii=False, indent=2), file=stream)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ahra", description="Operate the AHRA local reference framework.")
    groups = parser.add_subparsers(dest="group", required=True)

    workflow = groups.add_parser("workflow", help="Validate, start, inspect, or resume workflow runs.")
    workflow_commands = workflow.add_subparsers(dest="workflow_command", required=True)
    workflow_validate = workflow_commands.add_parser("validate", help="Validate a workflow request file.")
    workflow_validate.add_argument("request", help="WorkflowRunRequest or WorkflowResumeRequest YAML path.")

    workflow_start = workflow_commands.add_parser("start", help="Start a WorkflowRunRequest.")
    workflow_start.add_argument("request", help="WorkflowRunRequest YAML path.")
    workflow_start.add_argument(
        "--enable-fixture-driver",
        action="store_true",
        help="Register fake-reference for local fixture smoke tests only.",
    )

    workflow_inspect = workflow_commands.add_parser("inspect", help="Inspect a local workflow artifact directory.")
    workflow_inspect.add_argument("artifact_dir", help="Local workflow artifact directory.")

    workflow_resume = workflow_commands.add_parser("resume", help="Resume a WorkflowResumeRequest.")
    workflow_resume.add_argument("request", help="WorkflowResumeRequest YAML path.")
    workflow_resume.add_argument(
        "--enable-fixture-driver",
        action="store_true",
        help="Register fake-reference for local fixture smoke tests only.",
    )

    task = groups.add_parser("task", help="Inspect AWKP task state and acceptance criteria.")
    task_commands = task.add_subparsers(dest="task_command", required=True)
    task_inspect = task_commands.add_parser("inspect", help="Inspect task state, manifests, events, and criteria.")
    task_inspect.add_argument("task", help="Task ID such as TASK-0014, or path to a task directory.")
    task_inspect.add_argument("--work-root", default="work", help="AWKP work root containing tasks/.")

    fixture = groups.add_parser("fixture", help="Run deterministic local fixture scenarios.")
    fixture_commands = fixture.add_subparsers(dest="fixture_command", required=True)
    fixture_repair = fixture_commands.add_parser(
        "dynamic-repair",
        help="Run the isolated dynamic Goal-to-repair fixture.",
    )
    fixture_repair.add_argument("--fixture", required=True, help="Fixture project directory.")
    fixture_repair.add_argument("--report", required=True, help="JSON report output path.")

    gate = groups.add_parser("evidence-gate", help="Evaluate AWKP task completion evidence.")
    gate_commands = gate.add_subparsers(dest="evidence_gate_command", required=True)
    gate_eval = gate_commands.add_parser("evaluate", help="Validate evidence and transition task state.")
    gate_eval.add_argument("task", help="Task ID such as TASK-0014, or path to a task directory.")
    gate_eval.add_argument("--work-root", default="work", help="AWKP work root containing tasks/.")
    gate_eval.add_argument("--expected-version", required=True, type=int)
    gate_eval.add_argument("--report", required=True, help="Verifier report JSON path.")
    gate_eval.add_argument("--actor", required=True, help="Verifier actor, for example agent:verifier.")
    gate_eval.add_argument("--decision", choices=["approve", "request_changes"])
    gate_eval.add_argument("--dry-run", action="store_true")

    doctor = groups.add_parser("doctor", help="Run local framework health checks.")
    doctor.add_argument("--dry-run", action="store_true", help="Print checks without running them.")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
