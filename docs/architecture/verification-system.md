---
type: Architecture
id: ARCH-verification-system-v2
schema_version: awkp/0.1
title: Verification system v2
description: Defines acceptance claims, layered gates, evidence validity, invalidation, defects, and selective reverification.
status: active
owner: team:quality
source_refs:
  - ../../AHRA_dynamic_kernel_master_plan_2026-06-25.md
  - evidence-gate.md
evidence_refs: []
confidence: reviewed
last_verified_at: 2026-06-25T00:00:00Z
review_after: 2026-09-25T00:00:00Z
tags: [verification, evidence, testing, defects]
---

# Principle

**验收逻辑全量，验证执行增量。**

Completion Gate must inspect every Goal Claim. It may reuse an Evidence record only when all inputs bound into the evidence fingerprint remain current.

# Terminology

- **Criterion**：人类 Goal Contract 中的成功标准。
- **Claim**：可独立判断真假的规范化陈述。
- **GateDefinition**：产生某种 Evidence 的版本化方法。
- **GateRun**：一次实际验证尝试。
- **Evidence**：GateRun 对 Claim/Subject 的不可变结论。
- **VerificationSelection**：本轮必须运行的最小保守 Gate 集。
- **DefectRecord**：失败的 Claim、复现、影响和修复边界。

# Claim Graph requirements

A valid graph must satisfy:

1. Every Goal criterion maps to at least one Claim.
2. Every Claim has at least one registered Gate or a declared human-approval requirement.
3. Dependencies form an acyclic graph.
4. Security and governance Claims cannot be silently marked optional.
5. A derived Claim records its parent criterion and dependency Claims.
6. The graph records uncovered, ambiguous and conflicting Claims; admission fails while any required item remains.

Example:

```yaml
apiVersion: ahra.dev/v1alpha1
kind: ClaimGraph
metadata:
  goalId: GOAL-doc-staleness
  version: 1
spec:
  claims:
    - id: CLAIM-cli-detects-stale-docs
      type: functional
      statement: The CLI exits non-zero when an active document is past review_after.
      criterionRefs: [CRIT-1]
      dependsOn: [CLAIM-frontmatter-parses]
      riskLevel: R1
      requiredEvidenceKinds: [deterministic_test, semantic_review]
      gateRefs: [GATE-doc-staleness-unit, GATE-cli-contract-review]
```

# Gate levels

## L0 Node Gate

Fast, local and usually deterministic. It runs after a node and before dependants consume its output.

Default examples:

- output JSON Schema validation;
- changed-path and line-size policy;
- import/type/unit test for directly changed component;
- Artifact hash and manifest check;
- capability/audit consistency;
- no dirty workspace caused by verification.

Target characteristics:

- seconds to a few minutes;
- small context;
- deterministic where possible;
- no full repository scan unless the node changes shared foundations.

## L1 Integration Gate

Runs at merge boundaries and public contract changes. It validates interactions rather than each isolated file.

Examples:

- CLI → service → store path;
- schema producer/consumer compatibility;
- planner output → compiler → scheduler path;
- policy decision → runtime enforcement;
- two parallel node outputs merged into one artifact.

## L2 Goal Gate

Evaluates all Claims and current Evidence. It includes required end-to-end, recovery, security and governance scenarios. The L2 selector may reuse current Evidence but cannot reuse stale, expired, contradicted or revoked Evidence.

# Evidence v2 shape

```yaml
apiVersion: ahra.dev/v1alpha1
kind: Evidence
metadata:
  evidenceId: EVD-01...
  createdAt: 2026-06-25T00:00:00Z
spec:
  claimRefs: [CLAIM-cli-detects-stale-docs]
  gateRef: GATE-doc-staleness-unit@sha256:...
  gateRunId: GATERUN-01...
  result: passed
  confidence: verified
  subjects:
    - ref: ART-cli-module
      digest: sha256:...
  dependencies:
    - ref: ART-document-schema
      digest: sha256:...
  environment:
    runtimeProfileDigest: sha256:...
    policyDigest: sha256:...
    verifierReleaseDigest: sha256:...
    testDefinitionDigest: sha256:...
  validity:
    state: current
    validUntil: null
  refs: [ART-test-log, AUD-tool-trace]
```

# Current Evidence set

Evidence history is append-only. A new Evidence record may supersede one or
more older Evidence records by listing their `evidenceId` values in
`spec.supersedes`; the older records remain auditable and are not rewritten.

The EvidenceRegistry resolves a deterministic current set before Completion or
selective reverification:

1. Validate the supersession graph.
2. Reject self-supersession, unknown supersedes refs, cycles and competing
   unsuperseded leaves for the same Claim/Gate/subject set.
3. Treat unsuperseded leaves as the current Evidence set.
4. Treat superseded records as historical excluded Evidence.
5. Let only current leaves with `result: passed`, valid fingerprints and
   `validity.state: current` satisfy Claims.

A stale, revoked, expired or contradicted current leaf leaves the Claim
uncovered. It must not reactivate an older superseded record.

# Invalidation triggers

Evidence becomes stale when any bound item changes:

- subject digest;
- dependency digest;
- GateDefinition or test digest;
- Policy or Runtime profile affecting semantics;
- verifier release when a policy requires release-sensitive verification;
- declared environment input;
- Claim statement or dependency;
- contradiction from stronger/newer Evidence;
- TTL expiry.

A documentation-only change may avoid code tests only when the dependency graph proves no code, schema, policy, command, prompt or test definition changed.

# Selection algorithm

```text
INPUT:
  changed subjects
  failed gates
  changed claims/policies/gates
  current evidence registry

1. direct_claims := claims referencing changed subjects
2. affected_claims := reverse_dependency_closure(direct_claims)
3. current_set := EvidenceRegistry.resolve_current_set()
4. stale_evidence := current leaves bound to affected claims or changed fingerprints
5. historical_excluded := superseded Evidence retained for audit
6. selected_gates := gates required by affected_claims
7. selected_gates += failed_gates
8. selected_gates += mandatory safety baseline for changed risk classes
9. selected_gates += integration gates crossing changed/unchanged boundary
10. minimize only when coverage and policy remain satisfied
11. emit deterministic VerificationSelection with reused current Evidence,
    stale current Evidence and historical excluded Evidence separated
```

Selection is auditable. An Agent suggestion may be an input, but the final selection is computed by trusted code.

# Defect lifecycle

```text
open -> triaged -> repair_planned -> repairing -> reverifying -> resolved
  └----------------------------------------------------------> escalated
  └----------------------------------------------------------> rejected
```

A Defect may only be resolved when its failed Claims have new current Evidence and no dependent Claim remains contradicted.

A Defect records:

- `directClaimRefs`: the Claim or Claims directly failed by the Gate result;
- `affectedClaimRefs`: deterministic reverse dependency closure from the direct
  Claims, or an independently validated equivalent with trace.

Repair and selective reverification use affected Claims; reproduction and root
failure analysis use direct Claims.

# Completion rule

A Goal is complete only when:

- every required Claim is covered;
- every required Claim has at least one sufficient Evidence record in the
  EvidenceRegistry current set;
- no open blocking Defect exists;
- mandatory security/governance Claims pass;
- required approvals are valid and unexpired;
- all Evidence subjects match the final accepted Artifact digests;
- the verifier is independent under the configured policy.

Completion must receive the append-only Evidence history. It must not require a
caller to delete failed or stale historical Evidence before evaluation.

# Cost controls

- Cache deterministic Gate outputs by full fingerprint.
- Reuse Evidence only by digest, never by mutable path or “last run”.
- Keep L0 prompts minimal; prefer host checks.
- Invoke semantic Reviewer only for semantic Claims or risk boundaries.
- Supply Reviewer with Claim subset and relevant diff, not full conversation history.
- Limit failed-Gate correction cycles; repeated identical Defect escalates.
