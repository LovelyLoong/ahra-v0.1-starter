---
type: Policy
id: POLICY-component-lifecycle
schema_version: awkp/0.1
title: Component lifecycle policy
description: Prevents unwired, unowned, untested, or misleading capabilities from remaining in AHRA's default core.
status: active
owner: team:platform
source_refs:
  - ../architecture/repository-consolidation.md
evidence_refs: []
confidence: reviewed
last_verified_at: 2026-06-25T00:00:00Z
review_after: 2026-09-25T00:00:00Z
tags: [policy, repository, lifecycle]
---

# Mandatory classification

Every top-level package, CLI command, Skill, protocol adapter, contract family and active architecture document must be classified as `core`, `adapter`, `experimental`, `legacy`, `removal_candidate`, or `archived`.

# Default path requirements

A default-visible capability must have:

- one authoritative description;
- an executable entrypoint;
- at least one non-fixture consumer or an explicit fixture-only label;
- contract and failure tests;
- owner and review date;
- security and side-effect classification;
- Artifact/Evidence behavior where applicable.

# Prohibitions

- Do not leave an optional protocol in default packaging after docs deprecate it.
- Do not claim a Port is implemented merely because a Protocol class exists.
- Do not keep demo-only services under the same namespace as the authoritative path without labeling.
- Do not keep two independent stores for the same state without an explicit projection/reconciliation contract.
- Do not add a new feature until its consumer and lifecycle class are known.
- Do not silently delete historical decisions or events.

# Experimental increments

An experimental component may receive usability or admission-hardening
increments only when the changed entrypoint remains explicitly invoked and
`default_visible` remains false in the component inventory. Adding a status
surface, human briefing artifact, or stricter admission check to an
experimental entrypoint is not component promotion unless a separate
EvidenceGate-approved lifecycle task changes the lifecycle classification.

# Review cadence

The component inventory is checked at every architecture Stage Gate and before release. `legacy` entries require a removal trigger/date. `experimental` entries require an owner and explicit non-default status. `removal_candidate` entries cannot receive new features.
