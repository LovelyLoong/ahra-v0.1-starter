---
type: Concept
id: DOCS-architecture-observability-evaluation
schema_version: awkp/0.1
title: Observability and Evaluation
description: Defines the minimal local trace, audit, cost, replay, and eval records needed by the starter.
status: active
owner: team:platform
source_refs: [../../architecture/SPEC.md, ../../src/ahra/ports.py]
evidence_refs: []
confidence: reviewed
last_verified_at: 2026-06-22T00:00:00Z
review_after: 2026-09-22T00:00:00Z
tags: [architecture, observability, evaluation]
---

# Purpose

Observability and Evaluation give the framework evidence about how a run
behaved, how much it cost, whether it followed policy, and whether a new agent
release is safe to use.

This is not a requirement to adopt a specific UI product. The starter should
start with local records and ports, then allow OTel or a hosted backend later.

# Minimum Local Records

The first implementation should keep four concepts separate:

| Record | Purpose | Sampling |
|---|---|---|
| Audit event | Non-repudiable security and state-change fact | Never sampled away |
| Debug trace | Model/tool/runtime timing and metadata | May be sampled or expired |
| Cost ledger | Token, tool, runtime, and external service cost | Should be complete per run |
| Eval result | Test or benchmark outcome for a task or agent release | Evidence-producing |

Telemetry is not the authoritative task state. Task state remains in AWKP, Run
state remains in RunStore, and artifacts/evidence remain in their manifests.

# Implemented Local Record Shape

The starter defines the first local-only shape in
`contracts/schemas/local-observability-record.schema.json` with
`schema_version: ahra/local-observability-record/0.1`.

Each record has a common envelope:

- `record_type`: one of `audit_event`, `trace_summary`, `usage_summary`, or
  `eval_result`.
- `record_id`, `task_id`, optional `run_id`, optional `context_id`.
- `created_at` and `created_by`.
- `refs` for AWKP artifacts, evidence, events, tasks, or verifier commands.
- `payload`, whose schema is selected by `record_type`.

Local records are written with deterministic JSON serialization. The helper in
`src/ahra/local_observability.py` hashes the serialized bytes, writes the file
under `work/tasks/<TASK-ID>/local-records/`, and attaches content-addressed
`ART-...` and optional `EVD-...` manifest records. The helper does not update
`state.json` or `events.jsonl`; those remain the AWKP state and audit
authorities.

`eval_result` records may be attached as Evidence when a verifier or local
runner uses them to support an acceptance decision. `audit_event`,
`trace_summary`, and `usage_summary` records are inspectable artifacts unless a
task explicitly chooses to promote one as evidence.

# Privacy Defaults

The local default should record metadata first:

- IDs, hashes, byte sizes, timing, status, and references;
- model name or model profile;
- token counts and cost estimates;
- tool name, argument digest, and result digest;
- artifact and evidence references.

Prompt text, completion text, raw tool output, and memory content should require
an explicit opt-in and should be scrubbed before export.

Private chain of thought must not be stored. Store concise action reasons,
policy decisions, command results, and verifier conclusions instead.

# Evaluation Scope

Evaluation should cover:

- schema and contract validity;
- deterministic checks and unit tests;
- tool trajectory and permission boundaries;
- task outcome and artifact correctness;
- security cases such as prompt injection and path escape;
- recovery behavior;
- cost and latency budget.

Eval results should become AWKP Evidence when they are used to approve a task,
agent release, or framework change.

# Minimal Implementation Path

After EvidenceGate, add a local `EvalRunner` and trace/audit adapter in three
small steps:

1. emit a per-run metadata trace artifact with IDs, durations, commands, and
   references;
2. emit a cost ledger artifact for model/tool/runtime usage where data exists;
3. add an `EvalSuite` descriptor and a local runner that converts results into
   Evidence.

This keeps the starter AI-operable without forcing CI, dashboards, or hosted
observability products.
