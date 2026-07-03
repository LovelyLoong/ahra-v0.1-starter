---
type: Handoff
id: HANDOFF-TASK-0005-0001
schema_version: awkp/0.1
title: Reference runner isolation fix ready for verification
description: Handoff for independent review of default local workspace isolation and cross-platform check entrypoint.
status: active
owner: agent:verifier
task_id: TASK-0005
from: agent:codex
to: agent:verifier
state: review
source_refs: [../task.md, ../state.json, ../artifact-manifest.json]
artifact_refs: [ART-TASK-0005-0001]
evidence_refs: [EVD-TASK-0005-0001]
confidence: tested
created_at: 2026-06-22T14:36:00Z
last_verified_at: 2026-06-22T14:36:00Z
review_after: 2026-09-22T00:00:00Z
tags: [handoff, workflow, workspace-isolation]
---

# Goal and state

TASK-0005 is in `review`. The implementation agent has not marked the task
completed.

# Completed

- Documented local runner workspace isolation before implementation.
- Changed default `run_workflow()` to create a run-owned Git worktree.
- Recorded `workspace.json` with source and effective workspace metadata.
- Changed manual resume to continue the stored effective workspace.
- Added regression tests proving the source workspace remains unchanged.
- Added `python scripts/check.py` for Windows-friendly verification.

# Verification

- `python scripts\check.py`
- `python scripts\lint_awkp.py`
- `git diff --check`

# Exact next action

Independent verifier reruns the checks, inspects the default runner isolation
path, then updates TASK-0005 to `completed` or `changes_requested`.

# Blockers and required input

None known.

# Failed approaches

None recorded.

# Risks and assumptions

Custom injected workspace providers are not changed by this task; they remain
responsible for their own isolation semantics.

# Lease

Released; no holder.
