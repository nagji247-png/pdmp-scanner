"""Provisional component scores from already archived market evidence.

These scores are separate from the published PDMP score. They are intended
to make available evidence visible immediately while the historical samples
continue to accumulate.
"""
import datetime as dt

from component_scoring import build_component, clamp_score, finite_number

# User-approved provisional component weights. These are separate from the
# published PDMP Main Score weights in component_scoring.py.
# combine_components renormalizes only across components with valid evidence.
def source_date_is_fresh(source_date, scan_date, max_age_days=3):
    """Reject missing, future-dated, or calendar-stale archived evidence."""
    try:
        observed = dt.date.fromisoformat(str(source_date)[:10])
        scanned = dt.date.fromisoformat(str(scan_date)[:10])
    except (TypeError, ValueError):
        return False
    age_days = (scanned - observed).days
    return 0 <= age_days <= int(max_age_days)


PROVISIONAL_WEIGHTS = {
    "news": 15.0,
    "stock_basket": 20.0,
    "eod_oi": 15.0,
    "client_ce_pe": 15.0,
    "client_futures": 15.0,
    "search": 20.0,
}


def index_oi_balance_component(archive, asset, scan_date, weight=20.0, sessions=5, max_age_days=3):
    """Average the nearest-unexpired-expiry PE/CE OI balance over recent sessions."""
    if not isinstance(archive, dict):
        return None
    records = [
        row for row in archive.get("records", [])
        if isinstance(row, dict)
        and isinstance(row.get("date"), str)
        and row["date"] <= str(scan_date)
    ]
    records.sort(key=lambda row: row["date"])
    observations = []
    for row in records[-int(sessions):]:
        symbol_data = (row.get("symbols") or {}).get(asset)
        by_expiry = symbol_data.get("by_expiry") if isinstance(symbol_data, dict) else None
        if not isinstance(by_expiry, dict):
            continue
        eligible = sorted(
            expiry for expiry in by_expiry
            if isinstance(expiry, str) and expiry >= row["date"]
        )
        if not eligible:
            continue
        expiry = eligible[0]
        sides = by_expiry.get(expiry) or {}
        ce = sides.get("CE") or {}
        pe = sides.get("PE") or {}
        ce_oi = finite_number(ce.get("open_interest"))
        pe_oi = finite_number(pe.get("open_interest"))
        ce_contracts = finite_number(ce.get("contracts"))
        pe_contracts = finite_number(pe.get("contracts"))
        if (ce_oi is None or pe_oi is None or ce_oi < 0 or pe_oi < 0
                or ce_contracts is None or pe_contracts is None
                or ce_contracts <= 0 or pe_contracts <= 0
                or ce_oi + pe_oi <= 0):
            continue
        score = clamp_score(10.0 * (pe_oi - ce_oi) / (pe_oi + ce_oi))
        if score is not None:
            observations.append({
                "date": row["date"], "expiry": expiry,
                "ce_oi": int(ce_oi), "pe_oi": int(pe_oi),
                "score": score,
            })
    if not observations:
        return None
    # Never let an old archive masquerade as a current component.
    if not source_date_is_fresh(observations[-1]["date"], scan_date, max_age_days):
        return None
    mean_score = round(sum(item["score"] for item in observations) / len(observations), 2)
    return build_component(
        mean_score,
        "NSE F&O UDiFF · nearest-expiry PE/CE open-interest balance",
        observations[-1]["date"],
        weight,
        observations=len(observations),
        session_dates=[item["date"] for item in observations],
        expiry_dates=[item["expiry"] for item in observations],
        method="प्रत्येक सत्र: 10 × (nearest-expiry PE OI − CE OI) ÷ (PE OI + CE OI); उपलब्ध सत्रों का औसत",
        validation_status="प्रारंभिक; historical directional validation जारी",
        scope="index-specific; nearest unexpired expiry",
    )


def client_marketwide_components(context, scan_date=None, max_age_days=3):
    """Build a shared market-wide CLIENT CE/PE quantity-balance component.

    The score is intentionally shared by NIFTY, SENSEX and BANKNIFTY because
    NSE participant-wise CLIENT option positions are market-wide aggregates.
    It is a provisional crowd-positioning diagnostic, not index-specific data
    and not a validated trading predictor. CLIENT futures remain excluded.
    """
    if not isinstance(context, dict) or not context.get("available"):
        return {}
    source = context.get("source") or "NSE official participant-wise OI · CLIENT"
    source_date = context.get("source_date")
    if not source_date:
        return {}
    if scan_date is not None and not source_date_is_fresh(
        source_date, scan_date, max_age_days
    ):
        return {}

    evidence = context.get("evidence_components") or {}
    keys = ("ce_long", "ce_short", "pe_long", "pe_short")
    changes = {}
    for key in keys:
        row = evidence.get(key)
        change = finite_number(row.get("change")) if isinstance(row, dict) else None
        if change is None:
            return {}
        changes[key] = change

    # Keep the user's quantity-based construction transparent:
    # (CALL Long - CALL Short) + (PUT Long - PUT Short).
    ce_net = changes["ce_long"] - changes["ce_short"]
    pe_net = changes["pe_long"] - changes["pe_short"]
    net_change = ce_net + pe_net
    gross_change = sum(abs(value) for value in changes.values())
    if gross_change <= 0:
        return {}

    score = clamp_score(10.0 * net_change / gross_change)
    if score is None:
        return {}
    component = build_component(
        score,
        source,
        source_date,
        PROVISIONAL_WEIGHTS["client_ce_pe"],
        scope="shared market-wide CLIENT aggregate; same component on NIFTY, SENSEX and BANKNIFTY; not index-specific",
        method="10 × [(CALL Long change − CALL Short change) + (PUT Long change − PUT Short change)] ÷ sum(abs(all four CE/PE changes)); clamp −10..+10",
        validation_status="PROVISIONAL_DIAGNOSTIC · quantity-based; predictive holdout validation pending",
        directional_reading="bullish_client_positioning" if net_change > 0 else ("bearish_client_positioning" if net_change < 0 else "balanced_client_positioning"),
        call_net_change=round(ce_net, 4),
        put_net_change=round(pe_net, 4),
        combined_net_change=round(net_change, 4),
        gross_absolute_change=round(gross_change, 4),
        evidence_fields=list(keys),
        previous_source_date=context.get("previous_date"),
        not_index_specific=True,
        not_validated_predictor=True,
    )
    return {"client_ce_pe": component} if component else {}
