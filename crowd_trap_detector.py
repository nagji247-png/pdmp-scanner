"""Validated 30-minute and session open/close evidence for CROWD TRAP DETECTOR."""
from __future__ import annotations
import datetime as dt
import math

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
SESSION_CLOSE = dt.time(15, 30)


def _stamp(value):
    if isinstance(value, dt.datetime):
        stamp = value
    else:
        try:
            stamp = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if stamp.tzinfo is None:
        return None
    return stamp.astimezone(dt.timezone.utc)


def build_crowd_trap_snapshot(rows, now_utc=None):
    """Return only completed, valid 30m OHLC bars plus current session open/close."""
    now = now_utc or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)
    now = now.astimezone(dt.timezone.utc)
    bars = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        start = _stamp(row.get("time") or row.get("timestamp"))
        if start is None:
            continue
        end = start + dt.timedelta(minutes=30)
        if end > now:
            continue
        try:
            o, h, l, c = (float(row[k]) for k in ("open", "high", "low", "close"))
            volume = float(row.get("volume") or 0)
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if (not all(math.isfinite(x) for x in (o, h, l, c, volume))
                or min(o, h, l, c) <= 0 or volume < 0
                or h < max(o, c) or l > min(o, c) or h < l):
            continue
        pct = (c / o - 1) * 100
        direction = 1 if pct > 0.000001 else -1 if pct < -0.000001 else 0
        bars.append({
            "start": start.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "end": end.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "open": round(o, 4), "high": round(h, 4), "low": round(l, 4),
            "close": round(c, 4), "volume": round(volume, 2),
            "change_pct": round(pct, 4), "direction": direction,
        })
    bars.sort(key=lambda x: x["end"])
    if not bars:
        return None
    last = bars[-1]
    now_ist = now.astimezone(IST)
    today = now_ist.date().isoformat()
    todays = [b for b in bars if _stamp(b["start"]).astimezone(IST).date().isoformat() == today]
    session = None
    if todays:
        first, final = todays[0], todays[-1]
        move = (final["close"] / first["open"] - 1) * 100
        is_closed = (now_ist.time() >= SESSION_CLOSE
                     and _stamp(final["end"]).astimezone(IST).time() >= SESSION_CLOSE)
        session = {
            "market_date": today, "open": first["open"], "latest_close": final["close"],
            "change_pct": round(move, 4),
            "direction": 1 if move > 0.000001 else -1 if move < -0.000001 else 0,
            "status": "complete" if is_closed else "in_progress",
            "last_bar_end": final["end"], "source": "Yahoo Finance / verified broker OHLC",
        }
    return {
        "price": last["close"], "source": "Yahoo Finance / verified broker OHLC",
        "price_dir": last["direction"],
        "last_30m": last, "session_open_close": session,
        "completed_30m_bars": bars,
    }
