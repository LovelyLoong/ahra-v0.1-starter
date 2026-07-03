---
type: Evidence
id: EVD-TASK-0039-0001
schema_version: awkp/0.1
title: TASK-0039 implementation report
description: Producer report for the deterministic M1 minimal live loop experiment and baseline.
status: active
owner: agent:codex-dynamic-kernel-operator
source_refs:
  - ../task.md
  - ../../../tests/fixtures/m1-minimal-project/goal-run-request.yaml
  - ../../../src/ahra/m1_experiment.py
  - ../../../scripts/run_m1_minimal_experiment.py
evidence_refs:
  - EVD-TASK-0039-0002
  - EVD-TASK-0039-0003
  - EVD-TASK-0039-0004
  - EVD-TASK-0039-0005
  - EVD-TASK-0039-0006
confidence: reviewed
last_verified_at: 2026-06-26T11:03:00Z
review_after: 2026-09-25T00:00:00Z
tags: [task-0039, m1, experiment, evidence]
---

# Summary

TASK-0039 adds a deterministic M1 minimal project fixture and a repeatable experiment command that exercises the generic `ahra goal` operation path.

The producer implementation does not introduce a real LLM, does not target AHRA for self-modification, and does not mark the AWKP task completed.

# Changed files

- `src/ahra/m1_experiment.py`: deterministic experiment service for P0/P3 repetitions plus P1 defect-repair and P2 security-denial profiles.
- `scripts/run_m1_minimal_experiment.py`: command entrypoint for the twenty-run experiment.
- `tests/test_m1_experiment.py`: focused regression covering scorecard generation, hard metrics, P1 raw GateRuns, and security denial.
- `tests/fixtures/m1-minimal-project/`: isolated fixture project and GoalExecutionRequest.
- `work/tasks/TASK-0039/`: authoritative task state, event ledger, manifests, evidence, and handoff.

# Producer Release Context

- Workspace: `E:\ahra-v0.1-starter`
- Branch: `main`
- Base commit: `7a65ac64c71c19ec7790346815478be64ffc5848`
- Final commit: not created; this is an uncommitted producer patch for independent review.
- Producer Agent Release: `agent:codex-dynamic-kernel-operator`
- Context Manifest: `CTX-ahra-dynamic-kernel`

# Experiment command

The producer ran:

```bash
uv run python -B scripts/run_m1_minimal_experiment.py --request tests\fixtures\m1-minimal-project\goal-run-request.yaml --output work\tasks\TASK-0039\evidence\m1-experiment --runs 20
```

The command completed with `ok: true`.

# Results

- `run_count`: 20
- `success_count`: 20
- `false_completion_count`: 0
- `gate_execution_integrity`: 1.0
- `current_claim_coverage`: 1.0
- `capability_admission_coverage`: 1.0
- `repair_boundary_compliance`: 1.0
- `resume_duplicate_effect_count`: 0
- `stale_fencing_accept_count`: 0
- `unrun_gate_pass_count`: 0
- `unauthorized_write_allowed`: false
- `weighted_verification_saving`: 0.33333333333333337
- `semanticDigestDistribution`: one normalized digest across all 20 runs

# Acceptance mapping

| Criterion | Evidence |
|---|---|
| Twenty consecutive runs complete with false_completion_count = 0 | `EVD-TASK-0039-0002`, `m1-scorecard.json` |
| gate_execution_integrity = 1.0 in every run | `EVD-TASK-0039-0002`, run summaries |
| current_claim_coverage = 1.0 at every accepted completion | `EVD-TASK-0039-0002` |
| capability_admission_coverage = 1.0 for every executed side effect | `EVD-TASK-0039-0002`, `EVD-TASK-0039-0003`, `EVD-TASK-0039-0005` |
| repair_boundary_compliance = 1.0 | `EVD-TASK-0039-0003` |
| resume_duplicate_effect_count = 0 and stale_fencing_accept_count = 0 | `EVD-TASK-0039-0004`, run summaries |
| Selected actual verification cost is lower than full baseline | `EVD-TASK-0039-0003` |
| Every reused Evidence record has current-set inspection and rationale | `EVD-TASK-0039-0003` |
| Normalized semantic results are stable across all runs | `EVD-TASK-0039-0002` |
| Source fixture and AHRA remain unmodified outside declared locations | `git diff --check`, `EVD-TASK-0039-0002`, `EVD-TASK-0039-0005`, `EVD-TASK-0039-0006`, task-local artifacts |
| Independent verifier reviews raw Artifacts, GateRuns and scorecard | Handoff requires review of raw P1 GateRuns and all scorecard inputs |
| Passing EvidenceGate authorizes M1 deterministic claim | Pending independent EvidenceGate review |

# Known limitations

- The experiment is deterministic and local. It uses SQLite and local process execution only.
- The real-Agent pilot is intentionally excluded and remains TASK-0040.
- Producer evidence is not the final acceptance decision. The task must remain in `review` until independent EvidenceGate approval.
