---
type: Architecture
id: ARCH-framework-entrypoints
schema_version: awkp/0.1
title: Framework entrypoints
description: Defines the current default way humans and agents operate this Agent workflow foundation.
status: active
owner: team:platform
source_refs:
  - ../../AGENTS.md
  - ../../README.md
  - ../../skills/ahra-workflow-runner/SKILL.md
  - ../../docs/architecture/agent-drivers-and-workflow-invocation.md
  - ../../docs/architecture/reference-runtime-adapters-and-mcp.md
evidence_refs: []
confidence: reviewed
last_verified_at: 2026-06-23T14:32:49+08:00
review_after: 2026-09-23T00:00:00Z
tags: [architecture, entrypoint, cli, skill]
---

# Summary

The default foundation entrypoint is **CLI plus local Skill plus repository
documentation**.

An agent should first read `AGENTS.md`, load the relevant local Skill, inspect
the referenced task or request, and then run documented local commands. The
foundation must remain usable without an MCP server.

- Skill tells an agent which command to run and what evidence to inspect.
- CLI wraps the same Python APIs that currently back the reference runner,
  EvidenceGate, task inspection, and local checks.
- Documentation remains the human-readable authority for boundaries,
  sequencing, and non-goals.

# Current Operation Surface

The current reliable operation surface is:

- `uv run ahra workflow validate <request.yaml>`
- `uv run ahra workflow start <request.yaml>`
- `uv run ahra workflow inspect <artifact-dir>`
- `uv run ahra workflow resume <resume-request.yaml>`
- `uv run ahra task inspect <TASK-ID>`
- `uv run ahra evidence-gate evaluate <TASK-ID> --expected-version <N> --report <report.json> --actor <verifier>`
- `uv run ahra doctor`
- `uv run python -B scripts/check.py`
- `uv run python -B scripts/check.py --lint`
- `uv run python -B scripts/check.py --test`
- `uv run python -B scripts/lint_awkp.py`
- `uv run python -B -m ahra.demo`
- `git diff --check`
- direct Python calls to the reference runner APIs from tests or adapters.

# CLI Boundary

The CLI wrapper is intentionally narrow and must not invent workflow logic. It
exposes existing operations:

- `ahra workflow validate`
- `ahra workflow start`
- `ahra workflow inspect`
- `ahra workflow resume`
- `ahra task inspect`
- `ahra evidence-gate evaluate`
- `ahra doctor`

Every CLI command must call the same underlying Python service used by tests.
The CLI must fail closed on unknown modules, unknown drivers, stale
`expected_version`, invalid plan digests, missing manifests, and missing local
evidence.

# MCP Position

MCP is not part of the current default starter route.

The existing MCP code path is a legacy or optional adapter surface. It must not
be required to operate the framework, and new tasks should not add MCP-only
capabilities. A later implementation task may remove, quarantine, or explicitly
freeze the MCP code.

This avoids making a framework template depend on an agent-client integration
protocol before the framework's local operation contract is stable.

# Example Policy

Examples must distinguish two uses:

- Test fixtures may use `driverRef: fake-reference` and in-process fake
  drivers. The CLI only registers this driver when called with
  `--enable-fixture-driver`.
- Runnable examples must name a driver that is actually available in the local
  environment, or clearly state the setup command required before execution.

An example that validates as a schema fixture must not imply it is a runnable
default entrypoint.

# Local Isolation Boundary

For the starter's local profile, run-owned Git worktree isolation is sufficient
as the default boundary.

This protects the source worktree from direct mutation by workflow modules. It
does not claim process, network, host, or secret isolation. Stronger runtime
sandboxing remains a future adapter behind existing ports and should not block
the local template route.
