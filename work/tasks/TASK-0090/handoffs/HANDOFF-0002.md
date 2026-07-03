# HANDOFF-0002 — DEF-wf-a-draft-contract-apiversion fixed, awaiting codex SDK

**From**: agent:contract-fixer
**To**: maintainer
**Date**: 2026-07-03
**Task state**: working v1 (defect fixed, awaiting environment setup to resume)

## What was completed

Fixed DEF-wf-a-draft-contract-apiversion, the blocker that prevented TASK-0090's
A→B loop from completing the draft stage.

### Changes made

1. **Contract fix** (`src/ahra/alignment_session.py:605-656`):
   - `REQUIREMENT_DRAFT_OUTPUT`: Added complete nested schema for `planDraft`
     requiring `apiVersion`, `kind`, `metadata`, `spec` with proper constraints
   - `ACCEPTANCE_DRAFT_OUTPUT`: Added complete nested schema for `claimGraph`
     requiring `apiVersion`, `kind`, `metadata`, `spec` with proper constraints
   - Both now match what the domain parsers (`PlanDraft.from_mapping`,
     `ClaimGraph.from_mapping`) expect

2. **Regression test** (`tests/test_alignment_session.py`):
   - Added `test_draft_contract_requires_nested_apiversion_for_plan_and_claim`
   - Verifies contract schemas explicitly declare the nested structure
   - Prevents regression to under-specified contracts

3. **Verification**:
   - All 13 alignment_session tests pass
   - Full test suite: 339 tests, 1 pre-existing failure (Python 3.14 compatibility
     in reference_runner, unrelated to this fix)
   - Committed as bb41510

## What blocks resumption

The `workflow-a draft` command requires the `codex-python-sdk` driver, which
needs the `[codex]` extra:

```bash
pip install -e .[codex]
```

or

```bash
uv pip install -e .[codex]
```

Once installed, resume from the frozen session:

```bash
PYTHONPATH=src python -m ahra.cli workflow-a draft \
  --session work/tasks/TASK-0090/runs/loop-001/session.json \
  --request-draft work/tasks/TASK-0090/runs/loop-001/request-draft.json \
  --approval work/tasks/TASK-0090/runs/loop-001/approval.json \
  --driver-ref codex-python-sdk
```

The frozen requirement and session state are preserved; the draft stage should
now succeed with the corrected contracts.

## Next action

Maintainer: install codex extra, then resume the A→B loop from draft stage to
complete TASK-0090 end-to-end validation.
