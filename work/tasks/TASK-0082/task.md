---
type: WorkItem
id: TASK-0082
schema_version: awkp/0.1
title: "Gate alignment-session-manager lifecycle promotion"
description: "Define and enforce the EvidenceGate-backed promotion path for component:alignment-session-manager, keeping it experimental until required gates pass."
context_id: "CTX-component-lifecycle"
priority: "P1"
risk_level: "R1"
requester: "human:maintainer"
reviewer: "agent:independent-verifier"
created_at: 2026-07-01T11:02:28.625623Z
depends_on: ["TASK-0079", "TASK-0080", "TASK-0081"]
input_refs: ["docs/policies/component-lifecycle.md", "docs/architecture/component-inventory.json", "docs/architecture/authority-map.md"]
output_contract:
  - kind: "ahra/artifact/doc-change/0.1"
  - kind: "ahra/evidence/review-report/0.1"
---

# Goal

Define and enforce the EvidenceGate-backed promotion path for component:alignment-session-manager, keeping it experimental until required gates pass.

# Acceptance criteria

- [ ] component:alignment-session-manager remains lifecycle_class experimental and default_visible false until prerequisite Workflow A CLI, dogfood path, and semantic review gate tasks pass EvidenceGate.
- [ ] Promotion criteria are explicit, EvidenceGate-verifiable, and mapped to component-lifecycle policy rather than asserted from implementation presence.
- [ ] Authority docs and component inventory are updated only to the lifecycle level proven by evidence, with no default-route claim before approval.
