"""Daily option premium/OI build-up diagnostics from NSE UDiFF EOD archive.

These are descriptive EOD patterns, not intraday signals and not an asset score.
"""
from __future__ import annotations

import datetime as dt

CATEGORIES = {
    "long_build_up": "LONG BUILD-UP",
    "short_build_up": "SHORT BUILD-UP",
    "short_covering": "SHORT COVERING",
    "long_unwinding": "LONG UNWINDING",
}


def _date(value):
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _contract_map(record, symbol):
    payload = (record.get("option_contracts") or {}).get(symbol) or {}
    rows = payload.get("contracts") or []
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            key = (
                str(row["expiry"]),
                str(row["side"]).upper(),
                round(float(row["strike"]), 4),
            )
            close = float(row["close"])
            oi = int(row["open_interest"])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if key[1] not in ("CE", "PE") or close <= 0 or oi < 0:
            continue
        result[key] = {"close": close, "open_interest": oi}
    return result


def build_option_buildup_diagnostic(archive, symbol, as_of_date=None,
                                    max_age_days=3, min_matched_contracts=20):
    """Compare same expiry/strike/side contracts across the latest two EOD sessions."""
    unavailable = {
        "available": False,
        "status": "UNAVAILABLE",
        "source": "NSE F&O UDiFF Common Bhavcopy Final",
        "method": "Same expiry + strike + CE/PE; prior EOD close vs current EOD close and OI",
        "categories": {
            key: {"label": label, "oi_quantity": 0, "contracts": 0,
                  "ce_oi_quantity": 0, "pe_oi_quantity": 0}
            for key, label in CATEGORIES.items()
        },
        "matched_contracts": 0,
        "classified_contracts": 0,
        "coverage_validated": False,
        "included_in_asset_final": False,
    }
    if symbol not in ("NIFTY", "BANKNIFTY") or not isinstance(archive, dict):
        unavailable["reason"] = "NSE EOD option archive not applicable or unavailable"
        return unavailable

    records = archive.get("records") or []
    valid_records = [
        row for row in records
        if isinstance(row, dict) and _contract_map(row, symbol)
    ]
    valid_records.sort(key=lambda row: str(row.get("date") or ""))
    if len(valid_records) < 2:
        unavailable["reason"] = "दो तुलनीय NSE EOD सत्रों का contract-level premium/OI डेटा अभी जमा नहीं"
        return unavailable

    previous, current = valid_records[-2], valid_records[-1]
    previous_date, current_date = _date(previous.get("date")), _date(current.get("date"))
    if not previous_date or not current_date or current_date <= previous_date:
        unavailable["reason"] = "EOD session dates invalid or not increasing"
        return unavailable
    as_of = _date(as_of_date) if as_of_date else dt.date.today()
    if as_of and (as_of - current_date).days > max_age_days:
        unavailable["source_date"] = current_date.isoformat()
        unavailable["reason"] = "सबसे नया NSE EOD डेटा पुराना है"
        return unavailable

    old = _contract_map(previous, symbol)
    new = _contract_map(current, symbol)
    common = sorted(set(old) & set(new))
    totals = {
        key: {"label": label, "oi_quantity": 0, "contracts": 0,
              "ce_oi_quantity": 0, "pe_oi_quantity": 0,
              "contract_details": []}
        for key, label in CATEGORIES.items()
    }
    for contract in common:
        before, after = old[contract], new[contract]
        premium_change = after["close"] - before["close"]
        oi_change = after["open_interest"] - before["open_interest"]
        if premium_change == 0 or oi_change == 0:
            continue
        if premium_change > 0 and oi_change > 0:
            category = "long_build_up"
        elif premium_change < 0 and oi_change > 0:
            category = "short_build_up"
        elif premium_change > 0 and oi_change < 0:
            category = "short_covering"
        else:
            category = "long_unwinding"
        quantity = abs(oi_change)
        totals[category]["oi_quantity"] += quantity
        totals[category]["contracts"] += 1
        side_key = "ce_oi_quantity" if contract[1] == "CE" else "pe_oi_quantity"
        totals[category][side_key] += quantity
        totals[category]["contract_details"].append({
            "expiry": contract[0],
            "side": contract[1],
            "strike": contract[2],
            "previous_close": before["close"],
            "current_close": after["close"],
            "previous_oi": before["open_interest"],
            "current_oi": after["open_interest"],
            "oi_change": oi_change,
            "oi_quantity": quantity,
        })

    for item in totals.values():
        item["contract_details"].sort(
            key=lambda row: (-row["oi_quantity"], row["expiry"], row["strike"], row["side"])
        )

    classified = sum(item["contracts"] for item in totals.values())
    result = {
        **unavailable,
        "available": len(common) >= min_matched_contracts and classified > 0,
        "status": "AVAILABLE" if len(common) >= min_matched_contracts and classified > 0 else "UNAVAILABLE",
        "source_date": current_date.isoformat(),
        "previous_source_date": previous_date.isoformat(),
        "categories": totals,
        "matched_contracts": len(common),
        "classified_contracts": classified,
        "coverage_validated": False,
        "included_in_asset_final": False,
    }
    if not result["available"]:
        result["reason"] = (
            f"पर्याप्त तुलनीय कॉन्ट्रैक्ट/बदलाव नहीं: matched {len(common)}, "
            f"classified {classified}, आवश्यक matched {min_matched_contracts}"
        )
    else:
        result["reason"] = None
    return result
