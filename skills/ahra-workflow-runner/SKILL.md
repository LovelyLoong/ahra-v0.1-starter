# AHRA Workflow Runner

Use this skill when the user asks to start, run, resume, or validate an AHRA
workflow module such as `standard-harness` or `loop-engineering`.

## Read First

1. `architecture/decisions/ADR-0005-agent-neutral-workflow-invocation.md`
2. `architecture/decisions/ADR-0006-reference-runtime-adapters-mcp-and-resume.md`
3. `docs/architecture/agent-drivers-and-workflow-invocation.md`
4. `docs/architecture/reference-runtime-adapters-and-mcp.md`
5. `docs/architecture/framework-entrypoints.md`
6. `docs/architecture/workflow-modules.md`
7. The referenced `WorkflowRunRequest` or `WorkflowResumeRequest`
8. The referenced task or goal input

## Rules

- Do not implement workflow logic inside the chat session.
- Do not assume Codex, Claude Code, OpenAI Agents SDK, or any provider has
  special status.
- Resolve `driverRef` through the driver registry.
- Validate the `WorkflowRunRequest` before running it.
- Use the `ahra` CLI to start and inspect workflow runs.
- Use `WorkflowResumeRequest` to continue a paused manual plan.
- Bind approval to the exact plan artifact SHA-256 before resuming.
- Record run id, status, artifact directory, and evidence refs.
- Do not declare an AWKP Task completed. Completion is decided by the evidence
  gate and independent verifier.
- When a request targets an existing AWKP task under `workspaceRef`, treat it
  as a formal run: the task must be `ready`, dependencies must be completed,
  no active lease may exist, and an accepted run should update the source
  workspace task to `review` with workflow evidence and a handoff.
- If the request is ambiguous, ask for the missing request file, module id,
  workspace ref, or driver ref.

## Expected Request Shape

```yaml
apiVersion: ahra.dev/v1alpha1
kind: WorkflowRunRequest
metadata:
  name: example-standard-task
spec:
  moduleId: standard-harness
  input:
    taskRef: work/tasks/TASK-1234/task.yaml
  workspaceRef: .
  driverRef: codex-python-sdk
  storeRef: local-file
  artifactDir: .runtime/ahra-runs/TASK-1234
  approvalMode: manual
```

## Procedure

1. Locate the request file or create one only if the user explicitly asks.
2. Validate it against `contracts/schemas/workflow-run-request.schema.json`.
3. Load the workflow module registry.
4. Resolve `driverRef` through `AgentDriverRegistry`.
5. Call `uv run ahra workflow start <request>`.
6. Inspect generated artifact and evidence manifests.
7. For formal AWKP task runs, inspect the source task state and confirm it is
   `review`, not `completed`, before reporting status.
8. Report factual status and blockers.

## Resume Procedure

1. Confirm the paused run status is `awaiting_plan_approval`.
2. Locate the proposed plan artifact, usually `cycles/<n>/next-step.json`.
3. Compute and record the plan artifact SHA-256.
4. Validate `WorkflowResumeRequest` against
   `contracts/schemas/workflow-resume-request.schema.json`.
5. Resolve the same workflow module and `driverRef`.
6. Call `uv run ahra workflow resume <request>`.
7. Inspect the updated artifact and evidence manifests.

## Default Commands

Use these local commands for verification and health checks:

- `uv run ahra workflow validate <request.yaml>`
- `uv run ahra workflow start <request.yaml>`
- `uv run ahra workflow inspect <artifact-dir>`
- `uv run ahra workflow resume <resume-request.yaml>`
- `uv run ahra task inspect <TASK-ID>`
- `uv run ahra evidence-gate evaluate <TASK-ID> --expected-version <N> --report <report.json> --actor <verifier>`
- `uv run ahra doctor`
- `uv run python -B scripts/check.py`
- `uv run python -B scripts/check.py --lint`
- `uv run python -B scripts/check.py --test`
- `uv run python -B scripts/lint_awkp.py`
- `uv run python -B -m ahra.demo`
- `git diff --check`

`fake-reference` is only available for fixture smoke tests when the CLI is
called with `--enable-fixture-driver`. Do not use it as a runnable default
driver.

Use `codex-python-sdk` as the maintainer workstation's default non-fixture
local driver. If the optional SDK package or local Codex account setup is
missing, report the structured failure and ask the user to install or
authenticate the SDK before rerunning the workflow.

Do not use a separate command-line fallback driver. The starter does not
provide one.

Do not use the local AHRA MCP server for new workflow operation. MCP is a
legacy optional adapter surface and is not part of the current default starter
route.

## Approval Modes

- `manual`: planner proposals are saved and the run pauses for approval.
- `auto`: planner proposals may execute within the module's limits.
- `disabled`: planner proposals are not requested; unmet goals block.

## Failure Policy

Fail closed when:

- The module id is unknown.
- The driver ref is unknown.
- The request references both task and goal inputs incorrectly.
- A resume request approves a plan SHA-256 that does not match the stored
  plan artifact.
- The workspace ref cannot be resolved.
- The runner produces no artifact or evidence manifest.
- The workflow result claims completion without evidence.
