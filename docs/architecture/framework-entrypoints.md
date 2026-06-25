---
type: Architecture
id: ARCH-framework-entrypoints
schema_version: awkp/0.1
title: Framework entrypoints
description: Defines the current default way humans and agents operate this Agent workflow foundation.
status: active
owner: team:platform
source_refs:
  - ../../AGENTS.md
  - ../../README.md
  - ../../skills/ahra-dynamic-kernel/SKILL.md
  - component-inventory.json
evidence_refs: []
confidence: reviewed
last_verified_at: 2026-06-25T16:05:13Z
review_after: 2026-09-25T00:00:00Z
tags: [architecture, entrypoint, cli, skill, dynamic-kernel]
---

# Summary

The default foundation entrypoint is **CLI plus the dynamic-kernel Skill plus
repository documentation**.

The current executable dynamic path is deterministic and local. It proves one
authoritative runtime chain:

```text
GoalContract
  -> ClaimGraph and GatePlan
  -> untrusted PlanDraft
  -> admitted PlanIR
  -> StaticPlanIRScheduler and NodeRun leases
  -> CapabilityAdmission and CapabilityGateway
  -> Artifact and Evidence v2 records
  -> Defect repair and selective reverification
  -> GoalCompletionService
  -> AWKP EvidenceGate for task completion
```

This path is exercised by the dynamic repair fixture. It is not a claim that
AHRA already provides a production-grade general orchestrator for arbitrary
projects.

# Current Operation Surface

The default local operation surface is:

- `python -m ahra.cli fixture dynamic-repair --fixture tests/fixtures/dynamic-goal-project --report <report.json>`
- `python -m ahra.cli task inspect <TASK-ID>`
- `python -m ahra.cli evidence-gate evaluate <TASK-ID> --expected-version <N> --report <report.json> --actor <verifier>`
- `python -m ahra.cli doctor`
- `python -B scripts/check.py`
- `python -B scripts/check.py --lint`
- `python -B scripts/check.py --test`
- `python -B scripts/lint_awkp.py`
- `git diff --check`

On the maintainer workstation, `.venv\Scripts\python.exe` or `uv run python`
may be used for the same commands when the bare Python launcher is affected by
host encryption tooling.

# CLI Boundary

The CLI wrapper is intentionally narrow and must not invent runtime logic. It
exposes existing Python services:

- `fixture dynamic-repair`
- `task inspect`
- `evidence-gate evaluate`
- `doctor`

The default CLI help must not expose MCP, demo commands, `fake-reference`, or
legacy workflow modules. Historical workflow compatibility remains reachable
only when explicitly requested by a caller that already knows that compatibility
route.

# Default Dynamic Fixture

The dynamic repair fixture is fixture-scoped but authoritative for the current
implemented chain. It must demonstrate:

- Goal input before task decomposition.
- Claims and Gates before PlanIR.
- Planner output compiled and admitted before execution.
- Capability denial before side effect.
- Artifact and Evidence records for every accepted node result.
- Defect creation with reproduction and repair boundary.
- Selective reverification with documented Evidence reuse.
- Completion that rejects stale, uncovered, or open-defect evidence.

# Legacy Compatibility

`standard-harness`, `loop-engineering`, old workflow request schemas, the
reference runner compatibility path, and `fake-reference` are legacy assets.
They are retained for regression tests and migration trace. They are frozen for
default-route purposes and must not receive new default-path features.

The MCP server is also legacy. It has no default console script and is not part
of the local operation route.

`src/ahra/demo.py` is experimental/example code. It has no default console
script or Makefile target.

# Archive Boundary

Completed task directories remain traceable audit records. They are excluded
from normal Context Builder read order unless the current task, event, evidence
record, or user request explicitly references them.
