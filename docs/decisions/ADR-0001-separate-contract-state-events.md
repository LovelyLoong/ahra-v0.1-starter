---
type: Decision
id: ADR-0001
schema_version: awkp/0.1
title: Separate task contract, state snapshot, and event ledger
description: Avoids concurrency conflicts and preserves a durable audit trail.
status: active
owner: team:platform
source_refs: [SPEC.md]
evidence_refs: []
confidence: reviewed
last_verified_at: 2026-06-21T00:00:00Z
review_after: 2026-12-21T00:00:00Z
tags: [architecture, workflow]
---

# Decision

Use `task.md` for stable intent and acceptance, `state.json` for current machine state, and `events.jsonl` for append-only history.

# Rationale

These artifacts change at different rates and have different concurrency requirements. Separating them prevents a shared prose file from becoming both a lock and a knowledge base.

# Consequences

The Harness must reconcile state and events, enforce CAS, and generate human-facing indexes from authoritative data.
