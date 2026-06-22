from __future__ import annotations

import fnmatch
from dataclasses import dataclass

from .models import ChangePolicy, PolicyEvidence


@dataclass(frozen=True, slots=True)
class ChangeSummary:
    files: tuple[str, ...]
    added_lines: int
    deleted_lines: int


def _normalize(path: str) -> str:
    return path.replace("\\", "/").strip("/")


def _matches(path: str, pattern: str) -> bool:
    normalized = _normalize(path)
    normalized_pattern = _normalize(pattern)
    if normalized_pattern == "**":
        return True
    if normalized_pattern.endswith("/**"):
        prefix = normalized_pattern[:-3]
        if normalized == prefix or normalized.startswith(prefix + "/"):
            return True
    return fnmatch.fnmatchcase(normalized, normalized_pattern)


def _any_match(path: str, patterns: tuple[str, ...]) -> bool:
    return any(_matches(path, pattern) for pattern in patterns)


def evaluate_policy(
    change: ChangeSummary,
    task_policy: ChangePolicy,
    parent_policy: ChangePolicy | None = None,
) -> PolicyEvidence:
    policies = (task_policy,) if parent_policy is None else (task_policy, parent_policy)
    violations: set[str] = set()
    sensitive: set[str] = set()

    for index, policy in enumerate(policies):
        label = "task" if index == 0 else "goal"
        for changed_file in change.files:
            if not _any_match(changed_file, policy.allowed_globs):
                violations.add(f"{label} policy does not allow path: {changed_file}")
            if _any_match(changed_file, policy.protected_globs):
                violations.add(f"{label} policy protects path: {changed_file}")
            if _any_match(changed_file, policy.sensitive_globs):
                sensitive.add(changed_file)

        if len(change.files) > policy.max_changed_files:
            violations.add(
                f"{label} policy changed-file limit exceeded: "
                f"{len(change.files)} > {policy.max_changed_files}"
            )
        if change.added_lines > policy.max_added_lines:
            violations.add(
                f"{label} policy added-line limit exceeded: "
                f"{change.added_lines} > {policy.max_added_lines}"
            )
        if change.deleted_lines > policy.max_deleted_lines:
            violations.add(
                f"{label} policy deleted-line limit exceeded: "
                f"{change.deleted_lines} > {policy.max_deleted_lines}"
            )
        if not change.files and not policy.allow_no_changes:
            violations.add(f"{label} policy requires at least one changed file")

    return PolicyEvidence(
        changed_files=tuple(sorted(change.files)),
        sensitive_files=tuple(sorted(sensitive)),
        violations=tuple(sorted(violations)),
        added_lines=change.added_lines,
        deleted_lines=change.deleted_lines,
    )
