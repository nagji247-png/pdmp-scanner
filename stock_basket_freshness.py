"""Shared exchange-session freshness rules for the diagnostic-only cash basket."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
EOD_READY_AFTER = dt.time(20, 0)


def load_exchange_calendar(path="exchange_calendar.json"):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def is_exchange_session(day, calendar=None):
    day = day if isinstance(day, dt.date) else dt.date.fromisoformat(str(day)[:10])
    calendar = calendar if isinstance(calendar, dict) else {}
    key = day.isoformat()
    special = calendar.get("special_sessions", {})
    if isinstance(special, dict) and key in special:
        return True
    holidays = calendar.get("holidays", [])
    holiday_dates = {
        str(item.get("date")) for item in holidays
        if isinstance(item, dict) and item.get("date")
    }
    return day.weekday() < 5 and key not in holiday_dates


def expected_latest_completed_session(scan_timestamp, calendar=None):
    """Latest EOD cash session expected to be available for this scan time.

    During a trading day, retain the prior session until 20:00 IST. After that
    cutoff, today's session is expected. Weekends and exchange holidays roll
    back to the latest valid session.
    """
    raw = str(scan_timestamp or "")
    try:
        stamp = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid scan timestamp for cash-basket freshness") from exc
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=dt.timezone.utc)
    local = stamp.astimezone(IST)
    day = local.date()
    if is_exchange_session(day, calendar) and local.time().replace(tzinfo=None) < EOD_READY_AFTER:
        day -= dt.timedelta(days=1)
    while not is_exchange_session(day, calendar):
        day -= dt.timedelta(days=1)
    return day.isoformat()


def exchange_sessions_in_window(end_day, calendar_days, calendar=None):
    if calendar_days < 1:
        raise ValueError("calendar_days must be positive")
    end_day = end_day if isinstance(end_day, dt.date) else dt.date.fromisoformat(str(end_day)[:10])
    first = end_day - dt.timedelta(days=calendar_days - 1)
    return [
        first + dt.timedelta(days=offset)
        for offset in range(calendar_days)
        if is_exchange_session(first + dt.timedelta(days=offset), calendar)
    ]
