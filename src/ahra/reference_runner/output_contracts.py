from __future__ import annotations

from copy import deepcopy
from typing import Any

from ahra.ports import AgentOutputContract, AgentOutputContractError

from .models import (
    ChangePolicy,
    CheckSpec,
    CriterionAssessment,
    ExpectedOutputSpec,
    GoalReviewResult,
    NextStepDecision,
    PlanAction,
    ReviewResult,
    ReviewVerdict,
    TaskSpec,
    WorkReport,
)


def output_contract(expected_output: str) -> AgentOutputContract:
    try:
        contract = _CONTRACTS[expected_output]
    except KeyError as exc:
        raise ValueError(f"unsupported reference runner output contract: {expected_output}") from exc
    return AgentOutputContract(
        name=contract.name,
        schema=deepcopy(contract.schema),
        example=deepcopy(contract.example),
        instructions=contract.instructions,
    )


def parse_reference_output(expected_output: str, data: dict[str, Any]) -> Any:
    try:
        if expected_output in {"AcceptanceDraft", "PlanDraft", "PlanPatchDraft"}:
            return data
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
        raise AgentOutputContractError(expected_output, str(exc), details=(str(exc),)) from exc
    raise ValueError(f"unsupported reference runner expected output: {expected_output}")


_STRING_LIST = {
    "type": "array",
    "items": {"type": "string"},
}


_CHECK_SPEC = {
    "type": "object",
    "additionalProperties": False,
    "required": ["name", "argv"],
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "argv": {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}},
        "cwd": {"type": "string", "minLength": 1},
        "timeout_seconds": {"type": "integer", "minimum": 1},
        "required": {"type": "boolean"},
        "env": {"type": "object", "additionalProperties": {"type": "string"}},
    },
}


_CHANGE_POLICY = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "allowed_globs": {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}},
        "protected_globs": _STRING_LIST,
        "sensitive_globs": _STRING_LIST,
        "max_changed_files": {"type": "integer", "minimum": 1},
        "max_added_lines": {"type": "integer", "minimum": 0},
        "max_deleted_lines": {"type": "integer", "minimum": 0},
        "allow_no_changes": {"type": "boolean"},
    },
}


_TASK_SPEC = {
    "type": "object",
    "additionalProperties": False,
    "required": ["id", "title", "objective", "acceptance_criteria"],
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "title": {"type": "string", "minLength": 1},
        "objective": {"type": "string", "minLength": 1},
        "acceptance_criteria": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "minLength": 1},
        },
        "scope": _STRING_LIST,
        "requirements": _STRING_LIST,
        "non_goals": _STRING_LIST,
        "expected_outputs": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name"],
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "schema_ref": {"type": "string"},
                    "delivery_role": {"type": ["string", "null"]},
                    "artifact_required": {"type": "boolean"},
                },
            },
        },
        "checks": {"type": "array", "items": _CHECK_SPEC},
        "policy": _CHANGE_POLICY,
        "max_attempts": {"type": "integer", "minimum": 1, "maximum": 5},
        "max_turns": {"type": "integer", "minimum": 1, "maximum": 100},
    },
}


_CRITERION_ASSESSMENT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["criterion", "passed", "evidence", "concerns"],
    "properties": {
        "criterion": {"type": "string", "minLength": 1},
        "passed": {"type": "boolean"},
        "evidence": {"type": "string", "minLength": 1},
        "concerns": _STRING_LIST,
    },
}


_CONTRACTS = {
    "WorkReport": AgentOutputContract(
        name="WorkReport",
        schema={
            "type": "object",
            "additionalProperties": False,
            "required": [
                "summary",
                "changed_files",
                "verification_commands_run",
                "known_risks",
                "unresolved_items",
            ],
            "properties": {
                "summary": {"type": "string", "minLength": 1},
                "changed_files": _STRING_LIST,
                "verification_commands_run": _STRING_LIST,
                "known_risks": _STRING_LIST,
                "unresolved_items": _STRING_LIST,
            },
        },
        example={
            "summary": "Updated the requested implementation and verified it.",
            "changed_files": ["src/example.py"],
            "verification_commands_run": ["python scripts/check.py"],
            "known_risks": [],
            "unresolved_items": [],
        },
    ),
    "ReviewResult": AgentOutputContract(
        name="ReviewResult",
        schema={
            "type": "object",
            "additionalProperties": False,
            "required": [
                "verdict",
                "summary",
                "criteria",
                "blocking_issues",
                "non_blocking_issues",
                "confidence",
            ],
            "properties": {
                "verdict": {"enum": ["pass", "fail", "needs_human"]},
                "summary": {"type": "string", "minLength": 1},
                "criteria": {"type": "array", "items": _CRITERION_ASSESSMENT},
                "blocking_issues": _STRING_LIST,
                "non_blocking_issues": _STRING_LIST,
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            },
        },
        example={
            "verdict": "pass",
            "summary": "All acceptance criteria have evidence.",
            "criteria": [
                {
                    "criterion": "The requested behavior is implemented.",
                    "passed": True,
                    "evidence": "Patch and deterministic checks support this criterion.",
                    "concerns": [],
                }
            ],
            "blocking_issues": [],
            "non_blocking_issues": [],
            "confidence": 0.9,
        },
        instructions=(
            "Return fail when any acceptance criterion lacks explicit evidence.",
            "Do not use status, findings, acceptance_criteria, or policy_review as top-level fields.",
        ),
    ),
    "GoalReviewResult": AgentOutputContract(
        name="GoalReviewResult",
        schema={
            "type": "object",
            "additionalProperties": False,
            "required": [
                "verdict",
                "summary",
                "satisfied_criteria",
                "unsatisfied_criteria",
                "blocking_issues",
                "confidence",
            ],
            "properties": {
                "verdict": {"enum": ["pass", "fail", "needs_human"]},
                "summary": {"type": "string", "minLength": 1},
                "satisfied_criteria": _STRING_LIST,
                "unsatisfied_criteria": _STRING_LIST,
                "blocking_issues": _STRING_LIST,
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            },
        },
        example={
            "verdict": "fail",
            "summary": "One goal criterion is not yet satisfied.",
            "satisfied_criteria": [],
            "unsatisfied_criteria": ["Global verification passes."],
            "blocking_issues": ["Global check did not pass."],
            "confidence": 0.85,
        },
    ),
    "NextStepDecision": AgentOutputContract(
        name="NextStepDecision",
        schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["action", "rationale", "proposed_tasks", "human_questions"],
            "properties": {
                "action": {"enum": ["add_tasks", "escalate"]},
                "rationale": {"type": "string", "minLength": 1},
                "proposed_tasks": {"type": "array", "maxItems": 3, "items": _TASK_SPEC},
                "human_questions": _STRING_LIST,
            },
            "allOf": [
                {
                    "if": {"properties": {"action": {"const": "add_tasks"}}, "required": ["action"]},
                    "then": {"properties": {"proposed_tasks": {"minItems": 1}}},
                },
                {
                    "if": {"properties": {"action": {"const": "escalate"}}, "required": ["action"]},
                    "then": {"properties": {"proposed_tasks": {"maxItems": 0}}},
                },
            ],
        },
        example={
            "action": "escalate",
            "rationale": "The remaining decision needs human input.",
            "proposed_tasks": [],
            "human_questions": ["Which implementation boundary should be selected?"],
        },
    ),
}


def _criterion(data: dict[str, Any]) -> CriterionAssessment:
    return CriterionAssessment(
        criterion=str(data["criterion"]),
        passed=bool(data["passed"]),
        evidence=str(data["evidence"]),
        concerns=_str_tuple(data["concerns"]),
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
        expected_outputs=tuple(_expected_output(item) for item in data.get("expected_outputs", ())),
        checks=tuple(_check(item) for item in data.get("checks", ())),
        policy=_policy(data.get("policy", {})),
        max_attempts=int(data.get("max_attempts", 2)),
        max_turns=int(data.get("max_turns", 25)),
    )


def _expected_output(data: dict[str, Any]) -> ExpectedOutputSpec:
    return ExpectedOutputSpec(
        name=str(data["name"]),
        schema_ref=str(data.get("schema_ref") or ""),
        delivery_role=str(data["delivery_role"]) if data.get("delivery_role") else None,
        artifact_required=bool(data.get("artifact_required", True)),
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
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)
