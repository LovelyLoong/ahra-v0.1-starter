from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from ahra.agent_contracts import output_contract_prompt, validate_agent_output
from ahra.ports import AgentDriver, AgentOutputContractError, AgentRole, AgentRunRequest, AgentRunResult
from ahra.reference_runner.models import to_jsonable
from ahra.reference_runner.output_contracts import parse_reference_output

PLANNER_STRUCTURED_OUTPUTS = {"AcceptanceDraft", "PlanDraft", "PlanPatchDraft"}


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
        sandbox = self._sandbox_for_request(request)
        raw = await self.client.run(
            request=request,
            prompt=_prompt_for_request(request),
            sandbox=sandbox,
            model=self.config.model,
            cwd=request.workspace_ref,
        )
        data = _load_json_object(raw, request.expected_output)
        if request.expected_output in PLANNER_STRUCTURED_OUTPUTS and request.output_contract is None:
            raise AgentOutputContractError(
                request.expected_output,
                "explicit output contract is required for planner structured outputs",
                raw_output=raw,
            )
        if request.output_contract is not None:
            validate_agent_output(request.output_contract, data, raw_output=raw)
        try:
            output = parse_reference_output(request.expected_output, data)
        except AgentOutputContractError as exc:
            raise AgentOutputContractError(
                request.expected_output,
                exc.message,
                raw_output=raw,
                details=exc.details,
            ) from exc
        return AgentRunResult(output=output, raw_output=raw)

    def _sandbox_for_request(self, request: AgentRunRequest) -> str:
        if request.runtime_profile is not None:
            return request.runtime_profile.sandbox
        role = request.role
        if role == AgentRole.EXECUTOR:
            return self.config.executor_sandbox
        if role in (AgentRole.TASK_REVIEWER, AgentRole.GOAL_REVIEWER):
            return self.config.reviewer_sandbox
        if role == AgentRole.PLANNER:
            return self.config.planner_sandbox
        raise ValueError(f"unsupported Codex driver role: {role}")


def _prompt_for_request(request: AgentRunRequest) -> str:
    payload = json.dumps(to_jsonable(request.payload), ensure_ascii=False, indent=2)
    contract = (
        output_contract_prompt(request.output_contract)
        if request.output_contract is not None
        else "No explicit output contract was supplied. Use the expected output type exactly."
    )
    runtime = ""
    if request.runtime_profile is not None:
        runtime = (
            f"Runtime profile ref: {request.runtime_profile.profile_ref}\n"
            f"Runtime sandbox: {request.runtime_profile.sandbox}\n"
            "Runtime capabilities: "
            f"{', '.join(request.runtime_profile.capabilities) or '<none>'}\n"
        )
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
    role_instruction = role_instructions[request.role]
    if request.role == AgentRole.PLANNER and request.expected_output == "PlanDraft":
        role_instruction += (
            " For PlanDraft output, use the exact AHRA PlanDraft field names: "
            "metadata.goalId, metadata.proposedBy, spec.nodes, nodes[].nodeType, "
            "nodes[].claimRefs, nodes[].dependsOn, nodes[].inputRefs, "
            "nodes[].expectedOutputs, nodes[].gateRefs, and nodes[].budgetRequest. "
            "Do not use aliases such as goalRef, type, claims, gates, bounds, "
            "limits, budget, objective-only nodes, or planNodes."
        )
    return (
        "You are an AHRA AgentDriver adapter.\n"
        f"Role: {request.role.value}\n"
        f"Run ID: {request.run_id}\n"
        f"Workspace ref: {request.workspace_ref or '<none>'}\n"
        f"Expected output type: {request.expected_output}\n"
        f"{runtime}"
        f"{role_instruction}\n"
        "Return only one JSON object. Do not include markdown or prose.\n"
        "Do not add fields outside the output contract.\n"
        "Output contract:\n"
        f"{contract}\n"
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


def _load_json_object(raw: str, expected_output: str) -> dict[str, Any]:
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
            raise AgentOutputContractError(
                expected_output,
                "Codex driver response did not contain a JSON object",
                raw_output=raw,
            )
        text = text[start : end + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AgentOutputContractError(
            expected_output,
            f"Codex driver response JSON could not be decoded: {exc.msg}",
            raw_output=raw,
            details=(exc.msg,),
        ) from exc
    if not isinstance(data, dict):
        raise AgentOutputContractError(
            expected_output,
            "Codex driver response JSON must be an object",
            raw_output=raw,
        )
    return data
