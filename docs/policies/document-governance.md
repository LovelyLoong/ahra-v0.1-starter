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

# Metadata Filtering

Future pattern, lesson, module, and anti-pattern documents must carry enough
metadata for an Agent to filter before semantic reading. At minimum:

- `doc_kind`: architecture, policy, pattern, lesson, module, runbook, or
  anti_pattern;
- `authority`: active, proposed, experimental, archived, or superseded;
- `scope`: project, workflow, module, task_family, or task_local;
- `applies_to`: task types, risk levels, modules, or file areas;
- `evidence_refs`: task ids, run ids, gate reports, or verifier reports;
- `failure_modes`: known ways this guidance can mislead;
- `review_after`: freshness boundary.

Agents must prefer active, in-scope, fresh documents with evidence references.
Archived, superseded, task-local, or stale documents may explain history but
must not override active authority.

# Skill And Docs Boundary

Skills describe operating methods. Docs record durable project truth. A Skill
may reference docs, module manifests, and lessons, but it must not become the
only authority for project facts.

Skill changes that alter workflow behavior are treated as proposed operating
method changes. They require evidence that the new behavior improves outcomes
without weakening protected rules.

A Skill distilled from a successful dynamic workflow is a reusable operating
method, not proof that the same method applies everywhere. It must carry
applicability, non-applicability, protected-boundary notes, and evidence refs
from the completed run that produced it.
