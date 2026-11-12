"""Guarded, auditable promotion of market-wide CLIENT Futures into provisional scores."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from component_scoring import build_component, clamp_score

SUMMARY_PATH = Path(__file__).resolve().parent / "participant_oi_backtest_summary.json"
INDEX_NAMES = ("NIFTY", "SENSEX", "BANKNIFTY")
ANCHOR_DATE = "2026-11-12"
MIN_SESSIONS = 14
MIN_PER_SIGNAL_SIDE = 4
MIN_HIT_RATE_PCT = 60.0
MIN_WILSON_LOWER_PCT = 50.0
MAX_REPORT_AGE_DAYS = 3


def wilson_lower_bound(successes, trials):
    if not isinstance(successes, int) or isinstance(successes, bool):
        return None
    if not isinstance(trials, int) or isinstance(trials, bool):
        return None
    if trials <= 0 or successes < 0 or successes > trials:
        return None
    z = 1.959963984540054
    p = successes / trials
    z2 = z * z
    denominator = 1.0 + z2 / trials
    center = p + z2 / (2.0 * trials)
    margin = z * ((p * (1.0 - p) / trials + z2 / (4.0 * trials * trials)) ** 0.5)
    return max(0.0, (center - margin) / denominator * 100.0)


def _orientation_metrics(check, orientation):
    rows = check.get("observations") or []
    rows = [
        row for row in rows
        if isinstance(row, dict)
        and row.get("predicted_direction") in ("BULLISH", "BEARISH")
        and row.get("actual_direction") in ("UP", "DOWN")
    ]
    bull = sum(row["predicted_direction"] == "BULLISH" for row in rows)
    bear = sum(row["predicted_direction"] == "BEARISH" for row in rows)
    if orientation == "direct":
        hits = sum(bool(row.get("correct")) for row in rows)
    else:
        hits = sum(bool(row.get("contrarian_correct")) for row in rows)
    n = len(rows)
    rate = hits / n * 100.0 if n else None
    lower = wilson_lower_bound(hits, n)
    eligible = (
        check.get("status") == "ready"
        and int(check.get("sample_sessions") or 0) >= MIN_SESSIONS
        and n >= MIN_SESSIONS
        and bull >= MIN_PER_SIGNAL_SIDE
        and bear >= MIN_PER_SIGNAL_SIDE
        and rate is not None and rate >= MIN_HIT_RATE_PCT
        and lower is not None and lower > MIN_WILSON_LOWER_PCT
    )
    return {
        "eligible": eligible,
        "observations": n,
        "bullish_signals": bull,
        "bearish_signals": bear,
        "hits": hits,
        "hit_rate_pct": round(rate, 2) if rate is not None else None,
        "wilson_95_lower_pct": round(lower, 2) if lower is not None else None,
    }


def evaluate_client_futures_promotion(summary):
    """Require a fresh 14-session, direction-diverse, all-index validation window."""
    base = {
        "status": "withheld",
        "eligible_for_provisional_final": False,
        "orientation": None,
        "anchor_date_exclusive": ANCHOR_DATE,
        "required_sessions": MIN_SESSIONS,
        "minimum_signal_each_side": MIN_PER_SIGNAL_SIDE,
        "minimum_hit_rate_pct": MIN_HIT_RATE_PCT,
        "minimum_wilson_95_lower_pct_exclusive": MIN_WILSON_LOWER_PCT,
        "scope": "shared market-wide CLIENT Index Futures; not index-specific",
        "index_checks": {},
        "reason": "14 नए, दोनों दिशाओं में पर्याप्त signals वाले सत्यापित सत्र अभी पूरे नहीं हुए।",
    }
    if not isinstance(summary, dict) or summary.get("status") != "exploratory_only":
        base["status"] = "report_unavailable"
        base["reason"] = "ताज़ा participant OI validation report उपलब्ध नहीं।"
        return base

    indices = summary.get("indices") or {}
    if not all(name in indices for name in INDEX_NAMES):
        base["status"] = "index_coverage_incomplete"
        base["reason"] = "NIFTY, SENSEX और BANKNIFTY — तीनों की validation coverage उपलब्ध नहीं।"
        return base

    checks = {
        name: (indices[name] or {}).get("client_futures_new_14_session_check") or {}
        for name in INDEX_NAMES
    }
    candidates = {}
    for orientation in ("direct", "contrarian"):
        candidates[orientation] = {
            name: _orientation_metrics(checks[name], orientation)
            for name in INDEX_NAMES
        }

    base["index_checks"] = {
        name: {
            "sample_sessions": checks[name].get("sample_sessions", 0),
            "remaining_observations": checks[name].get("remaining_observations", MIN_SESSIONS),
            "first_signal_date": checks[name].get("first_signal_date"),
            "last_signal_date": checks[name].get("last_signal_date"),
            "direct": candidates["direct"][name],
            "contrarian": candidates["contrarian"][name],
        }
        for name in INDEX_NAMES
    }

    passing = [
        orientation for orientation in ("direct", "contrarian")
        if all(candidates[orientation][name]["eligible"] for name in INDEX_NAMES)
    ]
    if not passing:
        any_ready = all(checks[name].get("status") == "ready" for name in INDEX_NAMES)
        base["status"] = "validation_failed" if any_ready else "collecting_new_sessions"
        base["reason"] = (
            "14 सत्र पूरे हुए, लेकिन सभी तीनों indices में 60% hit-rate, 95% Wilson lower bound >50% "
            "और कम-से-कम 4 bullish + 4 bearish signals की शर्त एक साथ पूरी नहीं हुई।"
            if any_ready else
            "तीनों indices के लिए 14 नए पूर्ण signal→अगले-सत्र परिणाम अभी एकत्र हो रहे हैं।"
        )
        return base

    if len(passing) == 1:
        selected = passing[0]
    else:
        selected = max(
            passing,
            key=lambda direction: sum(
                candidates[direction][name]["wilson_95_lower_pct"] or 0
                for name in INDEX_NAMES
            ),
        )
        if all(
            candidates[passing[0]][name]["wilson_95_lower_pct"]
            == candidates[passing[1]][name]["wilson_95_lower_pct"]
            for name in INDEX_NAMES
        ):
            base["status"] = "ambiguous_direction"
            base["reason"] = "Direct और contrarian दोनों का परिणाम बराबर है; Futures को शामिल नहीं किया गया।"
            return base

    base.update({
        "status": "promoted",
        "eligible_for_provisional_final": True,
        "orientation": selected,
        "reason": (
            "तीनों indices में 14+ नए परिणाम, दोनों signal दिशाओं में पर्याप्त sample, "
            "कम-से-कम 60% hit-rate और 95% Wilson lower bound 50% से ऊपर सत्यापित।"
        ),
    })
    return base


def load_client_futures_promotion(scan_date, path=None):
    """Load only a fresh summary; stale reports cannot keep a component promoted."""
    target = Path(path) if path else SUMMARY_PATH
    try:
        summary = json.loads(target.read_text(encoding="utf-8"))
        last_date = dt.date.fromisoformat(str(summary.get("oi_last_date"))[:10])
        current_date = dt.date.fromisoformat(str(scan_date)[:10])
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {
            "status": "report_unavailable",
            "eligible_for_provisional_final": False,
            "reason": "ताज़ा तारीख़ वाला CLIENT Futures validation report उपलब्ध नहीं।",
        }
    age = (current_date - last_date).days
    if age < 0 or age > MAX_REPORT_AGE_DAYS:
        return {
            "status": "stale_report",
            "eligible_for_provisional_final": False,
            "reason": "CLIENT Futures validation report 3 calendar days से पुराना या future-dated है।",
        }
    decision = summary.get("client_futures_promotion")
    return decision if isinstance(decision, dict) else {
        "status": "promotion_rule_missing",
        "eligible_for_provisional_final": False,
        "reason": "Validation report में auto-promotion decision उपलब्ध नहीं।",
    }


def build_client_futures_component(context, scan_date, promotion, weight=15.0, max_age_days=3):
    """Create a shared provisional component only after the guarded promotion passes."""
    if not isinstance(promotion, dict) or promotion.get("eligible_for_provisional_final") is not True:
        return None
    orientation = promotion.get("orientation")
    if orientation not in ("direct", "contrarian"):
        return None
    if not isinstance(context, dict) or not context.get("available"):
        return None
    try:
        source_date = dt.date.fromisoformat(str(context.get("source_date"))[:10])
        current_date = dt.date.fromisoformat(str(scan_date)[:10])
    except (TypeError, ValueError):
        return None
    age = (current_date - source_date).days
    if age < 0 or age > max_age_days:
        return None
    evidence = context.get("evidence_components") or {}
    long_row, short_row = evidence.get("futures_long"), evidence.get("futures_short")
    if not isinstance(long_row, dict) or not isinstance(short_row, dict):
        return None
    long_change, short_change = long_row.get("change"), short_row.get("change")
    previous_long, previous_short = long_row.get("previous_gross"), short_row.get("previous_gross")
    try:
        long_change, short_change = float(long_change), float(short_change)
        gross = float(previous_long) + float(previous_short)
    except (TypeError, ValueError):
        return None
    if gross <= 0:
        return None
    raw_score = clamp_score(10.0 * (long_change - short_change) / gross)
    if raw_score is None:
        return None
    score = -raw_score if orientation == "contrarian" else raw_score
    return build_component(
        score,
        context.get("source") or "NSE official participant-wise EOD OI · CLIENT Index Futures",
        source_date.isoformat(),
        weight,
        method="10 × (CLIENT Futures Long change − Short change) ÷ previous gross exposure; clamp −10..+10; orientation selected by prospective 14-session validation",
        validation_status="AUTO_PROMOTED_PROVISIONAL · 14-session all-index directional gate passed; continue monitoring",
        scope="shared market-wide CLIENT Futures aggregate; same input on NIFTY, SENSEX and BANKNIFTY; not index-specific",
        orientation=orientation,
        validation_window_sessions=MIN_SESSIONS,
        validation_anchor_date=promotion.get("anchor_date_exclusive"),
        validation_hit_rates={
            name: (promotion.get("index_checks") or {}).get(name, {}).get(orientation, {}).get("hit_rate_pct")
            for name in INDEX_NAMES
        },
        validation_wilson_lower_bounds={
            name: (promotion.get("index_checks") or {}).get(name, {}).get(orientation, {}).get("wilson_95_lower_pct")
            for name in INDEX_NAMES
        },
        not_index_specific=True,
        auto_promoted=True,
    )
