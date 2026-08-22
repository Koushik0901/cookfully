from __future__ import annotations

from datetime import UTC, date, datetime, timedelta


def upcoming_week_start() -> date:
    today = datetime.now(UTC).date()
    return today + timedelta(days=7 - today.weekday())


def week_date(offset_days: int) -> str:
    return (upcoming_week_start() + timedelta(days=offset_days)).isoformat()
