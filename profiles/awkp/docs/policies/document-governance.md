---
type: Policy
id: POLICY-document-governance
schema_version: awkp/0.1
title: Document governance
description: Defines authority, provenance, freshness, and review rules for project knowledge.
status: active
owner: team:platform
source_refs: [SPEC.md]
evidence_refs: []
confidence: reviewed
last_verified_at: 2026-06-21T00:00:00Z
review_after: 2026-09-21T00:00:00Z
tags: [documentation, governance]
---

# Summary

Each fact class has one authority. Machine state is structured; durable knowledge is reviewed Markdown; artifacts and evidence are immutable and traceable.

# Rules

- One concept per file; link instead of copying rules.
- Active concepts require an owner and review date.
- Critical claims require source or evidence references.
- Supersede rather than silently erase historical decisions.
- Policy changes require human or CODEOWNER approval.
