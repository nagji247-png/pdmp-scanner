"""Provisional component scores from already archived market evidence.

These scores are separate from the published PDMP score. They are intended
to make available evidence visible immediately while the historical samples
continue to accumulate.
"""
from component_scoring import build_component, clamp_score, finite_number

PROVISIONAL_WEIGHTS = {
    "news": 40.0,
    "search": 40.0,
    "eod_oi": 20.0,
    "client_ce_pe": 10.0,
    "client_futures": 10.0,
    "stock_basket": 20.0,
}


def index_oi_balance_component(archive, asset, scan_date, weight=20.0, sessions=5):
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
    mean_score = sum(item["score"] for item in observations) / len(observations)
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


def client_marketwide_components(context):
    """Create provisional contrarian scores from dated CLIENT percentage changes."""
    if not isinstance(context, dict) or not context.get("available"):
        return {}
    evidence = context.get("evidence_components") or {}
    source = context.get("source") or "NSE official participant-wise OI · CLIENT"
    source_date = context.get("source_date")
    output = {}
    groups = {
        "client_ce_pe": ("ce_long", "ce_short", "pe_long", "pe_short"),
        "client_futures": ("futures_long", "futures_short"),
    }
    for component_name, names in groups.items():
        values = []
        for name in names:
            item = evidence.get(name) or {}
            pct = finite_number(item.get("change_pct_prior_gross"))
            bias = item.get("contrarian_bias")
            if pct is None or bias not in ("bullish", "bearish"):
                continue
            direction = 1.0 if bias == "bullish" else -1.0
            values.append(max(-10.0, min(10.0, pct * direction)))
        if len(values) != len(names) or not source_date:
            continue
        score = sum(values) / len(values)
        weight = PROVISIONAL_WEIGHTS[component_name]
        output[component_name] = build_component(
            score, source, source_date, weight,
            scope="market-wide CLIENT aggregate; same context across NIFTY, SENSEX and BANKNIFTY",
            method="प्रत्येक CLIENT बदलाव का prior-gross % × contrarian direction; उपलब्ध सभी पक्षों का औसत",
            validation_status="प्रारंभिक; market-wide directional validation जारी",
            evidence_fields=list(names),
            previous_source_date=context.get("previous_date"),
        )
    return output
