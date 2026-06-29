---
type: Roadmap
id: ROADMAP-development-program
schema_version: awkp/0.1
title: Development program overview
description: The full end-to-end development chain from verification teeth through workflow autonomy, intent closure, and the deferred self-iteration - a single map every agent and the maintainer can read to see the whole plan.
status: proposed
owner: human:maintainer
source_refs:
  - ./phase1-minimal-loop-intent-roadmap.md
  - ./dynamic-kernel-m1-roadmap.md
  - ../../work/index.md
evidence_refs: []
confidence: draft
last_verified_at: 2026-06-29T00:00:00Z
review_after: 2026-09-29T00:00:00Z
tags: [roadmap, program, overview, autonomy, intent]
---

# Purpose

One readable map of the whole forward plan, so any agent or the maintainer can
see where the current task sits in the larger chain. Task-level acceptance
contracts live in each `work/tasks/TASK-XXXX/task.md`; stage detail lives in the
per-increment roadmaps. This document only orders the increments and states the
through-line.

# The through-line

The goal is a complete, governed, closed loop that can be driven from an
abstract human intent and that can ultimately help optimize this project itself
(dogfooding). The chain builds that loop from the inside out, and every step
keeps the non-negotiable rule that an Agent cannot self-declare completion -
EvidenceGate plus a distinct verifier always decides.

```text
[A] Verification teeth   -> the gate can actually fail honestly
[B] Workflow autonomy    -> work flows ready->completed without manual handoff
[C] Intent closure (P1)  -> an abstract Goal becomes a frozen GoalExecutionRequest
[D] Governance depth (P2/P3) -> Goal and AWKP become one governed surface
[E] Self-iteration (P4)  -> deferred; memory-driven strategy synthesis, last
```

# Increment A - Verification teeth (TASK-0052..0056)

Make completion honest before anything is built on top of it.

- 0052 GateDefinition command-gate contract + ADR.
- 0053 CommandGateRunner kernel engine.
- 0054 Derive completion from real gate evidence.
- 0055 AWKP EvidenceGate reviews kernel evidence lineage.
- 0056 Demonstrate a real failing gate end-to-end.

Owner roadmap: this program doc plus each task.md. This is the foundation; it is
hand-driven because you cannot use a toothless workflow to give itself teeth.

# Increment B - Workflow autonomy (TASK-0057..0061)

Remove the manual "stall": the default path has no autonomous orchestration
layer today (no governed command for create/claim/review; producer-to-verifier
handoff is manual; Goal and AWKP worlds are disconnected).

- 0057 Governed CAS writer for ready->working / working->review /
  changes_requested->working.
- 0058 `ahra task create` + `ahra task claim`.
- 0059 Producer-to-verifier orchestrator (preserves producer != verifier).
- 0060 Goal-to-AWKP bridge (kernel evidence feeds the AWKP gate).
- 0061 Demonstrate autonomous end-to-end completion of one simple real task.

After B, later tasks - including Phase 1 itself - can be executed
semi-autonomously by the workflow.

# Increment C - Intent closure, Phase 1 (after TASK-0061)

Close the input boundary: an Agent-assisted alignment workflow turns an abstract
human Goal into a frozen, authorized GoalExecutionRequest, plus the governed
network and subjective-judgment gates that let arbitrary-direction Goals
actually execute and be verified.

Owner roadmap: [Phase 1 minimal-loop intent-closure roadmap](phase1-minimal-loop-intent-roadmap.md),
stages SG-P1-A..G. Binding rule recorded there: every Phase 1 development task is
command-gate-decidable and therefore autonomously executable by Increment B's
workflow, while the human authorization gate is a feature of the deliverable,
not a manual build step.

# Increment D - Governance depth, Phase 2 / Phase 3 (sketch)

- Phase 2: deepen the Goal-to-AWKP bridge so the two are fully one surface.
- Phase 3: harden the authorization gate and govern the
  work/proposed -> work/tasks promotion.

# Increment E - Self-iteration, Phase 4 (deferred, last)

Memory-driven strategy synthesis: summarize each work session into reusable,
promotable strategy context. This is the project-roadmap's long-deferred
non-goal. It is scheduled last and only on top of A-D, because autonomous
strategy generation must sit above a real authorization gate.

# Status pointer

Live task states are authoritative in `work/tasks/*/state.json` and summarized
in [the work index](../../work/index.md). As of this writing: Increment A is in
progress (0052-0053 completed, 0054 working), Increments B-E are planned with
skeletons created for B (0057-0061) and a roadmap for C.

# Sequencing rule

Do not start an increment before its predecessor's demonstration task is
EvidenceGate-approved: B depends on A's teeth (0056), C depends on B's
autonomous completion (0061), D depends on C, E depends on D. Skipping an
increment reintroduces a hollow gate, a manual stall, or an ungoverned
authorization path.
