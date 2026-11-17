"""Build complete, date-labelled Market Activity quotes from the official NSE CM EOD archive."""
from __future__ import annotations

import datetime as dt
import math

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def _positive(value):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def build_nse_eod_market_activity_quotes(archive, expected_symbols, now=None, max_age_days=7):
    """Return exact-symbol EQ quotes from the newest valid NSE CM archive session.

    These are explicitly tagged EOD, never represented as live/intraday quotes.
    """
    expected = {str(symbol).strip().upper() for symbol in expected_symbols}
    current = now or dt.datetime.now(IST)
    current = current.replace(tzinfo=IST) if current.tzinfo is None else current.astimezone(IST)
    records = archive.get("records", []) if isinstance(archive, dict) else []
    candidates = []
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("equity_rows"), list):
            continue
        try:
            day = dt.date.fromisoformat(str(record.get("date", ""))[:10])
        except ValueError:
            continue
        age = (current.date() - day).days
        if 0 <= age <= max_age_days:
            candidates.append((day, record))
    if not candidates:
        return {
            "source": "NSE India official CM-UDiFF Common Bhavcopy Final · EOD",
            "source_timestamp": None,
            "coverage": {"expected": len(expected), "matched": 0, "live_matched": 0, "eod_matched": 0},
            "instruments": {},
        }

    day, record = max(candidates, key=lambda item: item[0])
    instruments = {}
    for row in record["equity_rows"]:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").strip().upper()
        if symbol not in expected or str(row.get("series") or "").upper() != "EQ":
            continue
        close = _positive(row.get("close"))
        previous = _positive(row.get("previous_close"))
        if close is None or previous is None:
            continue
        volume = row.get("volume")
        try:
            volume = int(volume) if volume is not None and int(volume) >= 0 else None
        except (TypeError, ValueError, OverflowError):
            volume = None
        instruments[symbol] = {
            "type": "stock",
            "quote_kind": "eod",
            "price": round(close, 2),
            "change_pct": round((close / previous - 1) * 100, 2),
            "volume": volume,
            "price_as_of": day.strftime("%d/%m/%Y"),
            "price_time": "EOD Close",
            "price_source": "NSE India official CM-UDiFF Common Bhavcopy Final",
            "volume_as_of": day.strftime("%d/%m/%Y"),
            "volume_source": "NSE India official CM-UDiFF Common Bhavcopy Final",
        }
    stamp = dt.datetime.combine(day, dt.time(15, 30), tzinfo=IST)
    return {
        "source": "NSE India official CM-UDiFF Common Bhavcopy Final · EOD",
        "source_timestamp": stamp.strftime("%d-%b-%Y %H:%M:%S"),
        "coverage": {
            "expected": len(expected),
            "matched": len(instruments),
            "live_matched": 0,
            "eod_matched": len(instruments),
        },
        "instruments": instruments,
    }
