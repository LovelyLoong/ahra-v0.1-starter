from __future__ import annotations

from collections import Counter
from dataclasses import replace

from .models import GoalReviewResult, GoalSpec, ReviewResult, ReviewVerdict, TaskSpec


def enforce_task_review_contract(task: TaskSpec, review: ReviewResult) -> ReviewResult:
    if review.verdict != ReviewVerdict.PASS:
        return review

    expected = set(task.acceptance_criteria)
    assessed = [item.criterion for item in review.criteria]
    counts = Counter(assessed)
    passed = {item.criterion for item in review.criteria if item.passed}

    violations: list[str] = []
    missing = sorted(expected - set(assessed))
    unknown = sorted(set(assessed) - expected)
    duplicates = sorted(item for item, count in counts.items() if count > 1)
    failed = sorted(expected - passed)

    if missing:
        violations.append(f"Reviewer omitted acceptance criteria: {missing}")
    if unknown:
        violations.append(f"Reviewer assessed unknown criteria: {unknown}")
    if duplicates:
        violations.append(f"Reviewer duplicated criteria: {duplicates}")
    if failed:
        violations.append(f"Reviewer PASS contains unpassed criteria: {failed}")
    if review.blocking_issues:
        violations.append("Reviewer returned PASS with blocking issues")

    if not violations:
        return review

    return replace(
        review,
        verdict=ReviewVerdict.FAIL,
        summary=(
            "Reviewer output failed the deterministic review contract. "
            f"Original summary: {review.summary}"
        ),
        blocking_issues=tuple(sorted(set((*review.blocking_issues, *violations)))),
    )


def enforce_goal_review_contract(goal: GoalSpec, review: GoalReviewResult) -> GoalReviewResult:
    if review.verdict != ReviewVerdict.PASS:
        return review

    expected = set(goal.success_criteria)
    satisfied = set(review.satisfied_criteria)
    unsatisfied = set(review.unsatisfied_criteria)

    violations: list[str] = []
    missing = sorted(expected - satisfied)
    unknown = sorted((satisfied | unsatisfied) - expected)
    contradictory = sorted(satisfied & unsatisfied)

    if missing:
        violations.append(f"Goal reviewer omitted success criteria: {missing}")
    if unknown:
        violations.append(f"Goal reviewer referenced unknown criteria: {unknown}")
    if contradictory:
        violations.append(f"Goal reviewer contradicted itself on: {contradictory}")
    if unsatisfied:
        violations.append(
            f"Goal reviewer returned PASS with unsatisfied criteria: {sorted(unsatisfied)}"
        )
    if review.blocking_issues:
        violations.append("Goal reviewer returned PASS with blocking issues")

    if not violations:
        return review

    return replace(
        review,
        verdict=ReviewVerdict.FAIL,
        summary=(
            "Goal reviewer output failed the deterministic review contract. "
            f"Original summary: {review.summary}"
        ),
        blocking_issues=tuple(sorted(set((*review.blocking_issues, *violations)))),
    )
