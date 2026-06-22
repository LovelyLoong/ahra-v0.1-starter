from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from enum import StrEnum
from typing import Any

from ahra.domain import RunStatus


class WorkflowOutcome(StrEnum):
    ACCEPTED = "accepted"
    NEEDS_HUMAN = "needs_human"
    REJECTED = "rejected"
    ERROR = "error"
    COMPLETE = "complete"
    BLOCKED = "blocked"
    AWAITING_PLAN_APPROVAL = "awaiting_plan_approval"

    def to_ahra_run_status(self) -> RunStatus:
        return {
            self.ACCEPTED: RunStatus.SUCCEEDED,
            self.COMPLETE: RunStatus.SUCCEEDED,
            self.NEEDS_HUMAN: RunStatus.PAUSED_INPUT,
            self.AWAITING_PLAN_APPROVAL: RunStatus.PAUSED_INPUT,
            self.REJECTED: RunStatus.FAILED,
            self.ERROR: RunStatus.FAILED,
            self.BLOCKED: RunStatus.FAILED,
        }[self]


class ReviewVerdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    NEEDS_HUMAN = "needs_human"


class PlanAction(StrEnum):
    ADD_TASKS = "add_tasks"
    ESCALATE = "escalate"


@dataclass(frozen=True, slots=True)
class CheckSpec:
    name: str
    argv: tuple[str, ...]
    cwd: str = "."
    timeout_seconds: int = 300
    required: bool = True
    env: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("check name is required")
        if not self.argv:
            raise ValueError("check argv is required")
        if self.timeout_seconds < 1:
            raise ValueError("check timeout_seconds must be positive")


@dataclass(frozen=True, slots=True)
class ChangePolicy:
    allowed_globs: tuple[str, ...] = ("**",)
    protected_globs: tuple[str, ...] = (
        ".git/**",
        ".github/workflows/**",
        "**/*.pem",
        "**/*.key",
        "**/.env*",
    )
    sensitive_globs: tuple[str, ...] = (
        "**/migrations/**",
        "**/auth/**",
        "**/security/**",
        "**/Dockerfile",
        "**/*lock*",
    )
    max_changed_files: int = 30
    max_added_lines: int = 1200
    max_deleted_lines: int = 800
    allow_no_changes: bool = False


@dataclass(frozen=True, slots=True)
class TaskSpec:
    id: str
    title: str
    objective: str
    acceptance_criteria: tuple[str, ...]
    scope: tuple[str, ...] = ()
    requirements: tuple[str, ...] = ()
    non_goals: tuple[str, ...] = ()
    checks: tuple[CheckSpec, ...] = ()
    policy: ChangePolicy = field(default_factory=ChangePolicy)
    max_attempts: int = 2
    max_turns: int = 25

    def __post_init__(self) -> None:
        if not self.id or not self.title or not self.objective:
            raise ValueError("task id, title, and objective are required")
        if not self.acceptance_criteria:
            raise ValueError("task acceptance_criteria are required")
        if len(set(self.acceptance_criteria)) != len(self.acceptance_criteria):
            raise ValueError("task acceptance_criteria must be unique")
        if not 1 <= self.max_attempts <= 5:
            raise ValueError("task max_attempts must be between 1 and 5")
        if not 1 <= self.max_turns <= 100:
            raise ValueError("task max_turns must be between 1 and 100")


@dataclass(frozen=True, slots=True)
class GoalSpec:
    id: str
    title: str
    objective: str
    success_criteria: tuple[str, ...]
    boundaries: tuple[str, ...] = ()
    policy: ChangePolicy = field(default_factory=ChangePolicy)
    tasks: tuple[TaskSpec, ...] = ()
    global_checks: tuple[CheckSpec, ...] = ()
    max_cycles: int = 3
    max_total_tasks: int = 12
    dynamic_planning: bool = False
    auto_execute_proposed_tasks: bool = False

    def __post_init__(self) -> None:
        if not self.id or not self.title or not self.objective:
            raise ValueError("goal id, title, and objective are required")
        if not self.success_criteria:
            raise ValueError("goal success_criteria are required")
        if len(set(self.success_criteria)) != len(self.success_criteria):
            raise ValueError("goal success_criteria must be unique")
        task_ids = [task.id for task in self.tasks]
        if len(set(task_ids)) != len(task_ids):
            raise ValueError("goal task ids must be unique")
        if not self.tasks and not self.dynamic_planning:
            raise ValueError("goal needs tasks unless dynamic_planning is enabled")


@dataclass(frozen=True, slots=True)
class WorkReport:
    summary: str
    changed_files: tuple[str, ...] = ()
    verification_commands_run: tuple[str, ...] = ()
    known_risks: tuple[str, ...] = ()
    unresolved_items: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CheckEvidence:
    name: str
    argv: tuple[str, ...]
    required: bool
    exit_code: int | None = None
    timed_out: bool = False
    duration_seconds: float = 0.0
    stdout: str = ""
    stderr: str = ""

    @property
    def passed(self) -> bool:
        return not self.timed_out and self.exit_code == 0


@dataclass(frozen=True, slots=True)
class PolicyEvidence:
    changed_files: tuple[str, ...] = ()
    sensitive_files: tuple[str, ...] = ()
    violations: tuple[str, ...] = ()
    added_lines: int = 0
    deleted_lines: int = 0

    @property
    def passed(self) -> bool:
        return not self.violations


@dataclass(frozen=True, slots=True)
class DeterministicEvidence:
    policy: PolicyEvidence
    checks: tuple[CheckEvidence, ...] = ()
    verification_mutated_workspace: bool = False
    verification_mutation_files: tuple[str, ...] = ()
    patch_excerpt: str = ""

    @property
    def required_checks_passed(self) -> bool:
        return all(check.passed for check in self.checks if check.required)

    @property
    def passed(self) -> bool:
        return (
            self.policy.passed
            and self.required_checks_passed
            and not self.verification_mutated_workspace
        )


@dataclass(frozen=True, slots=True)
class CriterionAssessment:
    criterion: str
    passed: bool
    evidence: str
    concerns: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReviewResult:
    verdict: ReviewVerdict
    summary: str
    criteria: tuple[CriterionAssessment, ...] = ()
    blocking_issues: tuple[str, ...] = ()
    non_blocking_issues: tuple[str, ...] = ()
    confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class GoalReviewResult:
    verdict: ReviewVerdict
    summary: str
    satisfied_criteria: tuple[str, ...] = ()
    unsatisfied_criteria: tuple[str, ...] = ()
    blocking_issues: tuple[str, ...] = ()
    confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class TaskAttemptRecord:
    attempt: int
    work_report: WorkReport | None = None
    deterministic: DeterministicEvidence | None = None
    review: ReviewResult | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class TaskRunResult:
    run_id: str
    task_id: str
    status: WorkflowOutcome
    checkpoint: str
    workspace: str
    branch: str
    artifact_dir: str
    commit: str | None = None
    attempts: tuple[TaskAttemptRecord, ...] = ()
    message: str = ""


@dataclass(frozen=True, slots=True)
class NextStepDecision:
    action: PlanAction
    rationale: str
    proposed_tasks: tuple[TaskSpec, ...] = ()
    human_questions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.action == PlanAction.ADD_TASKS and not self.proposed_tasks:
            raise ValueError("ADD_TASKS requires proposed_tasks")
        if self.action != PlanAction.ADD_TASKS and self.proposed_tasks:
            raise ValueError("only ADD_TASKS may include proposed_tasks")
        if len(self.proposed_tasks) > 3:
            raise ValueError("proposed_tasks is limited to 3")


@dataclass(frozen=True, slots=True)
class GoalRunResult:
    run_id: str
    goal_id: str
    status: WorkflowOutcome
    branch: str
    workspace: str
    artifact_dir: str
    completed_tasks: tuple[TaskRunResult, ...] = ()
    global_evidence: DeterministicEvidence | None = None
    goal_review: GoalReviewResult | None = None
    next_step: NextStepDecision | None = None
    final_commit: str | None = None
    message: str = ""


def to_jsonable(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if is_dataclass(value):
        return {key: to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, tuple):
        return [to_jsonable(item) for item in value]
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    return value
