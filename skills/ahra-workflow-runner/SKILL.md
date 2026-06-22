# AHRA Workflow Runner

Use this skill when the user asks to start, run, resume, or validate an AHRA
workflow module such as `standard-harness` or `loop-engineering`.

## Read First

1. `architecture/decisions/ADR-0005-agent-neutral-workflow-invocation.md`
2. `architecture/decisions/ADR-0006-reference-runtime-adapters-mcp-and-resume.md`
3. `docs/architecture/agent-drivers-and-workflow-invocation.md`
4. `docs/architecture/reference-runtime-adapters-and-mcp.md`
5. `docs/architecture/workflow-modules.md`
6. The referenced `WorkflowRunRequest` or `WorkflowResumeRequest`
7. The referenced task or goal input

## Rules

- Do not implement workflow logic inside the chat session.
- Do not assume Codex, Claude Code, OpenAI Agents SDK, or any provider has
  special status.
- Resolve `driverRef` through the driver registry.
- Validate the `WorkflowRunRequest` before running it.
- Use the runner API to start the module.
- Use `WorkflowResumeRequest` to continue a paused manual plan.
- Bind approval to the exact plan artifact SHA-256 before resuming.
- Record run id, status, artifact directory, and evidence refs.
- Do not declare an AWKP Task completed. Completion is decided by the evidence
  gate and independent verifier.
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
  driverRef: codex
  storeRef: local-file
  artifactDir: .runtime/ahra-runs/TASK-1234
  approvalMode: manual
```

## Procedure

1. Locate the request file or create one only if the user explicitly asks.
2. Validate it against `contracts/schemas/workflow-run-request.schema.json`.
3. Load the workflow module registry.
4. Resolve `driverRef` through `AgentDriverRegistry`.
5. Call the stable runner API.
6. Inspect generated artifact and evidence manifests.
7. Report factual status and blockers.

## Resume Procedure

1. Confirm the paused run status is `awaiting_plan_approval`.
2. Locate the proposed plan artifact, usually `cycles/<n>/next-step.json`.
3. Compute and record the plan artifact SHA-256.
4. Validate `WorkflowResumeRequest` against
   `contracts/schemas/workflow-resume-request.schema.json`.
5. Resolve the same workflow module and `driverRef`.
6. Call the stable resume API.
7. Inspect the updated artifact and evidence manifests.

## MCP Tools

Agents may use the local AHRA MCP server instead of direct Python calls when
available. The MCP tools are thin wrappers around the same validation and
runner APIs:

- `ahra.list_workflow_modules`
- `ahra.validate_workflow_run_request`
- `ahra.start_workflow`
- `ahra.get_workflow_run`
- `ahra.resume_workflow`

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
