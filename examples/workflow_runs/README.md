# Workflow Run Examples

This directory separates schema/test fixtures from runnable local examples.

- `fixtures/` uses `driverRef: fake-reference`. These files are for schema,
  loader, and CLI smoke tests. They are not the default operation entrypoint.
- `runnable/` uses driver refs that can be available in a real local
  environment. If the named driver dependency is missing, the CLI must fail
  closed rather than silently falling back.

