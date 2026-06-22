---
type: HarnessPolicy
id: WORKFLOW-root
schema_version: awkp/0.1
title: AWKP and AHRA template workflow
description: Root policy for AWKP task governance plus AHRA contract development.
status: active
owner: team:platform
last_verified_at: 2026-06-21T00:00:00Z
review_after: 2026-09-21T00:00:00Z

state_backend: filesystem
state_authority: work/tasks/*/state.json
event_authority: work/tasks/*/events.jsonl
knowledge_authority: docs/
artifact_authority: artifact-manifest.json

orchestrator:
  max_concurrent_tasks: 4
  poll_interval_seconds: 30
  lease_ttl_seconds: 600
  heartbeat_interval_seconds: 120
  max_attempts: 3
  retry_backoff: exponential

approval:
  R0: automatic
  R1: independent_agent_verification
  R2: human_preapproval_and_review
  R3: human_owned
---

# Dispatch policy

Only tasks in `ready` with satisfied dependencies and no blocker may be claimed. Claiming must atomically increment `state_version`, set the lease, append `lease_acquired`, and move the task to `working`.

# Execution policy

Use one isolated branch/worktree per task. Work one verifiable increment at a time. Run a baseline check before modifying the system. Do not modify acceptance criteria after claim without an approved `scope_changed` event.

# State policy

All state writes require compare-and-swap against `state_version`. `events.jsonl` is append-only. A compensating event corrects mistakes. On restart, reconcile state against the event ledger.

# Verification policy

The producing agent publishes Artifact and Evidence, then requests review. A verifier distinct from the producer checks the acceptance criteria. R2/R3 actions require human approval according to the frontmatter policy.

# Handoff policy

Create an immutable Handoff when a lease is released before completion, a context is near exhaustion, work is blocked, or ownership changes. Include one exact next action and failed approaches.

# Knowledge policy

Promote only cross-task, durable facts, decisions, runbooks, or constraints into `docs/`. Every active concept needs owner, source/evidence, `last_verified_at`, and `review_after`. Doc-gardening changes open a PR.

# Harness contract development

Change AHRA infrastructure in this order:

1. Modify or add `contracts/schemas/`.
2. Update `architecture/SPEC.md` or an ADR with compatibility notes.
3. Update domain objects and `src/ahra/ports.py`.
4. Update adapters or reference implementations.
5. Add contract, recovery, and security tests.
6. Run `python scripts/check.py`. `make check` may wrap the same checks where
   `make` is available.

Compatibility rules:

- Adding optional fields is allowed within the same minor profile.
- Changing field meaning, deleting fields, or tightening enums requires a new schema version.
- Event consumers must ignore unknown extension fields, but must not ignore an unknown event major version.
- Release, Tool, Runtime, and Workflow must run by digest or immutable version.

Completion gates:

- Schema examples validate.
- Legal and illegal state transitions have tests.
- Retry, duplicate event, and lease expiry paths have tests.
- High-risk Tool calls without Approval are denied.
- Memory cannot become active without promotion.
- Context Manifest generation is deterministic for the same input.
- Domain code does not import concrete cloud, model, or Agent SDK dependencies.
