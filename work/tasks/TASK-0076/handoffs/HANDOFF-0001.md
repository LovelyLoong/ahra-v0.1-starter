---
type: Handoff
id: HANDOFF-TASK-0076-0001
schema_version: awkp/0.1
title: TASK-0076 producer handoff
description: Producer handoff for independent TASK-0076 EvidenceGate review.
task_id: TASK-0076
owner: agent:claude-code
status: review
created_by: agent:claude-code
created_at: 2026-07-01T08:30:00Z
---

# Handoff

TASK-0076 implementation is ready for independent EvidenceGate review.

`HostileAgentDriver` (`src/ahra/adapters/hostile_driver.py`) is a deterministic,
scenario-driven `AgentDriver` adapter that replays the hostile/careless actions
paid dogfood runs have already exposed (D1 destructive git, D2 out-of-allowlist
write, D4 always-fail), with framework-layer regressions for D3 non-GBK
subprocess and D5 None gate-selection. It is opt-in only, registered under
immutable-version refs, and never the default development executor. The
consolidated free invariant suite is `tests/test_hostile_agent_driver.py`.

Verification passed:

- `.venv/Scripts/python.exe -B -m unittest tests.test_hostile_agent_driver tests.test_development_worktree_isolation tests.test_verification tests.test_plan_execution tests.test_node_executor` — 69 tests passed.
- `.venv/Scripts/python.exe -B scripts/check.py` — full lint + 299 tests passed, 1 skipped.
- `git diff --check` — exit 0.

Evidence: `evidence/hostile-agent-driver-report.md`, `evidence/verification-summary.json`.

# Single next action

With the HostileAgentDriver invariant suite green, re-run the paid
development-bounded dogfood (`examples/goals/dogfood-a-alignment-session.yaml`
via `ahra goal start --allow-development-agent`) in the isolated worktree. With
framework invariants now pinned for free in CI, the paid run is a pure
**capability** test — "can the real Agent produce a conformant
`alignment_session.py`" — and its failures give clean signal rather than another
destructive framework trap. This re-run is a separate step, performed only after
TASK-0076 is EvidenceGate-approved and committed.
