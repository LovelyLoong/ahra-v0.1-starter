from __future__ import annotations

from datetime import date


def is_expired(review_after: date, today: date) -> bool:
    return review_after < today
