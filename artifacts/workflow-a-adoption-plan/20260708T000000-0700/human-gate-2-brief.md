# Human Gate 2 Brief: AHRA Adoption Model

Status: waiting for human authorization  
RequestDraft: `REQ-1d7c7ad449e4232f`  
Approval: `APR-1d7c7ad449e4232f`  
Plan digest: `sha256:422ed232033ee4176130a54d7de629437dcd50d741e7195639de02ad5eaaadd8`

This brief summarizes the machine-facing `request-draft.json` and `approval.json`.
It is not an approval record and does not authorize execution by itself.

## What You Are Being Asked To Authorize

Authorize a bounded planning/documentation increment that turns the approved
Gate 1 boundary into a concrete AHRA adoption architecture and rollout plan.

The authorized work is planning and documentation only. It is not the
implementation of `ahra project init`, `ahra project adopt`, `ahra project
doctor`, templates, or tests.

## Files This Request May Write

- `docs/architecture/ahra-adoption-model.md`
- `docs/policies/project-adoption-policy.md`
- `.ahra/project-template.yaml`

## Files This Request Does Not Authorize

- `src/ahra/cli.py`
- `tests/test_project_init.py`
- AHRA workflow runtime source
- legacy workflow modules
- fixtures
- archive history
- target project business code

## Boundary The Plan Must Preserve

- AHRA runtime, workflows, validators, and generic CLI behavior stay in the
  installable AHRA package and CLI.
- Target projects receive only the approved minimal governance overlay.
- `init` and `adopt` remain separate commands.
- `adopt` is non-destructive and reports conflicts instead of overwriting.
- `.ahra/policy.yaml` is the machine-executed project policy authority.
- `docs/policies/*.md` is human-readable explanation only.
- scaffold templates are packaged inside the AHRA package for now.
- scaffold templates are overlay skeleton files only, not workflow runtime.
- `doctor` checks AHRA overlay health only by default.
- The plan must not promote experimental Workflow A to a default route.
- The plan must not claim AHRA is already a production-grade distributed
  orchestrator for arbitrary projects.

## Planned Work Nodes

1. `NODE-adoption-architecture-plan`
   - Draft the architecture split between AHRA package/CLI responsibilities
     and target-project overlay responsibilities.
   - Writes `docs/architecture/ahra-adoption-model.md`.

2. `NODE-policy-and-overlay-boundary`
   - Define the policy authority split and project overlay boundary.
   - Writes `.ahra/project-template.yaml` and
     `docs/policies/project-adoption-policy.md`.

3. `NODE-init-adopt-doctor-contract`
   - Specify exact behavior for `project init`, `project adopt`, and
     `project doctor`.
   - Writes `.ahra/project-template.yaml` and
     `docs/architecture/ahra-adoption-model.md`.

4. `NODE-adoption-rollout-plan`
   - Draft rollout milestones and a later implementation authorization
     checklist.
   - Writes `docs/architecture/ahra-adoption-model.md`.

5. `NODE-terminal-alignment-verification`
   - Verify the plan satisfies the frozen boundary and identifies future Human
     Gate 2 needs before implementation.
   - No file writes.

## Gates And Verification

The RequestDraft has already passed `RequestDraftAdmission`.

Registered node types:

- `bounded_task`
- `goal_verification`

Registered gate refs:

- `GATE-alignment-objective`
- `GATE-alignment-complete`

Allowed capability:

- `filesystem.write`

## Risk Notes

- Risk level is R2/R3 because this sets product and governance direction.
- The request writes planning docs and a template config, not executable
  implementation code.
- The current Workflow A Gate 2 experience has a human-usability defect:
  raw `request-draft.json` and `approval.json` are machine-facing and too hard
  for human authorization review. Future Workflow A should produce this kind of
  human-readable briefing automatically before asking for Gate 2 approval.

## Human Decision

Approve Gate 2 only if the scope above is acceptable.

If approved, the next command is:

```powershell
uv run python -B -m ahra.cli workflow-a authorize `
  --request-draft artifacts/workflow-a-adoption-plan/20260708T000000-0700/request-draft.json `
  --approval artifacts/workflow-a-adoption-plan/20260708T000000-0700/approval.json `
  --output artifacts/workflow-a-adoption-plan/20260708T000000-0700/goal-execution-request.yaml `
  --actor human:maintainer `
  --reason "Human Gate 2 approved after reviewing the human-readable Gate 2 brief."
```

If not approved, revise the Gate 2 scope before authorization.
