# ADR-0008: Command gate verification engine

- Status: accepted
- Date: 2026-06-29
- Decision owner: human:maintainer

## Context

AHRA has a governed dynamic Agent kernel with Goal, Claim, GateDefinition,
PlanIR, Evidence v2, Defect, selective reverification, and AWKP EvidenceGate
boundaries. The current deterministic gate path is useful for fixtures and CI
baselines, but it cannot be the long-term default verification engine for real
project work because real verification must execute the exact command declared
by the GateDefinition and judge the command result against a recorded
expectation.

The GateDefinition schema already allowed an optional command array. Before
this decision, the domain object did not parse that command and the contract had
no explicit expectation for exit code or output matching.

## Decision

The command gate is the default verification engine for AHRA kernel
verification. A command-gate GateDefinition records:

1. the exact command vector to execute; and
2. the expectation used to judge the result, starting with `expectedExitCode`
   and an optional single `outputMatch` rule.

`DeterministicGateRunner` remains a fixture and CI baseline. It can exercise
contract and scheduler behavior, provide stable local regression evidence, and
support examples, but it is not the default engine for real project verification
semantics.

AWKP EvidenceGate remains the evidence-lineage reviewer for task completion. It
reviews task evidence, manifests, command summaries, verifier reports, and
producer independence. It does not replace the command gate and it does not run
producer verification commands as a hidden implementation step.

## Consequences

- GateDefinition is the contract source for command-gate execution intent.
- GateExecutionRequest and GateExecutionResult should carry the command and
  execution outcome without inventing a second verification contract.
- TASK-0053 must implement a CommandGateRunner against this contract instead of
  extending DeterministicGateRunner into a real verification engine.
- Existing deterministic fixture records remain valid because the new
  expectation field is optional in `ahra.dev/v1alpha1`.
- Completion authority remains separate: command gates produce evidence, while
  AWKP EvidenceGate decides whether a task may move from `review` to
  `completed`.

## Rejected alternatives

### Keep DeterministicGateRunner as the default engine

Rejected. That would keep real project verification dependent on fixture
semantics and would not bind a GateDefinition to an executable command result.

### Let AWKP EvidenceGate execute verification commands

Rejected. EvidenceGate is the final reviewer of published evidence and task
lineage. Making it execute producer commands would merge verifier authority with
execution and blur the current task completion boundary.

### Add an open-ended expectation expression language now

Rejected. A broad assertion language is not needed for the first command-gate
contract. `expectedExitCode` plus one optional output containment rule is enough
to give TASK-0053 executable teeth without expanding the trusted surface.
