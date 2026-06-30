---
type: WorkItem
id: TASK-0066
schema_version: awkp/0.1
title: Governed network.access admission gate
description: Make network.access an explicitly admitted, audited side effect instead of unconditionally denied, so Goals requiring network can be governed rather than rejected, while denial still applies when no grant is present.
context_id: CTX-phase1-intent-closure
priority: P1
risk_level: R3
requester: human:maintainer
reviewer: agent:independent-verifier
created_at: 2026-06-30T10:00:00Z
depends_on: [TASK-0065]
input_refs:
  - ../../../src/ahra/capabilities.py
  - ../../../src/ahra/goal_operations.py
  - ../../../docs/roadmaps/phase1-minimal-loop-intent-roadmap.md
output_contract:
  - kind: network_admission_gate_report
  - kind: verification_summary
  - kind: handoff
---

# Goal

Remove the unconditional network.access denial. Implement a governed admission
path so each network use is an explicitly admitted, audited side effect with
evidence. Network becomes a granted capability, not a banned one, but denial
still applies when no grant is present (default-deny holds).

# Scope

- Modify `src/ahra/capabilities.py` to support network.access as an admittable
  capability (currently in HIGH_RISK_ACTIONS but not in SUPPORTED_LOCAL_ACTIONS).
- Implement audit trail for network grants: actor, timestamp, resource scope.
- Keep default-deny: network.access with no grant is rejected.
- Add evidence capture for network operations (request/response summary, not
  full payloads for privacy).

# Non-goals

- Do not implement actual network execution here (use RuntimeProvider or
  existing mechanisms).
- Do not weaken the default-deny boundary.
- Do not self-complete this task; EvidenceGate decides completion.

# Acceptance criteria

- [ ] network.access is no longer unconditionally denied; it can be admitted
  with an explicit grant, covered by a test.
- [ ] Every network use is audited (actor, timestamp, resource scope) and the
  audit is append-only, covered by a test.
- [ ] An attempt to use network.access without a grant is rejected (default-deny
  holds), covered by a test.
- [ ] Network operation evidence is captured (summary, not full payloads),
  covered by a test.
- [ ] The domain module imports no adapter/model/cloud dependency (lint passes).
- [ ] Unit tests, lint, and diff checks pass: `.\.venv\Scripts\python.exe -B -m
  unittest tests.test_capabilities -v` and `.\.venv\Scripts\python.exe -B
  scripts\check.py --lint` green.
- [ ] Producer moves TASK-0066 only to review; EvidenceGate decides completion.

# Verification method

- .\.venv\Scripts\python.exe -B -m unittest tests.test_capabilities -v
- .\.venv\Scripts\python.exe -B scripts\check.py --lint
- git diff --check

# Required evidence and handoff

- Publish `evidence/network-admission-gate-report.md` describing the admission
  path, the audit trail, and the default-deny test.
- Publish `evidence/verification-summary.json`.
- Publish `handoffs/HANDOFF-0001.md` with one exact next action for TASK-0067.
