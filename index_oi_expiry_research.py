"""Exact-expiry research diagnostics for NSE index derivatives archives.

Offline only. Never creates a score, fetches data, or modifies production data.
"""
from __future__ import annotations

import datetime as dt


def _date(value):
    try:
        return dt.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _number(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if result >= 0 and result < float("inf") else None


def _records(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        return []
    return sorted(
        (row for row in payload["records"] if isinstance(row, dict)),
        key=lambda row: str(row.get("date") or ""),
    )


def summarize_index_futures_same_expiry(payload, symbols=("NIFTY", "BANKNIFTY")):
    """Compare exact same-expiry FUTIDX OI and close across adjacent archived sessions.

    Contract rolls are never stitched. Gaps greater than five calendar days are
    excluded to avoid treating missing archive sessions as adjacent observations.
    """
    records = _records(payload)
    result = {}
    for symbol in symbols:
        observations = []
        previous = None
        for record in records:
            trade_date = _date(record.get("date"))
            item = ((record.get("index_futures") or {}).get(symbol) or {})
            by_expiry = item.get("by_expiry") if isinstance(item, dict) else {}
            current = by_expiry if isinstance(by_expiry, dict) else {}
            if previous is not None and trade_date is not None:
                gap = (trade_date - previous["date"]).days
                if 0 < gap <= 5:
                    for expiry in sorted(set(previous["contracts"]) & set(current)):
                        old = previous["contracts"][expiry]
                        new = current[expiry]
                        old_oi, new_oi = _number(old.get("open_interest")), _number(new.get("open_interest"))
                        old_close, new_close = _number(old.get("close")), _number(new.get("close"))
                        if None in (old_oi, new_oi, old_close, new_close) or old_close <= 0 or new_close <= 0:
                            continue
                        oi_delta = new_oi - old_oi
                        price_return = (new_close / old_close - 1.0) * 100.0
                        if price_return > 0 and oi_delta > 0:
                            regime = "long_buildup"
                        elif price_return > 0 and oi_delta < 0:
                            regime = "short_covering"
                        elif price_return < 0 and oi_delta > 0:
                            regime = "short_buildup"
                        elif price_return < 0 and oi_delta < 0:
                            regime = "long_unwinding"
                        else:
                            regime = "flat_or_mixed"
                        observations.append({
                            "from_date": previous["date"].isoformat(),
                            "to_date": trade_date.isoformat(),
                            "expiry": expiry,
                            "oi_change": int(oi_delta),
                            "close_return_pct": round(price_return, 6),
                            "regime": regime,
                        })
            previous = {"date": trade_date, "contracts": current} if trade_date else None
        result[symbol] = {
            "sessions": sum(1 for row in records if symbol in ((row.get("index_futures") or {}))),
            "same_expiry_observations": len(observations),
            "observations": observations,
            "score": None,
            "included_in_asset_final": False,
            "validation_status": "DIAGNOSTIC_ONLY_REQUIRES_HOLDOUT",
            "scope": "NSE official FUTIDX exact symbol and exact expiry; not participant CLIENT OI",
        }
    return result


def summarize_index_options_same_expiry(payload, symbols=("NIFTY", "BANKNIFTY")):
    """Keep CE and PE OI deltas separate for exact expiry pairs; no directional score."""
    records = _records(payload)
    result = {}
    for symbol in symbols:
        observations = []
        previous = None
        for record in records:
            trade_date = _date(record.get("date"))
            item = ((record.get("symbols") or {}).get(symbol) or {})
            expiries = item.get("by_expiry") if isinstance(item, dict) else {}
            current = expiries if isinstance(expiries, dict) else {}
            if previous is not None and trade_date is not None:
                gap = (trade_date - previous["date"]).days
                if 0 < gap <= 5:
                    for expiry in sorted(set(previous["expiries"]) & set(current)):
                        old, new = previous["expiries"][expiry], current[expiry]
                        sides = {}
                        valid = True
                        for side in ("CE", "PE"):
                            old_oi = _number((old.get(side) or {}).get("open_interest"))
                            new_oi = _number((new.get(side) or {}).get("open_interest"))
                            if old_oi is None or new_oi is None:
                                valid = False
                                break
                            sides[side] = {"oi_change": int(new_oi - old_oi)}
                        if valid:
                            observations.append({
                                "from_date": previous["date"].isoformat(),
                                "to_date": trade_date.isoformat(),
                                "expiry": expiry,
                                "sides": sides,
                            })
            previous = {"date": trade_date, "expiries": current} if trade_date else None
        result[symbol] = {
            "sessions": sum(1 for row in records if symbol in ((row.get("symbols") or {}))),
            "same_expiry_observations": len(observations),
            "observations": observations,
            "score": None,
            "included_in_asset_final": False,
            "validation_status": "DIAGNOSTIC_ONLY_REQUIRES_HOLDOUT",
            "scope": "NSE official IDO CE and PE OI separately by exact expiry; option OI alone is not directional",
        }
    return result


def build_report(payload):
    return {
        "mode": "offline_exact_expiry_index_oi_research",
        "external_requests_made": 0,
        "production_data_modified": False,
        "production_score_modified": False,
        "index_futures": summarize_index_futures_same_expiry(payload),
        "index_options": summarize_index_options_same_expiry(payload),
        "guardrail": "No score is emitted. Exact-expiry observations remain diagnostic until adequate holdout testing validates directional edge.",
    }
