"""Offline, one-batch verification of the five asset component-score snapshots.

Reads the committed data.json only. It does not call Google Trends, NSE, Yahoo,
BSE, MCX, RSS, or any other network source, and never changes data.json.
"""
import datetime as dt
import json
from pathlib import Path

import component_scoring
import fetch_and_score

ASSETS = ("NIFTY", "SENSEX", "BANKNIFTY", "GOLD", "SILVER")
INPUT = Path("data.json")
OUTPUT = Path("component-score-consolidated-verification.json")



SEARCH_ASSETS = {"NIFTY": ("index_search_shadow", "nifty"), "SENSEX": ("index_search_shadow", "sensex"), "BANKNIFTY": ("index_search_shadow", "bank nifty"), "GOLD": ("asset_search_shadow", "gold price"), "SILVER": ("asset_search_shadow", "silver price")}

def summarize_asset_search(asset, instrument, now_utc):
    field, expected = SEARCH_ASSETS[asset]
    snap = instrument.get(field) if isinstance(instrument, dict) else None
    if not isinstance(snap, dict):
        return {"status": "MISSING", "field": field, "expected_seed": expected, "reason": "asset-specific snapshot missing"}
    actual = str(snap.get("seed") or "").strip().lower()
    stamp = snap.get("source_data_time") or snap.get("as_of")
    fresh = component_scoring.is_fresh_timestamp(stamp, now_utc, max_age_minutes=360)
    bull = component_scoring.finite_number(snap.get("bull_pct"))
    bear = component_scoring.finite_number(snap.get("bear_pct"))
    neutral = component_scoring.finite_number(snap.get("neutral_pct"))
    directional = component_scoring.finite_number(snap.get("directional_bull_pct"))
    if actual != expected:
        status, reason = "SEED_MISMATCH", "cross-asset seed rejected"
    elif not snap.get("valid"):
        status, reason = "INVALID", snap.get("reason") or "source marked invalid"
    elif not fresh:
        status, reason = "STALE_OR_INVALID_TIMESTAMP", "observation is not fresh"
    elif directional is None or (bull == 0 and bear == 0):
        status, reason = "NEUTRAL_ONLY", "no directional evidence; excluded from Search Final"
    else:
        status, reason = "DIRECTIONAL_EVIDENCE_PRESENT", "directional evidence exists; score eligibility checked separately"
    return {"status": status, "field": field, "expected_seed": expected, "actual_seed": actual or None, "source": snap.get("source"), "timeframe": snap.get("timeframe"), "source_data_time": stamp, "fresh": bool(fresh), "classification_coverage_pct": component_scoring.finite_number(snap.get("classification_coverage_pct")), "bull_pct": bull, "bear_pct": bear, "neutral_pct": neutral, "directional_bull_pct": directional, "classified_queries": snap.get("classified_queries"), "raw_queries": snap.get("raw_queries"), "in_scope_queries": snap.get("in_scope_queries"), "out_of_scope_queries": snap.get("out_of_scope_queries"), "out_of_scope_weight": snap.get("out_of_scope_weight"), "reason": reason}


def main():
    if not INPUT.is_file():
        raise SystemExit("FAIL: data.json is missing")
    with INPUT.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    instruments = data.get("instruments")
    if not isinstance(instruments, dict):
        raise SystemExit("FAIL: data.json instruments object is missing")
    missing_assets = [asset for asset in ASSETS if not isinstance(instruments.get(asset), dict)]
    if missing_assets:
        raise SystemExit("FAIL: missing asset snapshots: " + ", ".join(missing_assets))

    now = dt.datetime.now(dt.timezone.utc)
    scan_time = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    participant = data.get("participant_oi") or {}
    method = fetch_and_score.build_asset_component_breakdowns(
        instruments,
        scan_time,
        now,
        participant,
        participant.get("changes"),
    )

    report_assets = {}
    failures = []
    for asset in ASSETS:
        breakdown = instruments[asset].get("component_breakdown") or {}
        components = breakdown.get("components") or {}
        final = breakdown.get("final") or {}
        included = {}
        for name, component in components.items():
            if not isinstance(component, dict):
                failures.append(f"{asset}.{name}: malformed included component")
                continue
            score = component_scoring.clamp_score(component.get("score"))
            source = component.get("source")
            source_date = component.get("source_date")
            weight = component_scoring.finite_number(component.get("weight"))
            valid = (
                score is not None
                and isinstance(source, str) and bool(source.strip())
                and isinstance(source_date, str) and bool(source_date.strip())
                and weight is not None and weight > 0
                and component.get("included") is True
            )
            if not valid:
                failures.append(f"{asset}.{name}: included component lacks valid score/source/date/weight")
            included[name] = {
                "status": "VERIFIED" if valid else "INVALID",
                "score": score,
                "source": source,
                "source_date": source_date,
                "weight": weight,
            }

        independently_combined = component_scoring.combine_components(
            components, breakdown.get("component_weights")
        )
        if independently_combined != final:
            failures.append(f"{asset}: Final Score does not match independent weighted recomputation")

        normalized = final.get("normalized_weights_pct") or {}
        if final.get("status") == "available" and (
            not normalized or abs(sum(normalized.values()) - 100.0) > 0.03
        ):
            failures.append(f"{asset}: normalized included weights do not sum to 100%")

        excluded = breakdown.get("excluded_components") or {}
        report_assets[asset] = {
            "status": "SCORED" if final.get("status") == "available" else "DATA_MISSING",
            "final_score": final.get("score"),
            "final_status": final.get("status", "unavailable"),
            "included_components": included,
            "excluded_components": excluded,
            "normalized_weights_pct": normalized,
            "included_component_count": len(included),
            "excluded_component_count": len(excluded),
            "search_evidence_audit": summarize_asset_search(asset, instruments[asset], now),
        }

    report = {
        "report_version": 1,
        "mode": "offline_consolidated_five_asset_verification",
        "verification_time_utc": scan_time,
        "input_file": str(INPUT),
        "input_data_updated": data.get("updated"),
        "assets_checked": list(ASSETS),
        "external_requests_made": 0,
        "production_data_modified": False,
        "production_dashboard_score_changed": False,
        "component_method": method,
        "summary": {
            "assets_checked": len(ASSETS),
            "assets_with_final_score": sum(1 for item in report_assets.values() if item["status"] == "SCORED"),
            "assets_without_final_score": sum(1 for item in report_assets.values() if item["status"] != "SCORED"),
            "component_integrity_failures": failures,
            "integrity_result": "PASS" if not failures else "FAIL",
            "completion_status": (
                "COMPLETE" if not failures and all(
                    item["status"] == "SCORED"
                    and item["excluded_component_count"] == 0
                    for item in report_assets.values()
                ) else "PARTIAL" if not failures else "BLOCKED"
            ),
        },
        "assets": report_assets,
        "limitations": [
            "यह रिपोर्ट committed data.json snapshot का offline सत्यापन है; यह नया market-data refresh नहीं करती।",
            "Unavailable या unvalidated components को Final Score में नहीं जोड़ा जाता।",
            "Market-wide CLIENT participant OI को किसी एक index का OI score नहीं माना जाता।",
            "Shadow Final Score को live trading recommendation नहीं माना जाए।",
        ],
    }
    with OUTPUT.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)

    print("CONSOLIDATED_COMPONENT_VERIFICATION")
    for asset, item in report_assets.items():
        print(
            f"{asset}: {item['status']} final={item['final_score']} "
            f"included={item['included_component_count']} "
            f"excluded={item['excluded_component_count']}"
        )
        for name, component in item["included_components"].items():
            print(
                f"  {name}: {component['status']} score={component['score']} "
                f"source={component['source']} date={component['source_date']}"
            )
    print("SUMMARY", json.dumps(report["summary"], ensure_ascii=False))
    print("COMPLETION_STATUS", report["summary"]["completion_status"])
    print(f"REPORT_READY {OUTPUT}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
