from __future__ import annotations

from datetime import date

from src.doc_health import is_expired


def test_expired_document_is_detected() -> None:
    assert is_expired(date(2026, 1, 1), date(2026, 6, 26))


def test_current_document_is_not_reported() -> None:
    assert not is_expired(date(2026, 9, 1), date(2026, 6, 26))
