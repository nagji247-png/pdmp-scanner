#!/usr/bin/env python3
"""Create a compact, auditable view of the exploratory participant-OI backtest."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "participant_oi_backtest.json"
OUTPUT = ROOT / "participant_oi_backtest_summary.json"

TRAIN = "train_first_70pct"
HOLDOUT = "chronological_holdout_last_30pct"
BASE_FIELDS = (
    "n", "avg_forward_return_pct", "positive_return_rate_pct",
    "pearson_r", "spearman_r",
)
DIRECTIONAL_FIELDS = (
    "signal_coverage_pct", "directional_signal_count",
    "directional_observation_count", "correct_signals", "false_signals",
    "false_bullish_signals", "false_bearish_signals",
    "false_signal_rate_pct", "directional_hit_rate_pct",
    "bullish_signal_avg_return_pct", "bearish_signal_avg_return_pct",
    "bull_bear_return_spread_pct",
)
REGIME_DIRECTIONAL_FIELDS = (
    "n", "directional_observation_count", "directional_hit_rate_pct",
    "false_signals", "false_signal_rate_pct", "avg_forward_return_pct",
)


def metric_view(item, directional, regime=False):
    if item is None:
        return None
    fields = BASE_FIELDS
    if directional:
        fields += REGIME_DIRECTIONAL_FIELDS[1:] if regime else DIRECTIONAL_FIELDS
    return {key: item.get(key) for key in fields}


def summarize_index(name, index):
    raw_metrics = index.get("metrics")
    if not isinstance(raw_metrics, list):
        raise ValueError(f"{name}: metrics list missing")

    grouped = {}
    for item in raw_metrics:
        if not isinstance(item, dict):
            continue
        feature = item.get("feature")
        horizon = item.get("horizon_sessions")
        sample = item.get("sample")
        if not isinstance(feature, str) or not isinstance(horizon, int):
            continue
        if sample not in (TRAIN, HOLDOUT):
            continue
        grouped.setdefault((feature, horizon), {})[sample] = item

    features = []
    for (feature, horizon), samples in sorted(grouped.items()):
        holdout = samples.get(HOLDOUT)
        if not holdout:
            continue
        train = samples.get(TRAIN)
        field = holdout.get("field") or feature.split(".", 1)[-1]
        is_directional = field.startswith("future_index")
        raw_regimes = holdout.get("regime_metrics") or {}
        regimes = {
            regime: metric_view(metrics, is_directional, regime=True)
            for regime, metrics in raw_regimes.items()
            if isinstance(metrics, dict)
        }
        features.append({
            "feature": feature,
            "participant": holdout.get("participant") or feature.split(".", 1)[0],
            "field": field,
            "horizon_sessions": horizon,
            "directional_futures": is_directional,
            "train": metric_view(train, is_directional),
            "holdout": metric_view(holdout, is_directional),
            "holdout_regimes": regimes,
        })

    futures = [
        item for item in features
        if item["directional_futures"]
        and item["holdout"].get("directional_hit_rate_pct") is not None
    ]
    futures.sort(
        key=lambda item: (
            item["holdout"].get("directional_hit_rate_pct", -1),
            item["holdout"].get("directional_observation_count", 0),
        ),
        reverse=True,
    )

    quality_fields = (
        "symbol", "price_source", "ohlc_sessions", "ohlc_first_date",
        "ohlc_last_date", "duplicate_ohlc_dates", "invalid_ohlc_rows",
        "price_sessions_in_oi_date_range", "oi_dates_matching_price_calendar",
        "missing_oi_sessions_inside_price_range", "missing_oi_dates_sample",
        "oi_dates_without_price", "oi_dates_without_price_sample",
        "oi_to_price_date_match_pct", "aligned_oi_dates",
        "nonconsecutive_oi_pairs_skipped", "unmatched_oi_pairs_skipped",
        "aligned_first_date", "aligned_last_date",
        "regime_counts_on_aligned_dates", "regime_definition",
        "target_definition", "false_signal_definition",
    )
    return {
        "symbol": index.get("symbol"),
        "data_quality": {key: index.get(key) for key in quality_fields},
        "feature_horizon_count": len(features),
        "features": features,
        "best_holdout_futures_exploratory_only": [
            {
                "feature": item["feature"],
                "horizon_sessions": item["horizon_sessions"],
                "n": item["holdout"].get("n"),
                "directional_observation_count": item["holdout"].get("directional_observation_count"),
                "hit_rate_pct": item["holdout"].get("directional_hit_rate_pct"),
                "false_signal_rate_pct": item["holdout"].get("false_signal_rate_pct"),
                "false_signals": item["holdout"].get("false_signals"),
            }
            for item in futures[:5]
        ],
    }


def build_summary(report):
    status = report.get("status", "unavailable")
    base = {
        "schema_version": 2,
        "summary_format": "compact_v2",
        "status": status,
        "generated_at_utc": report.get("generated_at_utc"),
        "oi_source": report.get("oi_source"),
        "oi_scope_warning": report.get("oi_scope_warning"),
        "oi_sessions": report.get("oi_sessions"),
        "oi_first_date": report.get("oi_first_date"),
        "oi_last_date": report.get("oi_last_date"),
        "archive_validation": report.get("archive_validation"),
        "data_adequacy": report.get("data_adequacy"),
        "validation": report.get("validation"),
        "score_changed": False,
        "eligible_for_live_score": False,
        "indices": {},
        "index_errors": report.get("index_errors") or {},
    }
    if status != "exploratory_only":
        base["reason"] = report.get("reason") or "Detailed OI report is not in exploratory_only state"
        return base

    indices = report.get("indices")
    if not isinstance(indices, dict) or not indices:
        raise ValueError("exploratory OI report has no index results")
    for name, index in indices.items():
        if not isinstance(index, dict):
            base["index_errors"][name] = "index result is not an object"
            continue
        base["indices"][name] = summarize_index(name, index)
    if not base["indices"]:
        raise ValueError("no valid index metrics could be summarized")
    return base


def main():
    if not INPUT.exists():
        raise FileNotFoundError(f"missing input report: {INPUT}")
    report = json.loads(INPUT.read_text(encoding="utf-8"))
    summary = build_summary(report)
    encoded = json.dumps(
        summary, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )
    OUTPUT.write_text(encoded + "\n", encoding="utf-8")
    counts = ", ".join(
        f"{name}={item['feature_horizon_count']} feature/horizon rows"
        for name, item in summary.get("indices", {}).items()
    ) or "no index metrics"
    print(
        f"OI compact summary written: status={summary['status']}; "
        f"bytes={len(encoded.encode('utf-8'))}; {counts}"
    )


if __name__ == "__main__":
    main()
