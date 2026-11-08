"""Offline diagnostics for archived NSE index-option and MCX commodity data.

This module reads committed archive JSON only. It makes no provider requests and
never produces a component score or changes production dashboard data.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

NSE_PATH = Path("nse_index_option_oi.json")
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


def build_report(nse_payload, mcx_payload, generated_at=None):
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
        "mcx_commodity_futures": summarize_mcx(mcx_payload),
        "guardrail": "All archive-derived results remain diagnostic-only. No archive component is eligible for Final Score until sufficient dated history and out-of-sample directional validation pass.",
    }


def main():
    for path in (NSE_PATH, MCX_PATH):
        if not path.is_file():
            raise SystemExit(f"FAIL: required archive missing: {path}")
    nse_payload = json.loads(NSE_PATH.read_text(encoding="utf-8"))
    mcx_payload = json.loads(MCX_PATH.read_text(encoding="utf-8"))
    report = build_report(nse_payload, mcx_payload)
    OUTPUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\\n", encoding="utf-8")
    for group, data in (("NSE", report["nse_index_options"]["assets"]), ("MCX", report["mcx_commodity_futures"]["assets"])):
        for asset, item in data.items():
            print(f"{group} {asset}: sessions={item['sessions']} observations={item.get('same_expiry_observations', item.get('same_expiry_session_pairs', 0))} status={item['validation_status']} score=NONE")
    print(f"REPORT_READY {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
