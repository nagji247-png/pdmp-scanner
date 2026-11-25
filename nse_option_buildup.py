"""Daily option premium/OI build-up diagnostics from NSE UDiFF EOD archive.

These are descriptive EOD patterns, not intraday signals and not an asset score.
"""
from __future__ import annotations

import datetime as dt
import copy

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



def validate_option_buildup_diagnostic(diagnostic, min_matched_contracts=20):
    """Fail closed if summary counters and per-category contract details disagree."""
    if not isinstance(diagnostic, dict):
        return {
            "available": False,
            "status": "UNAVAILABLE",
            "integrity_validation": "FAILED",
            "integrity_error": "diagnostic is missing or not an object",
            "reason": "EOD build-up diagnostic का डेटा संरचनात्मक जाँच में विफल रहा।",
            "matched_contracts": 0,
            "classified_contracts": 0,
            "categories": {
                key: {"label": label, "oi_quantity": 0, "contracts": 0,
                      "ce_oi_quantity": 0, "pe_oi_quantity": 0}
                for key, label in CATEGORIES.items()
            },
            "coverage_validated": False,
            "included_in_asset_final": False,
        }

    checked = copy.deepcopy(diagnostic)

    def fail(reason):
        checked["reported_matched_contracts"] = checked.get("matched_contracts")
        checked["reported_classified_contracts"] = checked.get("classified_contracts")
        _original_categories = checked.get("categories")
        checked["reported_category_contracts"] = {
            key: value.get("contracts") if isinstance(value, dict) else None
            for key, value in (_original_categories.items() if isinstance(_original_categories, dict) else [])
        }
        checked["available"] = False
        checked["status"] = "UNAVAILABLE"
        checked["integrity_validation"] = "FAILED"
        checked["integrity_error"] = reason
        checked["reason"] = (
            "EOD Build-up के कुल आँकड़े और contract details आपस में मेल नहीं खाते; "
            "सुरक्षा के लिए यह डेटा हटाकर UNAVAILABLE रखा गया है।"
        )
        checked["matched_contracts"] = 0
        checked["classified_contracts"] = 0
        checked["categories"] = {
            key: {"label": label, "oi_quantity": 0, "contracts": 0,
                  "ce_oi_quantity": 0, "pe_oi_quantity": 0}
            for key, label in CATEGORIES.items()
        }
        checked.pop("display_snapshot", None)
        checked.pop("display_status", None)
        checked["coverage_validated"] = False
        checked["included_in_asset_final"] = False
        return checked

    categories = checked.get("categories")
    if not isinstance(categories, dict):
        return fail("categories is missing or invalid")

    matched = checked.get("matched_contracts")
    classified = checked.get("classified_contracts")
    if (isinstance(matched, bool) or not isinstance(matched, int) or matched < 0
            or isinstance(classified, bool) or not isinstance(classified, int) or classified < 0):
        return fail("matched/classified counters must be non-negative integers")

    category_contracts = 0
    detail_contracts = 0
    for key in CATEGORIES:
        item = categories.get(key)
        if not isinstance(item, dict):
            return fail(f"category {key} is missing or invalid")
        count = item.get("contracts")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            return fail(f"category {key} contract count is invalid")
        details = item.get("contract_details")
        if details is None:
            if count:
                return fail(f"category {key} has contracts but no contract_details")
            details = []
        if not isinstance(details, list) or len(details) != count:
            return fail(f"category {key} details count does not match its contracts")
        category_contracts += count
        detail_contracts += len(details)

    if classified != category_contracts or classified != detail_contracts:
        return fail(
            f"classified={classified}, category_contracts={category_contracts}, "
            f"detail_contracts={detail_contracts}"
        )
    if matched < classified:
        return fail(f"matched={matched} is lower than classified={classified}")
    if checked.get("available") is True and (
        matched < min_matched_contracts or classified <= 0
    ):
        return fail("available flag conflicts with matched/classified thresholds")

    checked["integrity_validation"] = "PASSED"
    checked["integrity_error"] = None
    snapshot = checked.get("display_snapshot")
    if isinstance(snapshot, dict):
        checked_snapshot = validate_option_buildup_diagnostic(
            snapshot, min_matched_contracts=min_matched_contracts
        )
        if checked_snapshot.get("integrity_validation") != "PASSED":
            checked.pop("display_snapshot", None)
            checked["display_status"] = "UNAVAILABLE"
            checked["reason"] = (
                (checked.get("reason") or "पिछला सत्यापित डेटा उपलब्ध नहीं।")
                + " पिछला snapshot भी integrity जाँच में विफल रहा।"
            )
        else:
            checked["display_snapshot"] = checked_snapshot
    return checked


def build_option_buildup_diagnostic(archive, symbol, as_of_date=None,
                                    max_age_days=3, min_matched_contracts=20,
                                    expected_source_date=None):
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
    latest_record = valid_records[-1] if valid_records else None
    if latest_record:
        unavailable["source_date"] = latest_record.get("date")
        unavailable["fetched_at"] = latest_record.get("fetched_at")
    if len(valid_records) < 2:
        unavailable["reason"] = "दो तुलनीय NSE EOD सत्रों का contract-level premium/OI डेटा अभी जमा नहीं"
        return unavailable

    previous, current = valid_records[-2], valid_records[-1]
    previous_date, current_date = _date(previous.get("date")), _date(current.get("date"))
    unavailable["source_date"] = current.get("date")
    unavailable["fetched_at"] = current.get("fetched_at")
    if not previous_date or not current_date or current_date <= previous_date:
        unavailable["reason"] = "EOD session dates invalid or not increasing"
        return unavailable
    expected = _date(expected_source_date) if expected_source_date is not None else None
    if expected_source_date is not None and expected is None:
        unavailable["source_date"] = current_date.isoformat()
        unavailable["reason"] = (
            "इस वर्ष का आधिकारिक NSE ट्रेडिंग कैलेंडर उपलब्ध/मान्य नहीं है; "
            "EOD तारीख़ की पुष्टि नहीं हो सकी, इसलिए पुराना डेटा ताज़ा नहीं माना जाएगा"
        )
        return unavailable
    if expected is not None and current_date != expected:
        unavailable["source_date"] = current_date.isoformat()
        unavailable["expected_source_date"] = expected.isoformat()
        unavailable["reason"] = (
            f"नया NSE EOD सत्र {expected.isoformat()} अभी नहीं मिला; "
            f"नीचे {current_date.isoformat()} तक का पिछला सत्यापित डेटा केवल जानकारी के लिए दिखाया गया है"
        )
        # Keep the last validated comparison visible, but keep the top-level
        # diagnostic unavailable so stale EOD data cannot be treated as current.
        snapshot = build_option_buildup_diagnostic(
            archive, symbol, as_of_date=current_date.isoformat(),
            max_age_days=10000, min_matched_contracts=min_matched_contracts,
            expected_source_date=None,
        )
        if snapshot.get("available"):
            unavailable["display_snapshot"] = snapshot
            unavailable["display_status"] = "STALE"
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
        "fetched_at": current.get("fetched_at"),
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
