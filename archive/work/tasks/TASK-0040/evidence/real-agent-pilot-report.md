---
type: Evidence
id: EVD-TASK-0040-0003
schema_version: awkp/0.1
title: TASK-0040 real-Agent pilot report
description: Producer report for the bounded real Planner and real Executor pilot, updated after EvidenceGate changes requested.
status: active
owner: agent:codex-dynamic-kernel-operator
source_refs:
  - ../task.md
  - real-agent-pilot-summary.json
  - real-agent-pilot/mode-a/scorecard.json
  - real-agent-pilot/mode-b/scorecard.json
  - evidence-gate-response-7.json
evidence_refs:
  - EVD-TASK-0040-0004
  - EVD-TASK-0040-0005
  - EVD-TASK-0040-0006
  - EVD-TASK-0040-0007
  - EVD-TASK-0040-0008
  - EVD-TASK-0040-0009
confidence: producer-reviewed
last_verified_at: 2026-06-28T04:33:08.152569Z
review_after: 2026-09-28T00:00:00Z
tags: [task-0040, real-agent-pilot, final-report, evidencegate-response]
---

# TASK-0040 Real-Agent Pilot Report

Created at: 2026-06-28T03:55:24.849927Z
Updated at: 2026-06-28T04:33:08.152569Z
Actor: agent:codex-dynamic-kernel-operator

## Scope Executed

- Mode A: 5 repetitions, real Planner, deterministic Executor and GateRunner.
- Mode B: 5 repetitions, deterministic Planner, real bounded Executor, deterministic GateRunner.
- Mode C: skipped by producer go/no-go decision because Mode A has a reproducible Planner output blocker and Mode B has runner timeout instability.

## EvidenceGate Response

- Mode B run 05 lineage is now independently resolvable with `goal inspect --artifact-dir`: `missingArtifactCount=0`, `artifactFindings=[]` at code commit `51418de`.
- Mode A planner failures now preserve invalid Planner output evidence in each run under `.ahra/artifacts/planner-invalid-output.json` and `.ahra/artifacts/planner-invalid-output-artifact.json`.
- The previous EvidenceGate changes-requested report remains preserved as `evidence/evidence-gate-report-6.json`; this producer response is `evidence/evidence-gate-response-7.json`.

## Results

| Mode | Runs | Successes | Failure classes | Hard metrics |
|---|---:|---:|---|---|
| Mode A | 5 | 0 | {"planner-output-invalid": 5} | zero false completion, zero unrun gate pass, zero duplicate resume effect |
| Mode B | 5 | 1 | {"runner_timeout": 4} | zero false completion, zero unrun gate pass, zero duplicate resume effect |

Mode A did not start Goal execution in any run. The real Planner output failed closed as `planner-output-invalid`; the invalid raw output and parsed driver output are now preserved with SHA-256 digests per run.

Mode B completed one run successfully. The successful bounded Executor run has a capability grant, node gate evidence, deterministic evidence, semantic-review-skipped evidence, and current independent `goal inspect --artifact-dir` reports no missing artifact findings. Four runs exceeded the process-level repetition timeout and are classified as `runner_timeout`.

## Failure Taxonomy

- `planner-output-invalid`: planner/model-adapter layer. Count: 5. Evidence: `evidence/real-agent-pilot/mode-a/scorecard.json` and each run's `planner-invalid-output*.json` artifacts.
- `runner_timeout`: executor/model-runtime layer. Count: 4. Evidence: `evidence/real-agent-pilot/mode-b/scorecard.json` and per-run `run-result.json`.

## Acceptance Mapping

- Mode A and Mode B each ran five bounded repetitions through the generic Goal path or failed closed before execution as required.
- Planner output was never executed without admission. Invalid Planner output was blocked before Goal start and preserved as inspectable artifacts.
- The successful Executor side effect has Capability Admission and audit lineage in Mode B run 05.
- Hard safety metrics remained zero for false completion, unrun gate pass, stale fencing accept, and resume duplicate effect.
- The report identifies a reproducible Mode A model/adapter blocker without weakening criteria.
- Token/cost fields are recorded as unavailable where the provider did not expose them; no synthetic usage values were invented.
- Mode C was skipped by producer decision and must not be treated as completed.

## Verification

- `.\.venv\Scripts\python.exe -m unittest tests.test_real_agent_pilot tests.test_planning tests.test_goal_operations -v` passed: 18 tests.
- `.\.venv\Scripts\python.exe -m ahra.cli goal inspect GEXEC-130c5ba6602a532d --db work	asks\TASK-0040\evidence
eal-agent-pilot\mode-b
un-05\.ahra\goal-control.sqlite3 --artifact-dir work	asks\TASK-0040\evidence
eal-agent-pilot\mode-b
un-05\.ahrartifacts` passed: `missingArtifactCount=0`, `artifactFindings=[]`.
- Mode A invalid planner artifact audit passed: 5/5 runs have raw output and driver output digests.
- `.\.venv\Scripts\python.exe -B scripts\check.py --lint` passed.
- `.\.venv\Scripts\python.exe -B scripts\lint_awkp.py` passed.
- `git diff --check` passed with CRLF/LF normalization warnings only.
- `.\.venv\Scripts\python.exe -B scripts\check.py --test` passed: 190 tests, 2 skipped.

## Recommendation

No-go for combined Mode C in this increment. Fix or prompt-harden the real Planner structured output first, then review real Executor timeout behavior before allowing combined mode.

## Next Action

Independent SG-10 EvidenceGate re-review should inspect `evidence/evidence-gate-response-7.json`, the updated scorecards, manifests, and Mode B run 05 lineage. The producer does not mark TASK-0040 complete.
