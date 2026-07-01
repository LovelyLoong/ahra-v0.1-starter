---
type: WorkItem
id: TASK-0076
schema_version: awkp/0.1
title: "HostileAgentDriver - free replay-based adversarial AgentDriver that hardens dogfood invariants in CI"
description: "Stop discovering one reliability defect per paid real-Agent dogfood run. Add a deterministic AgentDriver adapter that replays the exact hostile/careless actions the real dogfood runs have already exposed (git reset --hard + git clean -fd in the worktree, out-of-allowlist writes, non-GBK stderr, a second attempt past maxAttempts=1, a None gate-selection at 305s) so the TASK-0074 isolation and TASK-0072/0073/0075 invariants are provable for free in scripts/check.py, and the paid dogfood becomes a pure capability test."
context_id: "CTX-workflow-b-reliability"
priority: "P1"
risk_level: "R2"
requester: "human:maintainer"
reviewer: "agent:independent-verifier"
created_at: 2026-07-01T08:14:09.383577Z
depends_on: ["TASK-0074", "TASK-0075"]
input_refs: ["../../../src/ahra/ports.py", "../../../src/ahra/reference_runner/bounded_task.py", "../../../src/ahra/reference_runner/git_ops.py", "../../../src/ahra/reference_runner/task_harness.py", "../../../src/ahra/adapters/codex_sdk.py", "../../../examples/runtimes/local-worktree.yaml", "../../../work/tasks/TASK-0074/task.md", "../../../work/tasks/TASK-0075/task.md"]
output_contract:
  - kind: "hostile_agent_driver_adapter"
  - kind: "invariant_regression_tests"
  - kind: "verification_summary"
  - kind: "handoff"
---

# Goal

Stop discovering one reliability defect per paid real-Agent dogfood run. Add a deterministic AgentDriver adapter that replays the exact hostile/careless actions the real dogfood runs have already exposed (git reset --hard + git clean -fd in the worktree, out-of-allowlist writes, non-GBK stderr, a second attempt past maxAttempts=1, a None gate-selection at 305s) so the TASK-0074 isolation and TASK-0072/0073/0075 invariants are provable for free in scripts/check.py, and the paid dogfood becomes a pure capability test.

# Acceptance criteria

- [ ] HostileAgentDriver implements the AgentDriver protocol (async run(AgentRunRequest)->AgentRunResult) and is registered in AgentDriverRegistry under an immutable-version ref; not on the default path.
- [ ] Scenario D1 (destructive git: git reset --hard + git clean -fd) replayable; regression asserts main repo tree and a seeded uncommitted file unchanged - re-proves TASK-0074 isolation for free.
- [ ] Scenario D2 (out-of-allowlist write) replayable; regression asserts blacklisted path not propagated back into governed workspace.
- [ ] Scenario D3 (non-GBK stderr) replayable through subprocess path; regression asserts no UnicodeDecodeError.
- [ ] Scenario D4 (retry past maxAttempts=1) replayable; regression asserts node executes exactly one attempt on failure, no second attempt.
- [ ] Scenario D5 (None gate-selection at wall) replayable; regression asserts verification/gate path treats it as empty selection and does not raise NoneType has no len().
- [ ] Deterministic end-to-end run using HostileAgentDriver (no model cost) completes within free-invariant envelope and runs under scripts/check.py.
- [ ] M1 deterministic path and real development-bounded path unaffected; HostileAgentDriver is opt-in only.
- [ ] python scripts/check.py (lint + full tests) passes, or blockers recorded with exact command output.
- [ ] Producer moves TASK-0076 only to review; EvidenceGate decides completion.

# Background

So far each new class of framework defect was discovered mid-run during a paid
real-Agent dogfood, and the first one was destructive (TASK-0074: the real Agent
ran `git reset --hard` + `git clean -fd` in the main tree and wiped uncommitted
TASK-0072/0073 work). Today there is **no reusable adversarial Agent harness**:
searching `src/` for fake/hostile/replay agent drivers returns nothing - the
only `AgentDriver` implementations are the real `CodexSDKDriver`
(`src/ahra/adapters/codex_sdk.py`) and fixture stubs.

Concrete hostile actions already observed, each tied to a prior task's fix:

- **D1 destructive git** (TASK-0074): `git reset --hard` + `git clean -fd` run
  inside the Agent workspace. After 0074 the workspace is an isolated throwaway
  worktree (`bounded_task.py` now uses the local-worktree provider);
  HostileAgentDriver must reproduce this action so the isolation guarantee
  (`tests/test_development_worktree_isolation.py`) is exercised for free.
- **D2 out-of-allowlist writes** (TASK-0071): writes to a blacklisted path
  (e.g. `evidence_gate.py`). The filesystem.write allowlist governs this, but it
  is not exercised against a hostile Agent in CI.
- **D3 non-GBK stderr** (TASK-0075 P4): subprocess output containing bytes that
  cannot decode as the Windows default (GBK). HostileAgentDriver should emit
  such bytes via the same subprocess path so the `encoding="utf-8",
  errors="replace"` fix in `git_ops.py` / `runtime.py` stays proven.
- **D4 retry past maxAttempts=1** (TASK-0075 P3): a second attempt starts
  despite `retryPolicy.maxAttempts: 1`. HostileAgentDriver returning a failing
  `WorkReport` exactly once must let the regression prove the node runs one
  attempt.
- **D5 None gate-selection at the wall** (TASK-0075 P2): the deterministic gate
  received `None` `selected_gate_refs` and crashed `len()`. HostileAgentDriver
  should be able to drive the run to the wall and hand back a None/empty
  selection so the null-safety fix in `verification.py` stays proven.

# Scope

- Implement `HostileAgentDriver` as an `AgentDriver` adapter under
  `src/ahra/adapters/` (e.g. `hostile_driver.py`). It is a **reference/test
  adapter**, not new domain infrastructure - it implements the same Port the
  real Codex driver does, per the non-negotiable "no domain code imports
  concrete cloud/model/Agent SDK" rule.
- Make it **scenario-driven**: a `HostileScenario` selects which action(s) to
  replay (D1..D5), constructed from config (a runtime/profile entry or a
  constructor arg), so one driver covers all observed defects and future ones
  without code changes.
- Register it in `AgentDriverRegistry` under a stable ref (e.g.
  `agent/hostile-replay@sha256:...`) following the same immutable-version
  convention as other adapters; do not make it a default-path driver.
- Add invariant regression tests that, for each scenario, prove the framework
  invariant still holds for free: main tree intact after D1, blacklisted write
  not propagated after D2, no `UnicodeDecodeError` after D3, exactly one
  attempt after D4, no `NoneType len()` after D5.
- Add a documented dogfood precondition: the paid dogfood may only be run after
  the HostileAgentDriver regression suite is green; this becomes the
  authoritative "framework invariants hold" gate, recorded in the handoff.

# Non-goals

- Do not run a paid real-Agent dogfood as part of this task; deterministic
  regression is the whole point. The paid re-run stays a separate step after
  this task is committed.
- Do not weaken capability admission, the write allowlist/blacklist, lease,
  timeout, isolation, or EvidenceGate boundaries; HostileAgentDriver replays
  hostile actions, it must not bypass the gates that catch them.
- Do not make HostileAgentDriver a default-path component; it is a
  test/reference adapter and must stay off the default operation surface.
- Do not invent a new Port; reuse `AgentDriver` and `AgentDriverRegistry`.
- Do not self-complete; EvidenceGate decides completion.

# Verification method

- `.\.venv\Scripts\python.exe -B -m unittest tests.test_hostile_agent_driver tests.test_development_worktree_isolation tests.test_verification tests.test_plan_execution tests.test_node_executor -v`
- `.\.venv\Scripts\python.exe -B scripts\check.py`
- `git diff --check`

# Required evidence and handoff

- Publish `evidence/hostile-agent-driver-report.md` describing the adapter, the
  scenario set (D1..D5), which prior-task invariant each scenario re-proves, and
  why the paid dogfood may now be treated as a pure capability test.
- Publish `evidence/verification-summary.json`.
- Publish `handoffs/HANDOFF-0001.md` whose single next action is: with the
  HostileAgentDriver invariant suite green, re-run the paid development-bounded
  dogfood in the isolated worktree to test real-Agent capability (not framework
  safety).
