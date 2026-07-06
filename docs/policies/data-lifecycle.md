---
type: Policy
id: POLICY-data-lifecycle
schema_version: awkp/0.1
title: Task data lifecycle policy
description: Defines retention tiers for task contracts, authority state, evidence, and run byproducts.
status: active
owner: team:platform
source_refs:
  - ../../work/index.md
evidence_refs: []
confidence: reviewed
last_verified_at: 2026-07-03T00:00:00Z
review_after: 2026-10-03T00:00:00Z
tags: [policy, data, lifecycle, tasks]
---

# Summary

Task data is retained by authority tier. Permanent records stay small and reviewable. Ephemeral run byproducts are garbage-collected after success and retained on failure only while they are needed to diagnose and close the defect.

# Retention tiers

## Contract

`task.md` is the task contract. It is permanent and must remain available for acceptance, scope, and non-goal review.

## Authority

`state.json` and `events.jsonl` are authority records. They are permanent, but after completion they are archived with Git history as the audit authority. `state.json` preserves the final machine-readable state; `events.jsonl` preserves the append-only transition log.

## Evidence

Evidence is required until EvidenceGate approval. After approval, evidence is archived with the task so the completed decision remains traceable without keeping transient execution surfaces alive.

## Run byproducts

`runs/` worktrees, SQLite stores, caches, and other execution byproducts are ephemeral. They are garbage-collected on success. On failure, they are retained until the defect closes so the diagnostic state remains inspectable.

# Completion distillation

After completion, facts land in `docs/` and process lands in `archive/`. Distilled facts must describe the durable project truth; process records must preserve how the task was executed, reviewed, and approved without becoming the active authority.

Loop notes, temporary module records, generated WorkflowIR files, and short
task-local scripts are run byproducts unless separately promoted. At the end of
a run, a distillation step may create a durable lesson or module proposal under
`docs/` only when it includes provenance, applicability, non-applicability, and
evidence references. Raw notes do not become project truth by existing alone.

For dynamically synthesized workflows, workflow drafts and self-adjustments also
stay in task-local storage during execution. Only a run that completes normally
and reaches its confirmed acceptance condition may distill its workflow shape
into a project-local Skill under `skills/workflows/`. The distillation pass must
filter out one-off context, temporary paths, stale assumptions, and unsuccessful
attempts before writing the reusable Skill artifact.

For dynamically synthesized workflows, the fixed run layout under
`work/tasks/<TASK-ID>/runs/<RUN-ID>/` is a contract surface. `contract/` records
are frozen after human confirmation, `tmp/` holds mutable iteration byproducts,
`evidence/` is append-only evidence, `evidence/briefing-inputs/` contains the
dynamic workflow output package for external acceptance briefing, `handoff/`
contains the mandatory human review artifacts written outside WorkflowIR, and
`distillation/` is written only after confirmed acceptance.
`tmp/` is never a direct input source for external human acceptance briefing.
Temporary material must be promoted into `evidence/briefing-inputs/` or another
evidence artifact before it can influence the final human review package.

The HTML technical report, `HumanAcceptancePackageManifest`,
`HumanAcceptanceDecision`, and review package are mandatory handoff or evidence
artifacts for every dynamically synthesized workflow. The HTML report and
package manifest are produced by a fresh external Human Acceptance Briefing
Agent, not by WorkflowIR. They must be retained with the task or run record
until acceptance is resolved. They help the user review the work, record the
user's final decision, and let the outer workflow validate handoff completeness,
but they do not become durable project truth unless separately distilled into
reviewed docs.
