from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from ahra.alignment_session import AlignmentSessionError
from ahra.awkp_state_writer import AwkpTaskStateWriter
from ahra.awkp_task_creator import AwkpTaskCreateRequest, AwkpTaskCreator
from ahra.evidence_gate import EvidenceGateError, evaluate_task_gate, inspect_task
from ahra.goal_operations import GoalAwkpBridge, GoalAwkpBridgeRequest, GoalOperationError, GoalOperationService
from ahra.orchestrator import AwkpTaskOrchestrationRequest, AwkpTaskReviewOrchestrator
from ahra.ports import AgentDriverRegistry, AgentRole, AgentRunRequest, AgentRunResult


class FixtureDriver:
    """In-process fixture driver for CLI smoke tests only."""

    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        from ahra.reference_runner.models import (
            CriterionAssessment,
            GoalReviewResult,
            NextStepDecision,
            PlanAction,
            ReviewResult,
            ReviewVerdict,
            WorkReport,
        )

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
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    parser = _build_parser(
        include_legacy_workflow=bool(raw_argv and raw_argv[0] == "workflow"),
        include_workflow_sequence=True,
    )
    args = parser.parse_args(raw_argv)
    try:
        result = _dispatch(args)
    except AlignmentSessionError as exc:
        _print({"ok": False, "error": exc.to_dict()}, stream=sys.stderr)
        return 2
    except GoalOperationError as exc:
        _print({"ok": False, **exc.to_error_dict()}, stream=sys.stderr)
        return 2
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
    if args.group == "workflow-a":
        return _workflow_a_command(args)
    if args.group == "workflow-sequence":
        return _workflow_sequence_command(args)
    if args.group == "task":
        return _task_command(args)
    if args.group == "fixture":
        return _fixture_command(args)
    if args.group == "goal":
        return _goal_command(args)
    if args.group == "evidence-gate":
        return _evidence_gate_command(args)
    if args.group == "doctor":
        return _doctor_command(args)
    raise ValueError(f"unknown command group: {args.group}")


def _workflow_command(args: argparse.Namespace) -> Any:
    from ahra.reference_runner.invocation import (
        load_workflow_resume_request,
        load_workflow_run_request,
        resume_workflow,
        run_workflow,
    )

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


def _workflow_a_command(args: argparse.Namespace) -> Any:
    from ahra.workflow_a_cli import (
        admit_request,
        advance_session,
        approve_requirement,
        authorize_request,
        draft_request,
        read_snapshot,
        start_session,
    )

    if args.workflow_a_command == "start":
        return start_session(
            intent_path=Path(args.intent),
            session_path=Path(args.session),
            profile_ref=args.profile_ref,
            runtime_ref=args.runtime_ref,
            runtime_digest=args.runtime_digest,
            workspace_ref=args.workspace_ref,
            artifact_dir=args.artifact_dir,
            store_path=args.store_path,
            producer_actor=args.producer_actor,
        )
    if args.workflow_a_command == "advance":
        return asyncio.run(
            advance_session(
                session_path=Path(args.session),
                message=args.message,
                actor=args.actor,
                driver=_workflow_a_driver(args),
                timeout_seconds=args.timeout_seconds,
            )
        )
    if args.workflow_a_command == "snapshot":
        return read_snapshot(session_path=Path(args.session))
    if args.workflow_a_command == "approve-requirement":
        return approve_requirement(session_path=Path(args.session), actor=args.actor)
    if args.workflow_a_command == "draft":
        return asyncio.run(
            draft_request(
                session_path=Path(args.session),
                request_draft_path=Path(args.request_draft),
                approval_path=Path(args.approval) if args.approval else None,
                driver=_workflow_a_driver(args),
                timeout_seconds=args.timeout_seconds,
            )
        )
    if args.workflow_a_command == "admit":
        return admit_request(request_draft_path=Path(args.request_draft))
    if args.workflow_a_command == "authorize":
        return authorize_request(
            request_draft_path=Path(args.request_draft),
            approval_path=Path(args.approval),
            output_path=Path(args.output),
            actor=args.actor,
            reason=args.reason,
        )
    raise ValueError(f"unknown workflow-a command: {args.workflow_a_command}")


def _workflow_sequence_command(args: argparse.Namespace) -> Any:
    from ahra.workflow_sequence import WorkflowSequenceRunner, load_workflow_sequence

    if args.workflow_sequence_command != "run":
        raise ValueError(f"unknown workflow-sequence command: {args.workflow_sequence_command}")
    sequence = load_workflow_sequence(Path(args.sequence))
    if args.work_root:
        from dataclasses import replace

        sequence = replace(sequence, work_root=args.work_root)
    runner = WorkflowSequenceRunner(
        sequence,
        sequence_path=Path(args.sequence),
        run_root=Path(args.run_root) if args.run_root else None,
    )
    return runner.run(dry_run=args.dry_run).to_dict()


def _task_command(args: argparse.Namespace) -> Any:
    if args.task_command == "inspect":
        return inspect_task(args.task, work_root=args.work_root)
    if args.task_command == "create":
        request = AwkpTaskCreateRequest(
            task_id=args.task,
            title=args.title or "",
            description=args.description or "",
            context_id=args.context_id or "",
            acceptance_criteria=tuple(args.acceptance or ()),
            work_root=args.work_root,
            priority=args.priority,
            risk_level=args.risk_level,
            requester=args.requester,
            reviewer=args.reviewer,
            actor=args.actor,
            depends_on=tuple(args.depends_on or ()),
            input_refs=tuple(args.input_ref or ()),
            output_contract_kinds=tuple(args.output_contract or ()),
        )
        return asdict(AwkpTaskCreator().create(request))
    if args.task_command == "claim":
        idempotency_key = args.idempotency_key or f"{args.task}:task-claim:{args.expected_version}"
        result = AwkpTaskStateWriter(work_root=args.work_root).acquire_working(
            args.task,
            expected_version=args.expected_version,
            actor=args.actor,
            idempotency_key=idempotency_key,
            reason=args.reason,
            lease_ttl_seconds=args.lease_ttl_seconds,
        )
        return asdict(result)
    if args.task_command == "orchestrate-review":
        request = AwkpTaskOrchestrationRequest(
            task=args.task,
            work_root=args.work_root,
            expected_version=args.expected_version,
            producer_actor=args.producer_actor,
            verifier_actor=args.verifier_actor,
            fencing_token=args.fencing_token,
            report_paths=tuple(args.report or ()),
            max_cycles=args.max_cycles,
            idempotency_key_prefix=args.idempotency_key_prefix,
            review_refs=tuple(args.ref or ("state.json", "artifact-manifest.json", "evidence-manifest.json")),
            artifact_refs=tuple(args.artifact_ref or ()),
            evidence_refs=tuple(args.evidence_ref or ()),
            lease_ttl_seconds=args.lease_ttl_seconds,
            reason=args.reason,
        )
        return asdict(AwkpTaskReviewOrchestrator(work_root=args.work_root).run(request))
    raise ValueError(f"unknown task command: {args.task_command}")


def _fixture_command(args: argparse.Namespace) -> Any:
    if args.fixture_command == "dynamic-repair":
        from ahra.dynamic_fixture import write_dynamic_repair_fixture_report

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


def _goal_command(args: argparse.Namespace) -> Any:
    service = _goal_service(args)
    if args.goal_command == "validate":
        return service.validate(Path(args.request))
    if args.goal_command == "plan":
        return service.plan(Path(args.request))
    if args.goal_command == "start":
        return service.start(Path(args.request), run_once=args.run_once)
    if args.goal_command == "inspect":
        return service.inspect(
            args.goal_execution_id,
            db_path=Path(args.db),
            artifact_dir=Path(args.artifact_dir) if args.artifact_dir else None,
        )
    if args.goal_command == "resume":
        return service.resume(args.goal_execution_id, request_path=Path(args.request))
    if args.goal_command == "cancel":
        return service.cancel(args.goal_execution_id, db_path=Path(args.db), reason=args.reason)
    if args.goal_command == "bridge-awkp-task":
        request = GoalAwkpBridgeRequest(
            goal_execution_id=args.goal_execution_id,
            task=args.task,
            work_root=args.work_root,
            expected_task_version=args.expected_task_version,
            producer_actor=args.producer_actor,
            verifier_actor=args.verifier_actor,
            fencing_token=args.fencing_token,
            report_paths=tuple(args.report or ()),
            db_path=Path(args.db),
            artifact_dir=Path(args.artifact_dir),
            max_cycles=args.max_cycles,
            idempotency_key_prefix=args.idempotency_key_prefix,
            lease_ttl_seconds=args.lease_ttl_seconds,
            reason=args.reason,
        )
        return asdict(GoalAwkpBridge(work_root=args.work_root).run(request))
    raise ValueError(f"unknown goal command: {args.goal_command}")


def _goal_service(args: argparse.Namespace) -> GoalOperationService:
    if getattr(args, "allow_development_agent", False):
        from ahra.adapters.codex_sdk import CodexSDKDriver

        return GoalOperationService(real_executor_driver=CodexSDKDriver())
    return GoalOperationService()


def _workflow_a_driver(args: argparse.Namespace) -> Any:
    registry = _driver_registry(enable_fixture_driver=False)
    if getattr(args, "enable_fixture_driver", False):
        from ahra.workflow_a_cli import WorkflowAFixtureDriver

        registry.register("workflow-a-fixture", WorkflowAFixtureDriver())
    return registry.get(args.driver_ref)


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
    from ahra.reference_runner.invocation import (
        load_workflow_resume_request,
        load_workflow_run_request,
        validate_workflow_resume_request,
        validate_workflow_run_request,
    )

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
    from ahra.adapters.codex_sdk import CodexSDKDriver

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
    from ahra.reference_runner.models import to_jsonable

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


def _build_parser(
    *,
    include_legacy_workflow: bool = False,
    include_workflow_sequence: bool = True,
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ahra", description="Operate the AHRA dynamic-kernel local framework.")
    visible_groups = "{workflow-a,workflow-sequence,task,fixture,goal,evidence-gate,doctor}"
    if include_legacy_workflow:
        visible_groups = "{workflow,workflow-a,workflow-sequence,task,fixture,goal,evidence-gate,doctor}"
    groups = parser.add_subparsers(dest="group", required=True, metavar=visible_groups)

    if include_legacy_workflow:
        workflow = groups.add_parser("workflow", help="Legacy workflow compatibility commands.")
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

    workflow_a = groups.add_parser("workflow-a", help="Experimental Workflow A intent alignment lifecycle.")
    workflow_a_commands = workflow_a.add_subparsers(dest="workflow_a_command", required=True)
    workflow_a_start = workflow_a_commands.add_parser("start", help="Start an experimental Workflow A session.")
    workflow_a_start.add_argument("intent", help="IntentDraft YAML path.")
    workflow_a_start.add_argument("--session", required=True, help="Session JSON path to write.")
    workflow_a_start.add_argument("--profile-ref", help="Optional Goal operation profile ref.")
    workflow_a_start.add_argument("--runtime-ref", help="Optional runtime ref.")
    workflow_a_start.add_argument("--runtime-digest", help="Optional runtime digest.")
    workflow_a_start.add_argument("--workspace-ref", default="workspace", help="Workspace ref recorded in RequestDraft.")
    workflow_a_start.add_argument("--artifact-dir", default=".ahra/artifacts", help="Artifact dir recorded in RequestDraft.")
    workflow_a_start.add_argument("--store-path", default=".ahra/goal-control.sqlite3", help="SQLite store path recorded in RequestDraft.")
    workflow_a_start.add_argument("--producer-actor", default="agent:alignment-session", help="Producer actor for RequestDraft.")
    workflow_a_advance = workflow_a_commands.add_parser("advance", help="Advance an experimental Workflow A session.")
    workflow_a_advance.add_argument("--session", required=True, help="Session JSON path.")
    workflow_a_advance.add_argument("--message", required=True, help="Human message for the alignment turn.")
    workflow_a_advance.add_argument("--actor", default="human:maintainer", help="Actor for the alignment turn.")
    workflow_a_advance.add_argument("--driver-ref", default="codex-python-sdk", help="AgentDriver ref.")
    workflow_a_advance.add_argument("--enable-fixture-driver", action="store_true", help="Enable workflow-a-fixture driver for smoke tests only.")
    workflow_a_advance.add_argument("--timeout-seconds", type=float, help="Maximum seconds to wait for one AgentDriver call.")
    workflow_a_snapshot = workflow_a_commands.add_parser("snapshot", help="Read an experimental Workflow A session snapshot.")
    workflow_a_snapshot.add_argument("--session", required=True, help="Session JSON path.")
    workflow_a_approve = workflow_a_commands.add_parser("approve-requirement", help="Apply Human Gate 1 requirement approval.")
    workflow_a_approve.add_argument("--session", required=True, help="Session JSON path.")
    workflow_a_approve.add_argument("--actor", required=True, help="Human actor approving the frozen requirement.")
    workflow_a_draft = workflow_a_commands.add_parser("draft", help="Draft RequestDraft and optional ApprovalService authorization.")
    workflow_a_draft.add_argument("--session", required=True, help="Session JSON path.")
    workflow_a_draft.add_argument("--request-draft", required=True, help="RequestDraft JSON path to write.")
    workflow_a_draft.add_argument("--approval", help="Approval JSON path to write waiting_auth Gate 2 record.")
    workflow_a_draft.add_argument("--driver-ref", default="codex-python-sdk", help="AgentDriver ref.")
    workflow_a_draft.add_argument("--enable-fixture-driver", action="store_true", help="Enable workflow-a-fixture driver for smoke tests only.")
    workflow_a_draft.add_argument("--timeout-seconds", type=float, help="Maximum seconds to wait for one AgentDriver call.")
    workflow_a_admit = workflow_a_commands.add_parser("admit", help="Run RequestDraftAdmission on a RequestDraft JSON file.")
    workflow_a_admit.add_argument("--request-draft", required=True, help="RequestDraft JSON path.")
    workflow_a_authorize = workflow_a_commands.add_parser("authorize", help="Apply Human Gate 2 and freeze GoalExecutionRequest.")
    workflow_a_authorize.add_argument("--request-draft", required=True, help="RequestDraft JSON path.")
    workflow_a_authorize.add_argument("--approval", required=True, help="Approval JSON path from draft.")
    workflow_a_authorize.add_argument("--output", required=True, help="GoalExecutionRequest YAML path to write.")
    workflow_a_authorize.add_argument("--actor", required=True, help="Human actor authorizing the contract.")
    workflow_a_authorize.add_argument("--reason", default="", help="Authorization reason.")

    sequence = groups.add_parser("workflow-sequence", help="Run a governed multi-task sequence.")
    sequence_commands = sequence.add_subparsers(dest="workflow_sequence_command", required=True)
    sequence_run = sequence_commands.add_parser("run", help="Run a WorkflowSequence YAML definition.")
    sequence_run.add_argument("sequence", help="WorkflowSequence YAML path.")
    sequence_run.add_argument("--work-root", help="Override the sequence workRoot.")
    sequence_run.add_argument("--run-root", help="Directory for materialized task-scoped request templates.")
    sequence_run.add_argument("--dry-run", action="store_true", help="Validate ordering and CLI wiring without side effects.")

    task = groups.add_parser("task", help="create, claim, orchestrate-review, and inspect AWKP tasks.")
    task_commands = task.add_subparsers(dest="task_command", required=True)
    task_create = task_commands.add_parser("create", help="Create a lint-clean AWKP task skeleton.")
    task_create.add_argument("task", help="Task ID such as TASK-0062.")
    task_create.add_argument("--work-root", default="work", help="AWKP work root containing tasks/.")
    task_create.add_argument("--title", help="Task title.")
    task_create.add_argument("--description", help="Task description and initial Goal section.")
    task_create.add_argument("--context-id", help="Context id such as CTX-workflow-autonomy.")
    task_create.add_argument("--acceptance", action="append", help="Acceptance criterion text. Repeat for multiple criteria.")
    task_create.add_argument("--priority", default="P1", help="AWKP priority value.")
    task_create.add_argument("--risk-level", default="R1", help="AWKP risk level value.")
    task_create.add_argument("--requester", default="human:maintainer", help="Requester identity.")
    task_create.add_argument("--reviewer", default="agent:independent-verifier", help="Reviewer identity.")
    task_create.add_argument("--actor", default="human:maintainer", help="Actor recorded on the task_created event.")
    task_create.add_argument("--depends-on", action="append", help="Dependency task id. Repeat for multiple dependencies.")
    task_create.add_argument("--input-ref", action="append", help="Input ref. Repeat for multiple refs.")
    task_create.add_argument("--output-contract", action="append", help="Output contract kind. Repeat for multiple kinds.")

    task_claim = task_commands.add_parser("claim", help="Claim a ready AWKP task through the governed CAS writer.")
    task_claim.add_argument("task", help="Task ID such as TASK-0062, or path to a task directory.")
    task_claim.add_argument("--work-root", default="work", help="AWKP work root containing tasks/.")
    task_claim.add_argument("--expected-version", required=True, type=int, help="Expected state_version for CAS.")
    task_claim.add_argument("--actor", required=True, help="Lease holder recorded on the working state.")
    task_claim.add_argument("--idempotency-key", help="Unique idempotency key for the claim event.")
    task_claim.add_argument("--lease-ttl-seconds", type=int, help="Optional positive lease TTL.")
    task_claim.add_argument(
        "--reason",
        default="Claimed task through ahra task claim.",
        help="Reason recorded on the lease_acquired event.",
    )

    task_orchestrate = task_commands.add_parser(
        "orchestrate-review",
        help="Request review and invoke EvidenceGate under a distinct verifier identity.",
    )
    task_orchestrate.add_argument("task", help="Task ID such as TASK-0062, or path to a task directory.")
    task_orchestrate.add_argument("--work-root", default="work", help="AWKP work root containing tasks/.")
    task_orchestrate.add_argument("--expected-version", required=True, type=int, help="Expected working state_version.")
    task_orchestrate.add_argument("--producer-actor", required=True, help="Current task lease holder.")
    task_orchestrate.add_argument("--verifier-actor", required=True, help="Independent EvidenceGate verifier actor.")
    task_orchestrate.add_argument("--fencing-token", required=True, help="Current producer lease fencing token.")
    task_orchestrate.add_argument("--report", action="append", required=True, help="Verifier input report JSON. Repeat for retry cycles.")
    task_orchestrate.add_argument("--max-cycles", type=int, default=1, help="Maximum EvidenceGate cycles before adding a blocker.")
    task_orchestrate.add_argument("--idempotency-key-prefix", help="Prefix for generated review/reclaim/blocker events.")
    task_orchestrate.add_argument("--ref", action="append", help="Review event ref. Repeat for multiple refs.")
    task_orchestrate.add_argument("--artifact-ref", action="append", help="Artifact ref to attach on review.")
    task_orchestrate.add_argument("--evidence-ref", action="append", help="Evidence ref to attach on review.")
    task_orchestrate.add_argument("--lease-ttl-seconds", type=int, help="Optional reclaim lease TTL.")
    task_orchestrate.add_argument(
        "--reason",
        default="Task evidence is ready for automated independent EvidenceGate review.",
        help="Reason recorded on review_requested events.",
    )

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

    goal = groups.add_parser("goal", help="Operate durable generic GoalExecution requests.")
    goal_commands = goal.add_subparsers(dest="goal_command", required=True)
    goal_validate = goal_commands.add_parser("validate", help="Validate a GoalExecutionRequest without side effects.")
    goal_validate.add_argument("request", help="GoalExecutionRequest YAML path.")

    goal_plan = goal_commands.add_parser("plan", help="Compile a GoalExecutionRequest to admitted PlanIR artifacts.")
    goal_plan.add_argument("request", help="GoalExecutionRequest YAML path.")

    goal_start = goal_commands.add_parser("start", help="Start a durable GoalExecution from a request.")
    goal_start.add_argument("request", help="GoalExecutionRequest YAML path.")
    goal_start.add_argument("--run-once", action="store_true", help="Run one scheduler batch and leave remaining work resumable.")
    goal_start.add_argument(
        "--allow-development-agent",
        action="store_true",
        help="Inject the Codex AgentDriver for requests that explicitly select profile/development-bounded.",
    )

    goal_inspect = goal_commands.add_parser("inspect", help="Inspect durable GoalExecution, Plan, Node, evidence, and metrics.")
    goal_inspect.add_argument("goal_execution_id", help="GoalExecution id such as GEXEC-...")
    goal_inspect.add_argument("--db", required=True, help="SQLite control store path.")
    goal_inspect.add_argument("--artifact-dir", help="Optional artifact directory for relative artifact checks.")

    goal_resume = goal_commands.add_parser("resume", help="Resume a durable GoalExecution using its request profile.")
    goal_resume.add_argument("goal_execution_id", help="GoalExecution id such as GEXEC-...")
    goal_resume.add_argument("--request", required=True, help="Original immutable GoalExecutionRequest YAML path.")

    goal_cancel = goal_commands.add_parser("cancel", help="Cancel a non-terminal durable GoalExecution.")
    goal_cancel.add_argument("goal_execution_id", help="GoalExecution id such as GEXEC-...")
    goal_cancel.add_argument("--db", required=True, help="SQLite control store path.")
    goal_cancel.add_argument("--reason", default="cancellation requested", help="Cancellation reason recorded in state.")

    goal_bridge = goal_commands.add_parser("bridge-awkp-task", help="Bridge a succeeded GoalExecution into AWKP task review.")
    goal_bridge.add_argument("goal_execution_id", help="GoalExecution id such as GEXEC-...")
    goal_bridge.add_argument("--task", required=True, help="AWKP task id or task directory.")
    goal_bridge.add_argument("--work-root", default="work", help="AWKP work root containing tasks/.")
    goal_bridge.add_argument("--db", required=True, help="SQLite control store path.")
    goal_bridge.add_argument("--artifact-dir", required=True, help="Goal artifact directory with kernel verification records.")
    goal_bridge.add_argument("--expected-task-version", required=True, type=int, help="Expected AWKP task state_version.")
    goal_bridge.add_argument("--producer-actor", required=True, help="Current AWKP task lease holder.")
    goal_bridge.add_argument("--verifier-actor", required=True, help="Independent EvidenceGate verifier actor.")
    goal_bridge.add_argument("--fencing-token", required=True, help="Current producer lease fencing token.")
    goal_bridge.add_argument("--report", action="append", required=True, help="Verifier report JSON path. Repeat for retry cycles.")
    goal_bridge.add_argument("--max-cycles", type=int, default=1, help="Maximum EvidenceGate cycles before adding a blocker.")
    goal_bridge.add_argument("--idempotency-key-prefix", help="Prefix for bridge and review events.")
    goal_bridge.add_argument("--lease-ttl-seconds", type=int, help="Optional reclaim lease TTL.")
    goal_bridge.add_argument(
        "--reason",
        default="Completed GoalExecution evidence is ready for AWKP EvidenceGate review.",
        help="Reason recorded on review_requested events.",
    )

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
