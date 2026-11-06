"""Source-aware, fail-closed component scoring helpers for PDMP shadow scores.

These helpers never turn missing/stale inputs into zero and never mutate the
published production score.
"""
from datetime import datetime, timezone, timedelta
import math

DEFAULT_COMPONENT_WEIGHTS = {
    "news": 40.0,
    "search": 40.0,
    "eod_oi": 20.0,
    "futures": 20.0,
    "stock_basket": 20.0,
}

INDIAN_INDEX_SCOPE = (
    "NSE participant-wise market-wide Index F&O aggregate; not index-specific"
)


def finite_number(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def clamp_score(value):
    """Return a finite component score in [-10, +10], or None if unavailable."""
    number = finite_number(value)
    if number is None:
        return None
    return round(max(-10.0, min(10.0, number)), 4)


def parse_utc_timestamp(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        stamp = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def is_fresh_timestamp(value, now_utc=None, max_age_minutes=360, future_skew_minutes=5):
    """Timestamp freshness check. Naive timestamps are interpreted as UTC."""
    stamp = parse_utc_timestamp(value)
    if stamp is None:
        return False
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    age_minutes = (now.astimezone(timezone.utc) - stamp).total_seconds() / 60.0
    return -float(future_skew_minutes) <= age_minutes <= float(max_age_minutes)


def build_component(score, source, source_date, weight, **metadata):
    """Create a scored component only when score, source, date and weight exist."""
    normalized = clamp_score(score)
    numeric_weight = finite_number(weight)
    if normalized is None or not str(source or "").strip():
        return None
    if not isinstance(source_date, str) or not source_date.strip():
        return None
    if numeric_weight is None or numeric_weight <= 0:
        return None
    component = {
        "score": normalized,
        "source": str(source).strip(),
        "source_date": source_date.strip(),
        "weight": numeric_weight,
        "included": True,
    }
    component.update(metadata)
    return component


def search_component_from_snapshot(
    snapshot, now_utc=None, max_age_minutes=120, weight=40.0
):
    """Accept only a fresh, timestamped, asset-specific one-day Trends reading."""
    if not isinstance(snapshot, dict) or not snapshot.get("valid"):
        return None, "कोई वैध asset-specific Google Trends reading उपलब्ध नहीं"
    if snapshot.get("timeframe") != "now 1-d":
        return None, "केवल now 1-d reading स्वीकार है; 7-दिन fallback Search Score में शामिल नहीं"
    stamp = snapshot.get("source_data_time") or snapshot.get("as_of")
    if not is_fresh_timestamp(stamp, now_utc, max_age_minutes=max_age_minutes):
        return None, "Google Trends reading stale है या उसका वास्तविक observation timestamp मान्य नहीं"
    # A neutral-only query set has no directional crowd evidence. Keep its
    # descriptive 100% neutral mix in the snapshot, but do not inject a fake
    # zero into the weighted asset Final Score.
    directional_bull_pct = finite_number(snapshot.get("directional_bull_pct"))
    if directional_bull_pct is None:
        return None, "Google Trends में bullish-vs-bearish directional evidence नहीं; Search Final से बाहर"
    score = clamp_score(snapshot.get("neutral_aware_score"))
    if score is None:
        return None, "Google Trends directional score उपलब्ध नहीं"
    source = snapshot.get("source") or "Google Trends related_queries · India"
    stamp_dt = parse_utc_timestamp(stamp)
    source_date = stamp_dt.astimezone(timezone(timedelta(hours=5, minutes=30))).date().isoformat()
    component = build_component(
        score,
        source,
        source_date,
        weight,
        observed_at=stamp,
        seed=snapshot.get("seed"),
        timeframe="now 1-d",
        classified_queries=snapshot.get("classified_queries"),
        scope=snapshot.get("scope")
        or "एक seed की अपनी related-query scale; relative search interest, population percentage नहीं",
        denominator=snapshot.get("denominator")
        or "same seed's classified related-query relative weights only; not all searches or population percentages",
        score_method="(bullish classified weight - bearish classified weight) / all classified weight × 10",
        terms=snapshot.get("terms") or [],
    )
    if component is None:
        return None, "Search component में score/source/date/weight अधूरा है"
    return component, None


def combine_components(components, weights=None):
    """Weighted mean of valid components; missing components leave the denominator."""
    configured = weights or DEFAULT_COMPONENT_WEIGHTS
    valid = {}
    for name, component in (components or {}).items():
        if not isinstance(component, dict) or component.get("included") is False:
            continue
        score = clamp_score(component.get("score"))
        source = component.get("source")
        source_date = component.get("source_date")
        weight = finite_number(configured.get(name, component.get("weight")))
        if (
            score is None
            or not isinstance(source, str) or not source.strip()
            or not isinstance(source_date, str) or not source_date.strip()
            or weight is None or weight <= 0
        ):
            continue
        valid[name] = {"score": score, "weight": weight}

    total_weight = sum(item["weight"] for item in valid.values())
    if total_weight <= 0:
        return {
            "status": "unavailable",
            "score": None,
            "included_components": [],
            "normalized_weights_pct": {},
            "weight_total": 0.0,
        }

    normalized = {
        name: round(item["weight"] / total_weight * 100.0, 2)
        for name, item in valid.items()
    }
    final_score = sum(
        item["score"] * item["weight"] for item in valid.values()
    ) / total_weight
    return {
        "status": "available",
        "score": round(max(-10.0, min(10.0, final_score)), 2),
        "included_components": list(valid.keys()),
        "normalized_weights_pct": normalized,
        "weight_total": round(total_weight, 4),
    }


def client_oi_context(participant_today, changes):
    """Return aggregate CLIENT CE/PE/Futures changes as context, never an index score."""
    today = participant_today if isinstance(participant_today, dict) else {}
    change_data = changes if isinstance(changes, dict) else {}
    result = {
        "available": False,
        "source": today.get("source") or "NSE official participant-wise OI",
        "source_date": today.get("date"),
        "previous_date": change_data.get("prev_date"),
        "scope": INDIAN_INDEX_SCOPE,
        "included_in_asset_final": False,
        "reason": None,
        "ce_build_up": {
            "call_long_change": None,
            "call_short_change": None,
        },
        "pe_build_up": {
            "put_long_change": None,
            "put_short_change": None,
        },
        "client_index_futures": {
            "long_change": None,
            "short_change": None,
        },
        "directional_scoring": {
            "ce_pe": "Withheld: option-side long/short changes are not validated directional predictors.",
            "futures": "Withheld: market-wide CLIENT futures directional backtest is not robust enough for live scoring.",
        },
    }
    if not today.get("ok") or today.get("stale") or not today.get("date"):
        result["reason"] = "ताज़ा, तारीख़ वाला NSE participant EOD snapshot उपलब्ध नहीं"
        return result
    if not change_data.get("ok"):
        result["reason"] = "पिछले उपलब्ध EOD snapshot से CLIENT बदलाव सत्यापित नहीं"
        return result
    client = ((change_data.get("by_group") or {}).get("CLIENT") or {})
    if not client:
        result["reason"] = "NSE report में CLIENT participant row उपलब्ध नहीं"
        return result

    def value(key):
        raw = client.get(key)
        number = finite_number(raw)
        return int(number) if number is not None else None

    result["ce_build_up"] = {
        "call_long_change": value("index_call_long"),
        "call_short_change": value("index_call_short"),
    }
    result["pe_build_up"] = {
        "put_long_change": value("index_put_long"),
        "put_short_change": value("index_put_short"),
    }
    result["client_index_futures"] = {
        "long_change": value("future_index_long"),
        "short_change": value("future_index_short"),
    }
    result["available"] = any(
        item is not None
        for group in (
            result["ce_build_up"],
            result["pe_build_up"],
            result["client_index_futures"],
        )
        for item in group.values()
    )
    if not result["available"]:
        result["reason"] = "CLIENT की चार CE/PE बदलाव फ़ील्ड और Futures बदलाव उपलब्ध नहीं"
    return result


def _parse_exchange_date(value):
    """Parse UDiFF ISO dates plus common exchange display dates."""
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%b-%y", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _exchange_integer(value):
    """Parse integer OI fields without treating blanks or malformed text as zero."""
    if value is None or isinstance(value, bool):
        return None
    try:
        raw = str(value).replace(",", "").strip()
        if not raw:
            return None
        number = float(raw)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number) or not number.is_integer():
        return None
    return int(number)


def aggregate_nse_udiff_index_option_oi(rows, symbol, trade_date):
    """Aggregate NSE UDiFF OPTIDX CE/PE OI for one index and one exact trade date.

    This is exchange-file context only. It does not claim contract-master
    completeness and is deliberately not converted into a directional score.
    """
    target_symbol = str(symbol or "").strip().upper()
    target_date = _parse_exchange_date(str(trade_date or ""))
    if not target_symbol or not target_date or not isinstance(rows, list):
        return {"available": False, "included_in_asset_final": False,
                "reason": "symbol/date/UDiFF rows missing or invalid"}

    totals = {
        "CE": {"open_interest": 0, "change_in_oi": 0, "contracts": 0},
        "PE": {"open_interest": 0, "change_in_oi": 0, "contracts": 0},
    }
    expiries = set()
    matched = 0
    malformed = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("FinInstrmTp") or "").strip().upper() != "OPTIDX":
            continue
        if str(row.get("TckrSymb") or "").strip().upper() != target_symbol:
            continue
        row_date = _parse_exchange_date(str(row.get("BizDt") or ""))
        if row_date != target_date:
            malformed.append("trade_date_mismatch_or_missing")
            continue
        side = str(row.get("OptnTp") or "").strip().upper()
        if side not in totals:
            malformed.append("invalid_option_type")
            continue
        oi = _exchange_integer(row.get("OpnIntrst"))
        change = _exchange_integer(row.get("ChngInOpnIntrst"))
        expiry = _parse_exchange_date(str(row.get("XpryDt") or ""))
        if oi is None or change is None or expiry is None:
            malformed.append("missing_oi_change_or_expiry")
            continue
        totals[side]["open_interest"] += oi
        totals[side]["change_in_oi"] += change
        totals[side]["contracts"] += 1
        expiries.add(expiry)
        matched += 1

    valid = (
        matched > 0
        and totals["CE"]["contracts"] > 0
        and totals["PE"]["contracts"] > 0
        and not malformed
    )
    return {
        "available": valid,
        "included_in_asset_final": False,
        "source": "NSE F&O UDiFF Common Bhavcopy Final",
        "source_date": target_date,
        "exchange": "NSE",
        "symbol": target_symbol,
        "instrument_type": "OPTIDX",
        "scope": "Observed CE/PE contracts across expiries in the dated exchange file; contract-master completeness not yet reconciled",
        "call": totals["CE"],
        "put": totals["PE"],
        "expiry_count": len(expiries),
        "matched_contract_rows": matched,
        "coverage_validated": False,
        "reason": None if valid else "दोनों CE/PE पक्षों का पूर्ण, साफ़ और तारीख़-मेल वाला UDiFF डेटा उपलब्ध नहीं",
        "validation_warnings": sorted(set(malformed)),
    }
