---
type: Defect
id: DEF-manual-bypass-awkp
schema_version: awkp/0.1
title: "Manual Bypass of AWKP Governance"
description: "Governance-process defect recording a manual bypass of the AWKP loop."
owner: human:maintainer
status: documented
---

# Defect: Manual Bypass of AWKP Governance

**Defect ID**: DEF-manual-bypass-awkp  
**Created**: 2026-07-03  
**Severity**: governance-process  
**Status**: documented

## Summary

TASK-0089 and TASK-0091 had their code changes committed to git (commits 72ed577 and 11a7a87) through a manual path that bypassed the complete AWKP governance flow. While the code changes were correct and verified, the governance state machine (state.json) was not updated, and no evidence_refs were recorded at the time of completion.

## What Happened

1. **TASK-0091**: Workflow B execution GEXEC-187a468033890487 succeeded, code changes were committed (11a7a87), but state.json remained at `ready` v0
2. **TASK-0089**: Workflow B execution GEXEC-cf02e0a118cfd781 was rejected by policy gate (2044 files > 30 limit, 61869 lines > 800 limit). The rejected patch was manually reviewed and merged (72ed577, 2cdea3c), but state.json remained at `ready` v0

## Root Cause

The maintainer (in conversation context) performed git commits after verifying the work, but did not run the AWKP governance CLI commands (`task claim`, `task orchestrate-review`, `evidence-gate evaluate`) to update the authority state.

## Impact

- Git history accurate, code changes correct
- AWKP governance state inconsistent (state.json not updated)
- Dependency checking broken (TASK-0090 depends on TASK-0089, but 0089 shows as `ready` not `completed`)
- No evidence_refs recorded for auditability

## Resolution

Attempted retrospective governance completion via `ahra task claim` and `ahra evidence-gate evaluate` on 2026-07-03. Process blocked by EvidenceV2 format requirements.

**Workaround**: Document the defect, commit the partial governance records, and proceed with TASK-0090 as the first task to follow the complete A→B flow correctly.

## Prevention

TASK-0090 will add the binding rule: "New work defaults to Workflow A + B loop; manual paths must be recorded as loop defects."

## References

- Git commits: 72ed577, 11a7a87, 2cdea3c
- Workflow B runs: GEXEC-cf02e0a118cfd781 (rejected), GEXEC-187a468033890487 (succeeded)
- Tasks affected: TASK-0089, TASK-0091
- Discovered during: TASK-0090 preparation
