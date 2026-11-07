"""Run only the five-asset Google Trends shadow component check.

This intentionally reads the latest committed data.json snapshot and does not
refresh Yahoo, NSE, BSE, MCX, news, stock quotes, or the production dashboard.
The generated artifact is separate from data.json and is never published.
"""
import datetime as dt
import json
from pathlib import Path

import fetch_and_score as scanner

ASSETS = {
    "NIFTY": "index_search_shadow",
    "SENSEX": "index_search_shadow",
    "BANKNIFTY": "index_search_shadow",
    "GOLD": "asset_search_shadow",
    "SILVER": "asset_search_shadow",
}
SOURCE_PATH = Path("data.json")
OUTPUT_PATH = Path("component-score-live-shadow.json")


def main():
    if not SOURCE_PATH.is_file():
        raise SystemExit("Committed data.json snapshot is missing; refusing to run a full quote scan.")

    with SOURCE_PATH.open("r", encoding="utf-8") as handle:
        baseline = json.load(handle)
    instruments = baseline.get("instruments")
    if not isinstance(instruments, dict) or not instruments:
        raise SystemExit("data.json has no instrument snapshot; refusing to run a full quote scan.")

    now_utc = dt.datetime.now(dt.timezone.utc)
    scan_time = now_utc.isoformat(timespec="seconds").replace("+00:00", "Z")

    # Exactly one batched Trends payload for all five independent asset seeds.
    search_results = scanner.fetch_asset_trends_shadow()
    for asset, field in ASSETS.items():
        instrument = instruments.get(asset)
        if isinstance(instrument, dict):
            instrument[field] = search_results.get(asset) or {
                "valid": False,
                "seed": {
                    "NIFTY": "nifty",
                    "SENSEX": "sensex",
                    "BANKNIFTY": "bank nifty",
                    "GOLD": "gold price",
                    "SILVER": "silver price",
                }[asset],
                "timeframe": "now 1-d",
                "reason": "No asset-specific result returned by the single Trends batch",
                "production_score_used": False,
            }

    participant = baseline.get("participant_oi") or {}
    method = scanner.build_asset_component_breakdowns(
        instruments,
        scan_time,
        now_utc,
        participant,
        participant.get("changes"),
    )

    output_instruments = {}
    for asset, field in ASSETS.items():
        item = instruments.get(asset) or {}
        output_instruments[asset] = {
            "search_field": field,
            "search": item.get(field),
            "component_breakdown": item.get("component_breakdown"),
        }

    payload = {
        "mode": "isolated_five_asset_component_shadow",
        "scan_time": scan_time,
        "baseline_data_updated": baseline.get("updated"),
        "baseline_source": "repository data.json snapshot; read-only",
        "google_trends_requests": "one batched five-seed request",
        "other_market_data_requests": 0,
        "published_dashboard_score_changed": False,
        "component_score_method": method,
        "instruments": output_instruments,
    }
    with OUTPUT_PATH.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)

    for asset, item in output_instruments.items():
        search = item.get("search") or {}
        breakdown = item.get("component_breakdown") or {}
        print(
            f"SHADOW {asset}: search_valid={search.get('valid')} "
            f"classified={search.get('classified_queries')} "
            f"bull={search.get('bull_pct')} bear={search.get('bear_pct')} "
            f"neutral={search.get('neutral_pct')} "
            f"final={breakdown.get('final', {}).get('score') if isinstance(breakdown.get('final'), dict) else None}"
        )
    print(f"SHADOW_ARTIFACT_READY {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
