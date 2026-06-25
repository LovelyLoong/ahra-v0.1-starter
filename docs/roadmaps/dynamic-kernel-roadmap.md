---
type: Roadmap
id: ROADMAP-dynamic-agent-kernel
schema_version: awkp/0.1
title: Dynamic Agent kernel implementation roadmap
description: Orders implementation so verification and static execution become reliable before model-driven dynamic planning.
status: active
owner: human:maintainer
source_refs:
  - ../../AHRA_dynamic_kernel_master_plan_2026-06-25.md
  - ../../work/proposed/TASK-SEQUENCE.md
evidence_refs: []
confidence: reviewed
last_verified_at: 2026-06-25T00:00:00Z
review_after: 2026-09-25T00:00:00Z
tags: [roadmap, implementation]
---

# Non-negotiable order

```text
Repository truth
  -> Acceptance contracts
  -> Evidence validity
  -> Selective verification
  -> PlanIR compiler
  -> Capability admission
  -> Execution primitive
  -> Static DAG scheduler
  -> Planner adapter
  -> Dynamic repair loop
  -> Legacy cleanup
```

# Stage Gates

## SG-0: Truth and authority

After `TASK-0022`:

- baseline checks and drift are recorded;
- active backlog is reconciled;
- one active architecture authority exists;
- every component has a provisional lifecycle class.

## SG-1: Verification foundation

After `TASK-0025`:

- a Goal can be represented as Claims;
- Gate runs create fingerprinted Evidence;
- changed inputs make Evidence stale;
- a Defect causes deterministic selective reverification;
- Completion rejects stale or uncovered Claims.

## SG-2: Trusted static execution

After `TASK-0029`:

- a hand-authored PlanIR runs end-to-end;
- capability violations are denied;
- NodeRun state, checkpoint, artifact and evidence are consistent;
- no Planner is needed to prove the control plane.

## SG-3: Dynamic closed loop

After `TASK-0031`:

- Planner creates PlanDraft only;
- PlanCompiler/Admission produces PlanIR;
- Defect drives bounded repair;
- selective reverification demonstrably runs fewer Gates than full verification;
- all Goal Claims are logically covered at completion.

## SG-4: Consolidated repository

After `TASK-0032`:

- default CLI/docs/Skill expose only the new path;
- legacy paths are isolated or removed;
- no unclassified default components remain;
- historical audit is preserved.

# Stop conditions

Stop the sequence and escalate when:

- a Stage Gate cannot be satisfied without changing the approved architecture;
- acceptance criteria require weakening;
- a Core security boundary exists only in Prompt/docs and cannot be enforced;
- state authorities conflict without a reconciler;
- the same Defect recurs after the configured repair limit;
- baseline tests are nondeterministic enough to invalidate Evidence reuse.
