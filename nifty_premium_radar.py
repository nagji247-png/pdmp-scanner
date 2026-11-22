"""Broker-independent NIFTY spot reference levels from the last completed session."""
from __future__ import annotations

import math


def build_previous_session_levels(high, low, close, reference_close=None):
    """Return classic floor pivots and previous-session extremes.

    These are spot reference levels only, not option premiums or trade signals.
    Missing/invalid OHLC returns an empty list rather than fabricated levels.
    """
    try:
        high, low, close = float(high), float(low), float(close)
        if not all(math.isfinite(x) and x > 0 for x in (high, low, close)):
            return []
        if high < low or close < low or close > high:
            return []
        reference = float(reference_close if reference_close is not None else close)
        if not math.isfinite(reference) or reference <= 0:
            return []
    except (TypeError, ValueError, OverflowError):
        return []

    pivot = (high + low + close) / 3.0
    span = high - low
    raw = [
        ("पिछला High", "RESISTANCE", high),
        ("R2", "RESISTANCE", pivot + span),
        ("R1", "RESISTANCE", 2 * pivot - low),
        ("Pivot", "PIVOT", pivot),
        ("S1", "SUPPORT", 2 * pivot - high),
        ("S2", "SUPPORT", pivot - span),
        ("पिछला Low", "SUPPORT", low),
    ]
    result = []
    seen = set()
    for label, kind, value in sorted(raw, key=lambda item: item[2], reverse=True):
        level = round(value, 2)
        if level in seen:
            continue
        seen.add(level)
        result.append({
            "label": label,
            "type": kind,
            "level": level,
            "dist_pct": round((level / reference - 1) * 100, 2),
            "source": "पिछले पूरे सत्र का OHLC · Yahoo Finance दैनिक संदर्भ",
        })
    return result
