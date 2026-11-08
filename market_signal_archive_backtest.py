"""Build an offline contrarian backtest from PDMP's dated EOD archive."""
import argparse
import json
from datetime import datetime, timezone
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


def _component_evidence_error(breakdown, final, market_day, snapshot_time):
    """Fail closed on missing, future-dated, or mathematically inconsistent evidence."""
    components = breakdown.get("components") if isinstance(breakdown, dict) else None
    included = final.get("included_components") if isinstance(final, dict) else None
    configured = breakdown.get("component_weights") if isinstance(breakdown, dict) else None
    normalized = final.get("normalized_weights_pct") if isinstance(final, dict) else None
    if not isinstance(components, dict) or not isinstance(included, list) or not included:
        return "component metadata or included-component list missing"
    if not isinstance(configured, dict) or not isinstance(normalized, dict):
        return "configured or normalized component weights missing"
    if len(set(included)) != len(included):
        return "duplicate component name in final"
    if set(included) != set(components):
        return "final included components do not match component evidence rows"

    weighted_total = 0.0
    weight_total = 0.0
    observed_weights = {}
    for name in included:
        component = components.get(name)
        if not isinstance(component, dict) or component.get("included") is not True:
            return f"{name}: component is not explicitly included"
        score = _number(component.get("score"))
        weight = _number(configured.get(name))
        component_weight = _number(component.get("weight"))
        source = component.get("source")
        source_day = _day(component.get("source_date"))
        raw_observed_at = component.get("observed_at")
        if (score is None or not -10 <= score <= 10 or weight is None or weight <= 0
                or component_weight is None or abs(component_weight - weight) > 0.0001
                or not isinstance(source, str) or not source.strip()
                or source_day is None or source_day > market_day
                or not isinstance(raw_observed_at, str)):
            return f"{name}: score, source, weight, or source date is invalid"
        try:
            component_time = datetime.fromisoformat(raw_observed_at.replace("Z", "+00:00"))
        except ValueError:
            return f"{name}: observation timestamp is invalid"
        if component_time.tzinfo is None:
            component_time = component_time.replace(tzinfo=timezone.utc)
        if component_time.astimezone(timezone.utc) > snapshot_time.astimezone(timezone.utc):
            return f"{name}: component observation is later than EOD snapshot"
        weighted_total += score * weight
        weight_total += weight
        observed_weights[name] = round(weight / sum(
            _number(configured.get(item)) for item in included
        ) * 100.0, 2)

    expected_score = weighted_total / weight_total if weight_total else None
    final_score = _number(final.get("score"))
    final_weight_total = _number(final.get("weight_total"))
    if expected_score is None or final_score is None or abs(expected_score - final_score) > 0.02:
        return "final score does not match weighted component evidence"
    if final_weight_total is None or abs(final_weight_total - weight_total) > 0.01:
        return "final weight total does not match component weights"
    if set(normalized) != set(observed_weights) or any(
        _number(normalized.get(name)) is None
        or abs(_number(normalized.get(name)) - expected) > 0.02
        for name, expected in observed_weights.items()
    ):
        return "normalized weights do not match component weights"
    return None


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
        "missing_component_final": 0,\n        "invalid_component_evidence": 0,
        "invalid_or_non_eod_snapshot": 0,
        "invalid_or_mismatched_close": 0,
        "assets_with_component_final": {},
        "latest_asset_evidence": {},
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

            # Keep a readable latest-per-asset evidence snapshot in the audit.
            # This is derived only from the committed archive and makes no provider calls.
            previous_evidence = audit["latest_asset_evidence"].get(asset)
            if previous_evidence is None or day_text > previous_evidence["date"]:
                latest_breakdown = row.get("component_breakdown")
                latest_final = (
                    latest_breakdown.get("final")
                    if isinstance(latest_breakdown, dict) else None
                )
                latest_coverage = (
                    latest_breakdown.get("coverage")
                    if isinstance(latest_breakdown, dict) else None
                )
                latest_components = {}
                raw_components = (
                    latest_breakdown.get("components")
                    if isinstance(latest_breakdown, dict) else None
                )
                if isinstance(raw_components, dict):
                    for component_name, component in raw_components.items():
                        if not isinstance(component, dict):
                            continue
                        latest_components[component_name] = {
                            "score": _number(component.get("score")),
                            "source": component.get("source"),
                            "source_date": component.get("source_date"),
                            "observed_at": component.get("observed_at"),
                            "evidence_count": component.get("evidence_count"),
                        }
                raw_excluded = (
                    latest_breakdown.get("excluded_components")
                    if isinstance(latest_breakdown, dict) else None
                )
                latest_excluded = {}
                if isinstance(raw_excluded, dict):
                    latest_excluded = {
                        key: {
                            "source": value.get("source"),
                            "reason": value.get("reason"),
                        }
                        for key, value in raw_excluded.items()
                        if isinstance(value, dict)
                    }
                latest_score = (
                    _number(latest_final.get("score"))
                    if isinstance(latest_final, dict)
                    and latest_final.get("status") == "available" else None
                )
                audit["latest_asset_evidence"][asset] = {
                    "date": day_text,
                    "captured_at_ist": record.get("captured_at_ist"),
                    "component_status": "available" if latest_score is not None else "missing",
                    "final_score": latest_score,
                    "included_components": (
                        latest_final.get("included_components")
                        if isinstance(latest_final, dict) else []
                    ),
                    "coverage": {
                        key: latest_coverage.get(key)
                        for key in ("status", "included_count", "applicable_count", "coverage_pct")
                    } if isinstance(latest_coverage, dict) else None,
                    "components": latest_components,
                    "excluded_components": latest_excluded,
                }

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
