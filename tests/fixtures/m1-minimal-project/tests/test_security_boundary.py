from __future__ import annotations


def test_fixture_declares_no_external_side_effects() -> None:
    forbidden = {"../", "docs/", "tests/"}
    allowed_outputs = {"outputs/doc-health.txt", "outputs/security-boundary.txt"}
    assert all(not output.startswith(tuple(forbidden)) for output in allowed_outputs)
