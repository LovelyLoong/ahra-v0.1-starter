---
type: Handoff
id: HANDOFF-TASK-0032-0001
schema_version: awkp/0.1
title: TASK-0032 repository consolidation handoff
description: Producer handoff for independent EvidenceGate review of TASK-0032 repository consolidation.
status: review
owner: agent:codex-dynamic-kernel-operator
task_id: TASK-0032
created_by: agent:codex-dynamic-kernel-operator
created_at: 2026-06-25T16:19:15.889392Z
---

# TASK-0032 Handoff

Producer: `agent:codex-dynamic-kernel-operator`

State requested: `review`

## Summary

TASK-0032 consolidates the repository default path around the dynamic-kernel
fixture and quarantines legacy workflow, MCP, demo, and fake-driver surfaces.
It does not delete historical audit records or claim a production-grade general
orchestrator.

## Evidence

- `work/tasks/TASK-0032/evidence/component-inventory.json`
- `work/tasks/TASK-0032/evidence/repository-consolidation-report.json`
- `work/tasks/TASK-0032/evidence/dynamic-fixture-command-report.json`
- `work/tasks/TASK-0032/evidence/verification-report.json`

## Verification

- `.venv\Scripts\python.exe -B -m ahra.cli fixture dynamic-repair --fixture tests\fixtures\dynamic-goal-project --report work\tasks\TASK-0032\evidence\dynamic-fixture-command-report.json`
- `.venv\Scripts\python.exe -B -m unittest tests.test_repository_consolidation tests.test_cli tests.test_dynamic_fixture tests.test_plan_execution tests.test_capabilities -v`
- `.venv\Scripts\python.exe -B scripts\check.py --lint`
- `.venv\Scripts\python.exe -B scripts\check.py`
- `git diff --check`

## Reviewer Notes

- `ahra workflow ...` still exists as an explicit hidden compatibility command
  and is covered by legacy tests; it is not shown in default CLI help.
- `ahra-mcp` and `ahra-demo` were removed from default console scripts.
- `ART-TASK-0032-0001.uri` now points to
  `local://evidence/component-inventory.json`, matching EvidenceGate's
  task-local `local://` resolution rule.
- `src/ahra/demo.py` and `src/ahra/mcp_server.py` remain traceable code, not
  default operation paths.
- Completed task directories are kept under `work/tasks/` as append-only audit
  records and excluded from normal context loading unless explicitly referenced.
