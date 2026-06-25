# Acceptance Contract Compatibility

- `apiVersion: ahra.dev/v1alpha1` is the only accepted major version for GoalContract, ClaimGraph, GateDefinition, and GatePlan in this release.
- Compatible additions must use `x-*` extension fields or new optional fields in a later v1alpha profile.
- Unknown major versions must fail closed.
- Stable object IDs are part of the contract surface; malformed IDs fail schema validation.
- Extensions may add metadata, but they may not weaken required security or governance Claim fields.
- Breaking field meaning changes require a new major schema path and migration notes.
