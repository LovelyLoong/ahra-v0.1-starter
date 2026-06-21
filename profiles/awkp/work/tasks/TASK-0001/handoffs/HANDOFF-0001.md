---
type: Handoff
id: HANDOFF-0001
schema_version: awkp/0.1
title: Bootstrap task ready for claim
description: Initial handoff for validating the reference starter.
status: active
owner: human:maintainer
source_refs: [../task.md, ../state.json]
evidence_refs: []
confidence: verified
last_verified_at: 2026-06-21T00:00:00Z
review_after: 2026-06-22T00:00:00Z
tags: [handoff]
---

# Goal and state

TASK-0001 is in `ready`; no lease is held.

# Completed

The reference repository, schemas, and initial task package have been created.

# Verification

No verification has yet been published.

# Exact next action

Atomically claim TASK-0001, append `lease_acquired`, and run `python3 scripts/lint_awkp.py`.

# Blockers and required input

None.

# Failed approaches

None.

# Risks and assumptions

Assumes Python 3.10 or newer and a clean checkout.

# Touched assets

Repository template only.

# Lease

Released; no holder.
