---
type: Context
id: CTX-ahra-dynamic-kernel
schema_version: awkp/0.1
title: Migrate AHRA to an acceptance-first governed dynamic Agent kernel
description: Coordinates the architecture, verification, PlanIR, security, execution, dynamic planning, and repository consolidation work.
status: proposed
owner: human:maintainer
source_refs:
  - ../../AHRA-DYNAMIC-KERNEL-MASTER-PLAN.md
  - ../../architecture/decisions/ADR-0007-governed-dynamic-agent-kernel.md
success_criteria:
  - Goal input no longer requires a human-authored fixed task sequence.
  - Planner output is compiled and admitted before execution.
  - All Goal Claims require current Evidence at completion.
  - Local repairs trigger selective rather than unconditional full reverification.
  - Agent capability enforcement is default-deny and audited.
  - The default repository path contains no unwired or misleading core capability.
non_goals:
  - Framework self-iteration.
  - Production distributed workflow infrastructure.
  - Dashboard or visual workflow builder.
  - Unbounded recursive Agent spawning.
  - Automatic irreversible external actions.
created_at: 2026-06-25T00:00:00Z
---

# Human intent

Build the skeleton and governance that let Agents dynamically decide how to decompose and execute large, complex, changing goals while preserving strict file/document rules, capability permissions, audit, evidence and independent completion judgment.

# Execution policy

- Complete one task contract at a time.
- Do not start dynamic Planner integration until static PlanIR execution passes SG-2.
- Run the first end-to-end scenario against a fixture project, not AHRA itself.
- Keep old workflow code until SG-3 passes.
- Use Defect-driven local repair; do not restart the entire sequence for a local failure.
