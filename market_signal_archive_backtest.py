"""Build an offline contrarian backtest from PDMP's dated EOD archive."""
import argparse
import json
from datetime import datetime
from pathlib import Path

from offline_contrarian_market_backtest import _day, _number, run_contrarian_backtest


ASSETS = ("NIFTY", "SENSEX", "BANKNIFTY", "GOLD", "SILVER")


def _eod_snapshot_time(record, market_day):
    raw = record.get("captured_at_ist")
    if not isinstance(raw, str):
        return None
    try:
        stamp = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if stamp.date().isoformat() != market_day or stamp.hour * 60 + stamp.minute < 15 * 60 + 30:
        return None
    return stamp


def _asset_record(record, asset):
    if asset in ("NIFTY", "SENSEX", "BANKNIFTY"):
        return (record.get("indices") or {}).get(asset)
    return (record.get("other_assets") or {}).get(asset)


def build_archive_inputs(archive):
    """Extract only dated, EOD, per-asset component-final signals and matched closes.

    Published production scores are deliberately not used as a fallback. The
    backtest is specifically for the independently verified component score.
    """
    records = archive.get("records") if isinstance(archive, dict) else None
    if not isinstance(records, list):
        raise ValueError("archive must contain a records list")

    signals, closes = [], []
    audit = {
        "archive_records": len(records),
        "assets_considered": list(ASSETS),
        "signals_added": 0,
        "closes_added": 0,
        "missing_component_final": 0,
        "invalid_or_non_eod_snapshot": 0,
        "invalid_or_mismatched_close": 0,
        "assets_with_component_final": {},
    }

    for record in records:
        if not isinstance(record, dict):
            continue
        market_day = _day(record.get("date"))
        if market_day is None:
            audit["invalid_or_non_eod_snapshot"] += 1
            continue
        day_text = market_day.isoformat()
        observed = _eod_snapshot_time(record, day_text)
        if observed is None:
            audit["invalid_or_non_eod_snapshot"] += 1
            continue

        for asset in ASSETS:
            row = _asset_record(record, asset)
            if not isinstance(row, dict):
                continue
            breakdown = row.get("component_breakdown")
            final = breakdown.get("final") if isinstance(breakdown, dict) else None
            coverage = breakdown.get("coverage") if isinstance(breakdown, dict) else None
            score = _number(final.get("score")) if isinstance(final, dict) and final.get("status") == "available" else None
            included = final.get("included_components") if isinstance(final, dict) else None
            if (score is None or not isinstance(included, list) or not included
                    or not isinstance(coverage, dict)
                    or coverage.get("included_count", 0) < 1):
                audit["missing_component_final"] += 1
                continue

            signals.append({
                "asset": asset,
                "signal_date": day_text,
                "known_on": day_text,
                "score": score,
                "source": "PDMP per-asset verified component final; included=" + ",".join(included),
                "observed_at": observed.isoformat(),
            })
            audit["signals_added"] += 1
            audit["assets_with_component_final"][asset] = audit["assets_with_component_final"].get(asset, 0) + 1

            close = _number(row.get("close"))
            close_day = _day(row.get("close_as_of"))
            close_valid = row.get("close_valid") is not False
            price_source = row.get("price_source") or record.get("price_source_note") or "dated PDMP EOD archive"
            if close is None or close <= 0 or close_day != market_day or not close_valid or not isinstance(price_source, str):
                audit["invalid_or_mismatched_close"] += 1
                continue
            closes.append({
                "asset": asset,
                "market_date": day_text,
                "close": close,
                "source": price_source,
            })
            audit["closes_added"] += 1

    return signals, closes, audit


def run_archive_backtest(archive, threshold=1.0):
    signals, closes, audit = build_archive_inputs(archive)
    report = run_contrarian_backtest(signals, closes, threshold=threshold)
    report["archive_audit"] = audit
    report["signal_source_policy"] = (
        "Only component_breakdown.final.score from dated EOD snapshots; "
        "published production score is never substituted."
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", default="market_signal_history.json")
    parser.add_argument("--threshold", type=float, default=1.0)
    parser.add_argument("--out", default="contrarian_backtest_report.json")
    args = parser.parse_args()
    archive = json.loads(Path(args.archive).read_text(encoding="utf-8"))
    report = run_archive_backtest(archive, threshold=args.threshold)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "report": args.out,
        "sample_count": report["summary"]["sample_count"],
        "contrarian_accuracy_pct": report["summary"]["contrarian_accuracy_pct"],
        "crowd_follow_accuracy_pct": report["summary"]["crowd_follow_accuracy_pct"],
        "archive_audit": report["archive_audit"],
        "provider_calls": report["provider_calls"],
        "production_score_modified": report["production_score_modified"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
