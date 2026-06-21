---
name: doc-gardening
description: Audits AWKP/OKF-style project documentation for stale reviews, broken links, duplicate IDs, missing provenance, and drift. Use for scheduled documentation maintenance or before major releases.
compatibility: Requires Python 3 and git; network access is optional.
metadata:
  profile: awkp/0.1
---

# Procedure

1. Run `python3 scripts/lint_awkp.py`.
2. Compare active documents with code, schemas, APIs, and recent accepted tasks.
3. Classify findings as deterministic fixes, uncertain drift, duplication, or missing ownership.
4. Open a focused PR. Do not silently mutate protected policy or accepted decisions.
5. Mark uncertain claims for human review and preserve superseded history.

# Output

Publish a report listing files, finding type, evidence, proposed action, owner, and severity.
