"""Offline diagnostics for archived NSE index-option and MCX commodity data.

This module reads committed archive JSON only. It makes no provider requests and
never produces a component score or changes production dashboard data.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from index_oi_expiry_research import build_report as build_index_oi_expiry_report
from nse_option_buildup import build_option_buildup_diagnostic, validate_option_buildup_diagnostic
from trinetra_test_components import option_buildup_test_component

NSE_PATH = Path("nse_index_option_oi.json")
CLOSE_PATH = Path("nse_index_close_archive.json")
MCX_PATH = Path("mcx_bhavcopy_archive.json")
OUTPUT_PATH = Path("archive-component-diagnostics.json")
MIN_VALIDATION_SESSIONS = 60


def _records(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise ValueError("archive must contain a records list")
    records = [row for row in payload["records"] if isinstance(row, dict)]
    return sorted(records, key=lambda row: str(row.get("date") or ""))


def summarize_nse(payload):
    records = _records(payload)
    assets = {}
    for symbol in ("NIFTY", "BANKNIFTY"):
        sessions = []
        previous_expiries = None
        matched_expiry_pairs = 0
        ce_oi = pe_oi = ce_change = pe_change = 0
        for record in records:
            item = (record.get("symbols") or {}).get(symbol)
            if not isinstance(item, dict):
                continue
            expiries = item.get("by_expiry") or {}
            current = set(expiries)
            if previous_expiries is not None:
                matched_expiry_pairs += len(current & previous_expiries)
            previous_expiries = current
            ce_rows = [v.get("CE") or {} for v in expiries.values()]
            pe_rows = [v.get("PE") or {} for v in expiries.values()]
            ce_oi += sum(int(x.get("open_interest") or 0) for x in ce_rows)
            pe_oi += sum(int(x.get("open_interest") or 0) for x in pe_rows)
            ce_change += sum(int(x.get("change_in_oi") or 0) for x in ce_rows)
            pe_change += sum(int(x.get("change_in_oi") or 0) for x in pe_rows)
            sessions.append({
                "date": record.get("date"),
                "contract_rows": int(item.get("contract_rows") or 0),
                "expiry_count": len(expiries),
                "ce_contracts": sum(int(x.get("contracts") or 0) for x in ce_rows),
                "pe_contracts": sum(int(x.get("contracts") or 0) for x in pe_rows),
                "ce_change_in_oi": sum(int(x.get("change_in_oi") or 0) for x in ce_rows),
                "pe_change_in_oi": sum(int(x.get("change_in_oi") or 0) for x in pe_rows),
            })
        count = len(sessions)
        assets[symbol] = {
            "source": "NSE India official F&O UDiFF Common Bhavcopy Final",
            "sessions": count,
            "dates": [x["date"] for x in sessions],
            "contract_rows_total": sum(x["contract_rows"] for x in sessions),
            "same_expiry_session_pairs": matched_expiry_pairs,
            "ce_open_interest_sum_across_snapshots": ce_oi,
            "pe_open_interest_sum_across_snapshots": pe_oi,
            "ce_change_in_oi_sum_across_expiries_and_sessions": ce_change,
            "pe_change_in_oi_sum_across_expiries_and_sessions": pe_change,
            "daily": sessions,
            "validation_status": "INSUFFICIENT_HISTORY" if count < MIN_VALIDATION_SESSIONS else "REQUIRES_HOLDOUT_TEST",
            "included_in_asset_final": False,
            "score": None,
        }
    return {
        "source": "NSE India official F&O UDiFF Common Bhavcopy Final",
        "assets": assets,
        "limitation": "NSE archive covers NIFTY and BANKNIFTY options only; it is not participant CLIENT category OI and is not SENSEX data.",
    }



def summarize_option_buildup(payload, min_classified=100):
    """Report the latest same-contract EOD premium/OI comparison per index.

    The score is archive-pair TEST research only. It is never eligible for an
    asset Final and is not a claim that the observation is live/current.
    """
    records = _records(payload)
    latest_date = str(records[-1].get("date") or "") if records else None
    assets = {}
    for symbol in ("NIFTY", "BANKNIFTY"):
        diagnostic = build_option_buildup_diagnostic(
            payload, symbol, as_of_date=latest_date,
            max_age_days=10000, min_matched_contracts=20,
            expected_source_date=None,
        )
        checked = validate_option_buildup_diagnostic(
            diagnostic, min_matched_contracts=20
        )
        component, reason = option_buildup_test_component(
            checked, latest_date, max_age_days=10000,
            min_classified=min_classified,
        ) if latest_date else (None, "archive में तारीख़ वाला EOD session नहीं")
        categories = {}
        for key, row in (checked.get("categories") or {}).items():
            if not isinstance(row, dict):
                continue
            categories[key] = {
                "contracts": row.get("contracts", 0),
                "oi_quantity": row.get("oi_quantity", 0),
                "ce_oi_quantity": row.get("ce_oi_quantity", 0),
                "pe_oi_quantity": row.get("pe_oi_quantity", 0),
            }
        assets[symbol] = {
            "source": checked.get("source") or "NSE F&O UDiFF Common Bhavcopy Final",
            "source_date": checked.get("source_date"),
            "previous_source_date": checked.get("previous_source_date"),
            "matched_contracts": checked.get("matched_contracts", 0),
            "classified_contracts": checked.get("classified_contracts", 0),
            "categories": categories,
            "integrity_validation": checked.get("integrity_validation"),
            "coverage_validated": False,
            "test_score": component.get("score") if component else None,
            "test_score_status": (
                "ARCHIVE_PAIR_TEST_ONLY_NOT_LIVE" if component
                else "UNAVAILABLE"
            ),
            "test_score_reason": reason or checked.get("reason"),
            "included_in_asset_final": False,
            "scope": "इस archive के नवीनतम same-expiry/strike/CE-PE EOD pair का diagnostic; live signal या validated predictor नहीं",
        }
    return {
        "source": "NSE India official F&O UDiFF Common Bhavcopy Final",
        "minimum_classified_contracts_for_test_score": min_classified,
        "assets": assets,
        "limitation": "यह archive pair का TEST-only ऐतिहासिक diagnostic है; coverage और predictive accuracy validated नहीं हैं।",
    }



def _normalise_index_name(value):
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def _index_close(record, symbol):
    indices = record.get("indices")
    if not isinstance(indices, dict):
        return None, None
    aliases = {"NIFTY": {"NIFTY50"}, "BANKNIFTY": {"NIFTYBANK", "BANKNIFTY"}}
    for name, value in indices.items():
        if _normalise_index_name(name) in aliases[symbol]:
            try:
                close = float(value)
            except (TypeError, ValueError, OverflowError):
                return name, None
            if close > 0:
                return name, close
    return None, None


def summarize_option_buildup_next_session(option_payload, close_payload, min_classified=100):
    """Walk-forward research: signal after EOD pair, compare next official index close."""
    option_records = _records(option_payload)
    close_records = _records(close_payload)
    close_dates = {}
    for row in close_records:
        try:
            day = dt.date.fromisoformat(str(row.get("date"))[:10])
        except (TypeError, ValueError):
            continue
        close_dates[day] = row

    assets = {}
    for symbol in ("NIFTY", "BANKNIFTY"):
        results = []
        counters = {
            "signals_available": 0, "matched_close_pairs": 0,
            "missing_same_day_close": 0, "missing_next_session_close": 0,
            "bullish_hits": 0, "bullish_misses": 0,
            "bearish_hits": 0, "bearish_misses": 0,
            "flat_or_zero_excluded": 0,
        }
        for index, row in enumerate(option_records):
            signal_date = str(row.get("date") or "")[:10]
            try:
                signal_day = dt.date.fromisoformat(signal_date)
            except ValueError:
                continue
            history = {"records": option_records[:index + 1]}
            diagnostic = build_option_buildup_diagnostic(
                history, symbol, as_of_date=signal_date,
                max_age_days=10000, min_matched_contracts=20,
                expected_source_date=None,
            )
            # Do not duplicate an older symbol signal on unrelated archive rows.
            if str(diagnostic.get("source_date") or "")[:10] != signal_date:
                continue
            component, reason = option_buildup_test_component(
                diagnostic, signal_date, max_age_days=10000,
                min_classified=min_classified,
            )
            if not component:
                continue
            counters["signals_available"] += 1
            baseline = close_dates.get(signal_day)
            if baseline is None:
                counters["missing_same_day_close"] += 1
                results.append({"signal_date": signal_date, "score": component["score"],
                                "status": "MISSING_SAME_DAY_CLOSE"})
                continue
            future_days = [day for day in close_dates if day > signal_day]
            if not future_days:
                counters["missing_next_session_close"] += 1
                results.append({"signal_date": signal_date, "score": component["score"],
                                "status": "MISSING_NEXT_SESSION_CLOSE"})
                continue
            next_day = min(future_days)
            base_name, base_close = _index_close(baseline, symbol)
            next_name, next_close = _index_close(close_dates[next_day], symbol)
            if base_close is None or next_close is None:
                counters["missing_same_day_close"] += 1
                results.append({"signal_date": signal_date, "score": component["score"],
                                "next_close_date": next_day.isoformat(),
                                "status": "INDEX_CLOSE_MISSING",
                                "index_key_same_day": base_name, "index_key_next_day": next_name})
                continue
            change_pct = (next_close / base_close - 1.0) * 100.0
            score = float(component["score"])
            outcome = "FLAT_OR_ZERO"
            if score > 0 and change_pct > 0:
                counters["bullish_hits"] += 1
                outcome = "HIT"
            elif score > 0 and change_pct < 0:
                counters["bullish_misses"] += 1
                outcome = "MISS"
            elif score < 0 and change_pct < 0:
                counters["bearish_hits"] += 1
                outcome = "HIT"
            elif score < 0 and change_pct > 0:
                counters["bearish_misses"] += 1
                outcome = "MISS"
            else:
                counters["flat_or_zero_excluded"] += 1
            counters["matched_close_pairs"] += 1
            results.append({
                "signal_date": signal_date, "next_session_date": next_day.isoformat(),
                "index_name": base_name or next_name, "same_day_close": base_close,
                "next_session_close": next_close, "next_session_return_pct": round(change_pct, 6),
                "score": round(score, 6), "outcome": outcome,
            })
        eligible = counters["bullish_hits"] + counters["bullish_misses"] + counters["bearish_hits"] + counters["bearish_misses"]
        hits = counters["bullish_hits"] + counters["bearish_hits"]
        assets[symbol] = {
            **counters, "directional_pairs": eligible, "directional_hits": hits,
            "directional_accuracy_pct": round(100.0 * hits / eligible, 2) if eligible else None,
            "validation_status": "RESEARCH_ONLY_MINIMUM_60_SESSIONS_NOT_MET" if eligible < MIN_VALIDATION_SESSIONS else "REQUIRES_PREDECLARED_HOLDOUT_REVIEW",
            "included_in_asset_final": False, "observations": results,
        }
    return {
        "source": "Offline NSE official F&O option archive + official daily index-close archive",
        "method": "Walk-forward: each signal uses only option EOD records up to that date; outcome uses same-day close to first later archived trading-session close.",
        "minimum_directional_pairs_for_review": MIN_VALIDATION_SESSIONS,
        "assets": assets,
        "external_requests_made": 0,
        "predictive_validation_passed": False,
        "limitation": "Exploratory historical directional check only; no predeclared holdout or transaction costs. Never eligible for production Final Score.",
    }



def summarize_mcx(payload):
    records = _records(payload)
    assets = {}
    for symbol in ("GOLD", "SILVER"):
        sessions = []
        previous = None
        observations = []
        for record in records:
            rows = [
                row for row in (record.get("contract_rows") or [])
                if isinstance(row, dict)
                and row.get("InstrumentName") == "FUTCOM"
                and row.get("Symbol") == symbol
            ]
            by_expiry = {str(row.get("ExpiryDate")): row for row in rows if row.get("ExpiryDate")}
            if previous is not None:
                shared = sorted(set(previous) & set(by_expiry))
                for expiry in shared:
                    old, new = previous[expiry], by_expiry[expiry]
                    old_oi, new_oi = int(old["OpenInterest"]), int(new["OpenInterest"])
                    old_close, new_close = float(old["Close"]), float(new["Close"])
                    oi_delta = new_oi - old_oi
                    close_return_pct = (new_close / old_close - 1.0) * 100.0
                    if close_return_pct > 0 and oi_delta > 0:
                        regime = "price_up_oi_up"
                    elif close_return_pct > 0 and oi_delta < 0:
                        regime = "price_up_oi_down"
                    elif close_return_pct < 0 and oi_delta > 0:
                        regime = "price_down_oi_up"
                    elif close_return_pct < 0 and oi_delta < 0:
                        regime = "price_down_oi_down"
                    else:
                        regime = "mixed_or_flat"
                    observations.append({
                        "from_date": previous_date,
                        "to_date": record.get("date"),
                        "expiry": expiry,
                        "oi_change": oi_delta,
                        "close_return_pct": round(close_return_pct, 6),
                        "regime": regime,
                    })
            previous = by_expiry
            previous_date = record.get("date")
            sessions.append({"date": record.get("date"), "contract_count": len(rows), "expiries": sorted(by_expiry)})
        count = len(sessions)
        assets[symbol] = {
            "source": "MCX India official date-wise Bhavcopy · FUTCOM",
            "sessions": count,
            "dates": [x["date"] for x in sessions],
            "contract_rows_total": sum(x["contract_count"] for x in sessions),
            "same_expiry_observations": len(observations),
            "observations": observations,
            "validation_status": "INSUFFICIENT_HISTORY" if count < MIN_VALIDATION_SESSIONS else "REQUIRES_HOLDOUT_TEST",
            "included_in_asset_final": False,
            "score": None,
            "scope": "Total commodity FUTCOM contract OI and close; not CLIENT-category OI",
        }
    return {
        "source": "MCX India official date-wise Bhavcopy · FUTCOM",
        "assets": assets,
        "limitation": "Same-expiry observations are descriptive diagnostics only; a small sample cannot establish predictive direction or justify a score.",
    }


def build_report(nse_payload, mcx_payload, generated_at=None, close_payload=None):
    stamp = generated_at or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    return {
        "report_version": 1,
        "mode": "offline_archive_component_diagnostics",
        "generated_at_utc": stamp,
        "external_requests_made": 0,
        "production_data_modified": False,
        "production_dashboard_score_changed": False,
        "minimum_sessions_for_validation": MIN_VALIDATION_SESSIONS,
        "nse_index_options": summarize_nse(nse_payload),
        "nse_option_buildup_test": summarize_option_buildup(nse_payload),
        "nse_option_buildup_next_session_research": summarize_option_buildup_next_session(nse_payload, close_payload) if close_payload is not None else {"status": "CLOSE_ARCHIVE_NOT_SUPPLIED", "predictive_validation_passed": False},
        "nse_index_expiry_research": build_index_oi_expiry_report(nse_payload),
        "mcx_commodity_futures": summarize_mcx(mcx_payload),
        "guardrail": "All archive-derived results remain diagnostic-only. No archive component is eligible for Final Score until sufficient dated history and out-of-sample directional validation pass.",
    }


def main():
    for path in (NSE_PATH, CLOSE_PATH, MCX_PATH):
        if not path.is_file():
            raise SystemExit(f"FAIL: required archive missing: {path}")
    nse_payload = json.loads(NSE_PATH.read_text(encoding="utf-8"))
    mcx_payload = json.loads(MCX_PATH.read_text(encoding="utf-8"))
    close_payload = json.loads(CLOSE_PATH.read_text(encoding="utf-8"))
    report = build_report(nse_payload, mcx_payload, close_payload=close_payload)
    OUTPUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    for group, data in (("NSE", report["nse_index_options"]["assets"]), ("MCX", report["mcx_commodity_futures"]["assets"])):
        for asset, item in data.items():
            print(f"{group} {asset}: sessions={item['sessions']} observations={item.get('same_expiry_observations', item.get('same_expiry_session_pairs', 0))} status={item['validation_status']} score=NONE")
    print(f"REPORT_READY {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
