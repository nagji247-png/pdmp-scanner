"""Offline, no-lookahead forward test for MCX GOLD/SILVER FUTCOM price-OI regimes.

This is a research diagnostic only. It does not create a trading signal or
enable any MCX component in an asset Final Score.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import date
import math


def _positive_number(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _nonnegative_integer(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number) or number < 0 or not number.is_integer():
        return None
    return int(number)


def _session_map(record):
    rows = record.get("contract_rows") if isinstance(record, dict) else None
    if not isinstance(rows, list):
        raise ValueError("archive session contract_rows missing")
    mapped = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("malformed contract row")
        symbol = str(row.get("Symbol") or "").strip().upper()
        expiry = str(row.get("ExpiryDate") or "").strip().upper()
        if symbol not in {"GOLD", "SILVER"} or not expiry:
            raise ValueError("unexpected MCX contract identity")
        key = (symbol, expiry)
        if key in mapped:
            raise ValueError(f"duplicate contract {symbol} {expiry}")
        close = _positive_number(row.get("Close"))
        oi = _nonnegative_integer(row.get("OpenInterest"))
        if close is None or oi is None:
            raise ValueError(f"invalid price/OI for {symbol} {expiry}")
        mapped[key] = {"close": close, "oi": oi}
    return mapped


def evaluate_forward_price_oi(archive, min_signal_sessions=60):
    """Test whether current price direction continues or reverses next session.

    Signal inputs use only previous/current sessions. Outcome is the next
    archived session's close change for the identical symbol+expiry. Missing
    contracts, unchanged price/OI, malformed dates and duplicate sessions
    are excluded, never imputed. Calendar gaps are reported as archived-session
    steps; this is not necessarily a one-calendar-day forecast.
    """
    records = archive.get("records") if isinstance(archive, dict) else None
    if not isinstance(records, list):
        return {"status": "blocked", "reason": "archive records missing",
                "observations": 0, "included_in_asset_final": False}
    ordered = sorted(records, key=lambda item: str(item.get("date", "")) if isinstance(item, dict) else "")
    dates = []
    maps = []
    for record in ordered:
        if not isinstance(record, dict):
            raise ValueError("malformed archive session")
        try:
            session_date = date.fromisoformat(str(record.get("date")))
        except (TypeError, ValueError):
            raise ValueError("invalid archive session date")
        if dates and session_date <= dates[-1]:
            raise ValueError("duplicate or non-increasing archive session dates")
        dates.append(session_date)
        maps.append(_session_map(record))

    by_symbol = defaultdict(lambda: {"regimes": defaultdict(lambda: {
        "observations": 0, "continuation_hits": 0, "contrarian_hits": 0,
        "next_up": 0, "next_down": 0, "next_flat": 0}), "signal_dates": set()})
    excluded = defaultdict(int)
    observations = []
    for index in range(1, len(maps) - 1):
        previous, current, following = maps[index - 1], maps[index], maps[index + 1]
        for key in sorted(set(previous) & set(current) & set(following)):
            p, c, n = previous[key], current[key], following[key]
            price_delta = c["close"] - p["close"]
            oi_delta = c["oi"] - p["oi"]
            next_delta = n["close"] - c["close"]
            if price_delta == 0 or oi_delta == 0:
                excluded["unchanged_signal_input"] += 1
                continue
            outcome = "flat" if next_delta == 0 else ("up" if next_delta > 0 else "down")
            regime = ("price_up_oi_up" if price_delta > 0 and oi_delta > 0 else
                      "price_up_oi_down" if price_delta > 0 and oi_delta < 0 else
                      "price_down_oi_up" if price_delta < 0 and oi_delta > 0 else
                      "price_down_oi_down")
            expected = "up" if price_delta > 0 else "down"
            item = {"symbol": key[0], "expiry": key[1],
                    "signal_date": dates[index].isoformat(),
                    "outcome_date": dates[index + 1].isoformat(),
                    "price_oi_regime": regime, "next_session_direction": outcome}
            observations.append(item)
            symbol_data = by_symbol[key[0]]
            symbol_data["signal_dates"].add(item["signal_date"])
            bucket = symbol_data["regimes"][regime]
            bucket["observations"] += 1
            bucket["continuation_hits"] += int(outcome == expected)
            bucket["contrarian_hits"] += int(outcome != expected and outcome != "flat")
            bucket["next_up"] += int(outcome == "up")
            bucket["next_down"] += int(outcome == "down")
            bucket["next_flat"] += int(outcome == "flat")

    per_symbol = {}
    for symbol in ("GOLD", "SILVER"):
        symbol_data = by_symbol[symbol]
        signal_sessions = len(symbol_data["signal_dates"])
        regime_summary = {}
        for name, values in sorted(symbol_data["regimes"].items()):
            count = values["observations"]
            directional = values["next_up"] + values["next_down"]
            regime_summary[name] = {
                **values,
                "continuation_accuracy_pct": round(100 * values["continuation_hits"] / count, 2) if count else None,
                "contrarian_accuracy_pct_excluding_flat": round(100 * values["contrarian_hits"] / directional, 2) if directional else None,
            }
        per_symbol[symbol] = {
            "status": "available" if signal_sessions >= int(min_signal_sessions) else "insufficient_sample",
            "observations": sum(v["observations"] for v in regime_summary.values()),
            "signal_sessions": signal_sessions,
            "minimum_signal_sessions": int(min_signal_sessions),
            "regimes": regime_summary,
            "reason": None if signal_sessions >= int(min_signal_sessions) else
                f"signal sessions {signal_sessions} below minimum {int(min_signal_sessions)}",
        }

    count = len(observations)
    all_symbols_ready = all(per_symbol[symbol]["status"] == "available" for symbol in ("GOLD", "SILVER"))
    result = {
        "status": "available" if all_symbols_ready else "insufficient_sample",
        "observations": count,
        "signal_sessions_by_symbol": {symbol: per_symbol[symbol]["signal_sessions"] for symbol in ("GOLD", "SILVER")},
        "minimum_signal_sessions_per_symbol": int(min_signal_sessions),
        "sample_unit": "contract-expiry observations; GOLD and SILVER are reported separately; multiple expiries on one date are not independent sessions",
        "by_symbol": per_symbol,
        "excluded": dict(excluded),
        "sample": observations,
        "method": "same symbol+expiry; prior/current price-OI regime predicts next archived-session close direction; no look-ahead",
        "source": "MCX India official FUTCOM Bhavcopy archive",
        "included_in_asset_final": False,
        "trading_signal": False,
    }
    if not all_symbols_ready:
        result["reason"] = "at least one commodity has fewer than the required distinct signal sessions"

    return result
