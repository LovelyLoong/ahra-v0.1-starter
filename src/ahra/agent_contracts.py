from __future__ import annotations

import json
from typing import Any

from jsonschema import Draft202012Validator

from .ports import AgentOutputContract, AgentOutputContractError


def validate_agent_output(
    contract: AgentOutputContract,
    data: dict[str, Any],
    *,
    raw_output: Any | None = None,
) -> None:
    """Validate provider output before adapter-specific object conversion."""

    validator = Draft202012Validator(contract.schema)
    errors = sorted(validator.iter_errors(data), key=_schema_error_sort_key)
    if not errors:
        return
    details = tuple(_schema_error_detail(error) for error in errors)
    raise AgentOutputContractError(
        contract.name,
        details[0],
        raw_output=raw_output,
        details=details,
    )


def output_contract_prompt(contract: AgentOutputContract) -> str:
    """Render a stable output contract block for text-oriented AgentDrivers."""

    lines = [
        f"Output contract name: {contract.name}",
        "The final response must be exactly one JSON object validating this JSON Schema.",
        json.dumps(contract.schema, ensure_ascii=False, indent=2),
    ]
    if contract.example is not None:
        lines.extend(
            [
                "Example shape:",
                json.dumps(contract.example, ensure_ascii=False, indent=2),
            ]
        )
    if contract.instructions:
        lines.append("Additional contract rules:")
        lines.extend(f"- {item}" for item in contract.instructions)
    return "\n".join(lines)


def _schema_error_detail(error: Any) -> str:
    path = "/".join(str(item) for item in error.path) or "<root>"
    return f"{path}: {error.message}"


def _schema_error_sort_key(error: Any) -> tuple[int, list[Any]]:
    priority = {
        "required": 0,
        "type": 1,
        "enum": 1,
        "const": 1,
        "additionalProperties": 2,
    }.get(error.validator, 10)
    return (priority, list(error.path))
