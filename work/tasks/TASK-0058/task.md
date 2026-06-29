---
type: WorkItem
id: TASK-0058
schema_version: awkp/0.1
title: Add governed task create and claim CLI commands
description: Provide ahra task create (generate a compliant AWKP task skeleton from a template) and ahra task claim (ready to working), so the producer no longer hand-authors task directories.
context_id: CTX-workflow-autonomy
priority: P1
risk_level: R1
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-29T11:00:00Z
depends_on: [TASK-0057]
input_refs:
  - ../../../src/ahra/cli.py
  - ../../../src/ahra/evidence_gate.py
  - ../../../scripts/lint_awkp.py
  - ../../../work/tasks/TASK-0051/task.md
output_contract:
  - kind: task_create_claim_report
  - kind: verification_summary
  - kind: handoff
---

# Goal

Stop hand-authoring task directories. Expose governed CLI commands that create a
lint-clean AWKP task skeleton and claim it, using the CAS writer from TASK-0057.
This is the command form of the manual scaffolding currently done by hand.

# Scope

- `ahra task create`: generate a compliant `work/tasks/TASK-XXXX/` skeleton
  (task.md frontmatter + Acceptance criteria section, state.json at version 0
  ready, seeded `task_created` event, empty artifact/evidence manifests,
  handoffs/ and evidence/ directories) that passes `scripts/lint_awkp.py`.
- `ahra task claim`: perform `ready -> working` via the TASK-0057 governed CAS
  writer (lease + fencing).
- Validate inputs (id format, required acceptance criteria) and fail closed on
  malformed input.

# Non-goals

- Do not build the producer/verifier orchestrator here (that is TASK-0059).
- Do not auto-generate acceptance criteria content (that is the human/producer's
  contract; the command scaffolds structure only).
- Do not weaken EvidenceGate or the CAS writer guarantees.
- Do not self-complete this task; EvidenceGate decides completion.

# Acceptance criteria

- [ ] `ahra task create` produces a task directory that passes
  `scripts/lint_awkp.py` with zero errors, covered by a test.
- [ ] The generated skeleton includes task.md (frontmatter + a parseable
  `# Acceptance criteria` section), state.json (ready, version 0), a seeded
  `task_created` event, empty artifact and evidence manifests, and handoffs/ and
  evidence/ directories.
- [ ] `ahra task claim` moves a ready task to working through the TASK-0057
  governed CAS writer, recording a lease and fencing token, covered by a test.
- [ ] Malformed input (bad id, missing acceptance criteria) is rejected with a
  clear error (fail closed), covered by a test.
- [ ] The new commands appear in the default CLI help without exposing any
  default-excluded legacy token (lint_contracts default-exposure check passes).
- [ ] Targeted tests, lint, and diff checks pass, or any failure is recorded as
  a blocker with exact command output.
- [ ] Producer moves TASK-0058 only to review; EvidenceGate decides completion.

# Verification method

- .\.venv\Scripts\python.exe -B -m unittest tests.test_cli -v
- .\.venv\Scripts\python.exe -B scripts\check.py --lint
- .\.venv\Scripts\python.exe -B scripts\lint_awkp.py
- git diff --check

# Required evidence and handoff

- Publish `evidence/task-create-claim-report.md` describing the commands, the
  generated skeleton shape, and the fail-closed input validation.
- Publish `evidence/verification-summary.json`.
- Publish `handoffs/HANDOFF-0001.md` with one exact next action for TASK-0059.
