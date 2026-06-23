from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from ahra.ports import AgentDriver, AgentRole, AgentRunRequest, AgentRunResult
from ahra.reference_runner.models import (
    ChangePolicy,
    CheckSpec,
    CriterionAssessment,
    GoalReviewResult,
    NextStepDecision,
    PlanAction,
    ReviewResult,
    ReviewVerdict,
    TaskSpec,
    WorkReport,
    to_jsonable,
)


class CodexClient(Protocol):
    async def run(
        self,
        *,
        request: AgentRunRequest,
        prompt: str,
        sandbox: str,
        model: str | None,
        cwd: str | None,
    ) -> str: ...


@dataclass(frozen=True, slots=True)
class CodexDriverConfig:
    driver_ref: str = "codex-python-sdk"
    model: str | None = None
    executor_sandbox: str = "workspace_write"
    reviewer_sandbox: str = "read_only"
    planner_sandbox: str = "read_only"
    codex_bin: str | None = None


class CodexSDKClient:
    """Thin wrapper around the optional openai-codex Python SDK."""

    def __init__(self, config: CodexDriverConfig | None = None) -> None:
        self.config = config or CodexDriverConfig()

    async def run(
        self,
        *,
        request: AgentRunRequest,
        prompt: str,
        sandbox: str,
        model: str | None,
        cwd: str | None,
    ) -> str:
        try:
            from openai_codex import AsyncCodex, CodexConfig, Sandbox
        except ImportError as exc:
            raise RuntimeError(
                "CodexSDKDriver requires the optional 'codex' extra: "
                "pip install -e .[codex]"
            ) from exc

        kwargs: dict[str, Any] = {}
        if self.config.codex_bin or cwd:
            kwargs["config"] = CodexConfig(codex_bin=self.config.codex_bin, cwd=cwd)
        async with AsyncCodex(**kwargs) as codex:
            thread_kwargs = {"sandbox": _sdk_sandbox(Sandbox, sandbox)}
            if model is not None:
                thread_kwargs["model"] = model
            if cwd is not None:
                thread_kwargs["cwd"] = cwd
            thread = await codex.thread_start(**thread_kwargs)
            result = await thread.run(prompt)
        return str(getattr(result, "final_response", result))


class CodexSDKDriver(AgentDriver):
    """AgentDriver adapter for Codex Python SDK.

    The adapter is intentionally reference-runner oriented: it asks Codex for
    JSON matching the expected role output and converts that JSON into the
    local structured result objects.
    """

    def __init__(
        self,
        config: CodexDriverConfig | None = None,
        *,
        client: CodexClient | None = None,
    ) -> None:
        self.config = config or CodexDriverConfig()
        self.client = client or CodexSDKClient(self.config)

    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        sandbox = self._sandbox_for_role(request.role)
        raw = await self.client.run(
            request=request,
            prompt=_prompt_for_request(request),
            sandbox=sandbox,
            model=self.config.model,
            cwd=request.workspace_ref,
        )
        data = _load_json_object(raw)
        output = _parse_expected_output(request.expected_output, data)
        return AgentRunResult(output=output, raw_output=raw)

    def _sandbox_for_role(self, role: AgentRole) -> str:
        if role == AgentRole.EXECUTOR:
            return self.config.executor_sandbox
        if role in (AgentRole.TASK_REVIEWER, AgentRole.GOAL_REVIEWER):
            return self.config.reviewer_sandbox
        if role == AgentRole.PLANNER:
            return self.config.planner_sandbox
        raise ValueError(f"unsupported Codex driver role: {role}")


def _prompt_for_request(request: AgentRunRequest) -> str:
    payload = json.dumps(to_jsonable(request.payload), ensure_ascii=False, indent=2)
    role_instructions = {
        AgentRole.EXECUTOR: (
            "Executor duty: modify only the provided workspace to satisfy the task. "
            "Respect the task scope, policy, protected files, and feedback. "
            "Do not claim success unless the workspace was actually updated or no "
            "change is required by the task."
        ),
        AgentRole.TASK_REVIEWER: (
            "Task reviewer duty: perform an independent read-only review of the "
            "task, work report, deterministic evidence, and patch. Do not modify "
            "files. Return fail if any acceptance criterion lacks evidence."
        ),
        AgentRole.GOAL_REVIEWER: (
            "Goal reviewer duty: perform an independent read-only review of the "
            "completed task results, global deterministic evidence, and patch. "
            "Do not modify files."
        ),
        AgentRole.PLANNER: (
            "Planner duty: propose only bounded follow-up tasks within the goal "
            "scope, or escalate with questions. Do not modify files."
        ),
    }
    return (
        "You are an AHRA AgentDriver adapter.\n"
        f"Role: {request.role.value}\n"
        f"Run ID: {request.run_id}\n"
        f"Workspace ref: {request.workspace_ref or '<none>'}\n"
        f"Expected output type: {request.expected_output}\n"
        f"{role_instructions[request.role]}\n"
        "Return only one JSON object. Do not include markdown or prose.\n"
        "Use snake_case field names matching the expected output type.\n"
        "Payload:\n"
        f"{payload}\n"
    )


def _sdk_sandbox(sandbox_type: Any, name: str) -> Any:
    normalized = name.replace("-", "_")
    if normalized == "danger_full_access":
        normalized = "full_access"
    try:
        return getattr(sandbox_type, normalized)
    except AttributeError as exc:
        raise ValueError(f"unsupported Codex sandbox: {name}") from exc


def _load_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("Codex driver response did not contain a JSON object")
        text = text[start : end + 1]
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Codex driver response JSON must be an object")
    return data


def _parse_expected_output(expected_output: str, data: dict[str, Any]) -> Any:
    try:
        if expected_output == "WorkReport":
            return WorkReport(
                summary=str(data["summary"]),
                changed_files=_str_tuple(data.get("changed_files", ())),
                verification_commands_run=_str_tuple(data.get("verification_commands_run", ())),
                known_risks=_str_tuple(data.get("known_risks", ())),
                unresolved_items=_str_tuple(data.get("unresolved_items", ())),
            )
        if expected_output == "ReviewResult":
            return ReviewResult(
                verdict=ReviewVerdict(str(data["verdict"])),
                summary=str(data["summary"]),
                criteria=tuple(_criterion(item) for item in data.get("criteria", ())),
                blocking_issues=_str_tuple(data.get("blocking_issues", ())),
                non_blocking_issues=_str_tuple(data.get("non_blocking_issues", ())),
                confidence=float(data.get("confidence", 0.0)),
            )
        if expected_output == "GoalReviewResult":
            return GoalReviewResult(
                verdict=ReviewVerdict(str(data["verdict"])),
                summary=str(data["summary"]),
                satisfied_criteria=_str_tuple(data.get("satisfied_criteria", ())),
                unsatisfied_criteria=_str_tuple(data.get("unsatisfied_criteria", ())),
                blocking_issues=_str_tuple(data.get("blocking_issues", ())),
                confidence=float(data.get("confidence", 0.0)),
            )
        if expected_output == "NextStepDecision":
            return NextStepDecision(
                action=PlanAction(str(data["action"])),
                rationale=str(data["rationale"]),
                proposed_tasks=tuple(_task(item) for item in data.get("proposed_tasks", ())),
                human_questions=_str_tuple(data.get("human_questions", ())),
            )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Codex driver response did not match {expected_output}") from exc
    raise ValueError(f"unsupported Codex driver expected output: {expected_output}")


def _criterion(data: dict[str, Any]) -> CriterionAssessment:
    return CriterionAssessment(
        criterion=str(data["criterion"]),
        passed=bool(data["passed"]),
        evidence=str(data["evidence"]),
        concerns=_str_tuple(data.get("concerns", ())),
    )


def _task(data: dict[str, Any]) -> TaskSpec:
    return TaskSpec(
        id=str(data["id"]),
        title=str(data["title"]),
        objective=str(data["objective"]),
        acceptance_criteria=_str_tuple(data["acceptance_criteria"]),
        scope=_str_tuple(data.get("scope", ())),
        requirements=_str_tuple(data.get("requirements", ())),
        non_goals=_str_tuple(data.get("non_goals", ())),
        checks=tuple(_check(item) for item in data.get("checks", ())),
        policy=_policy(data.get("policy", {})),
        max_attempts=int(data.get("max_attempts", 2)),
        max_turns=int(data.get("max_turns", 25)),
    )


def _check(data: dict[str, Any]) -> CheckSpec:
    return CheckSpec(
        name=str(data["name"]),
        argv=_str_tuple(data["argv"]),
        cwd=str(data.get("cwd", ".")),
        timeout_seconds=int(data.get("timeout_seconds", 300)),
        required=bool(data.get("required", True)),
        env={str(key): str(value) for key, value in data.get("env", {}).items()},
    )


def _policy(data: dict[str, Any]) -> ChangePolicy:
    default = ChangePolicy()
    return ChangePolicy(
        allowed_globs=_str_tuple(data.get("allowed_globs", default.allowed_globs)),
        protected_globs=_str_tuple(data.get("protected_globs", default.protected_globs)),
        sensitive_globs=_str_tuple(data.get("sensitive_globs", default.sensitive_globs)),
        max_changed_files=int(data.get("max_changed_files", default.max_changed_files)),
        max_added_lines=int(data.get("max_added_lines", default.max_added_lines)),
        max_deleted_lines=int(data.get("max_deleted_lines", default.max_deleted_lines)),
        allow_no_changes=bool(data.get("allow_no_changes", default.allow_no_changes)),
    )


def _str_tuple(value: Any) -> tuple[str, ...]:
    return tuple(str(item) for item in value)
