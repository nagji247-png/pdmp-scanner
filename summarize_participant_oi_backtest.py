#!/usr/bin/env python3
"""Create a compact, auditable view of the exploratory participant-OI backtest."""
from __future__ import annotations

import json
import math
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
    "contrarian_correct_signals", "contrarian_false_signals",
    "contrarian_hit_rate_pct", "contrarian_false_signal_rate_pct",
    "bullish_signal_avg_return_pct", "bearish_signal_avg_return_pct",
    "bull_bear_return_spread_pct",
)
REGIME_DIRECTIONAL_FIELDS = (
    "n", "directional_observation_count", "directional_hit_rate_pct",
    "contrarian_correct_signals", "contrarian_false_signals",
    "contrarian_hit_rate_pct", "contrarian_false_signal_rate_pct",
    "false_signals", "false_signal_rate_pct", "avg_forward_return_pct",
)
WILSON_Z_95 = 1.959963984540054


def metric_view(item, directional, regime=False):
    if item is None:
        return None
    fields = BASE_FIELDS
    if directional:
        fields += REGIME_DIRECTIONAL_FIELDS[1:] if regime else DIRECTIONAL_FIELDS
    return {key: item.get(key) for key in fields}


def wilson_interval(successes, trials, z=WILSON_Z_95):
    """Return a two-sided Wilson score interval as percentages."""
    if (
        not isinstance(successes, int) or isinstance(successes, bool)
        or not isinstance(trials, int) or isinstance(trials, bool)
        or trials <= 0 or successes < 0 or successes > trials
    ):
        return None
    proportion = successes / trials
    z2 = z * z
    denominator = 1.0 + z2 / trials
    center = (proportion + z2 / (2.0 * trials)) / denominator
    margin = (
        z * math.sqrt(
            proportion * (1.0 - proportion) / trials
            + z2 / (4.0 * trials * trials)
        ) / denominator
    )
    return (
        max(0.0, (center - margin) * 100.0),
        min(100.0, (center + margin) * 100.0),
    )


def exact_binomial_two_sided_pvalue(successes, trials):
    """Exact two-sided binomial p-value for H0: directional hit probability = 0.5."""
    if (
        not isinstance(successes, int) or isinstance(successes, bool)
        or not isinstance(trials, int) or isinstance(trials, bool)
        or trials <= 0 or successes < 0 or successes > trials
    ):
        return None
    tail = min(successes, trials - successes)
    probability = math.fsum(
        math.comb(trials, value) for value in range(tail + 1)
    ) / (2 ** trials)
    return min(1.0, 2.0 * probability)


def holm_adjust_pvalues(pvalues):
    """Holm step-down family-wise correction; accepts {key: raw_p_value}."""
    valid = [
        (key, float(value))
        for key, value in pvalues.items()
        if isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and 0.0 <= float(value) <= 1.0
    ]
    valid.sort(key=lambda item: item[1])
    family_size = len(valid)
    adjusted = {}
    running_max = 0.0
    for rank, (key, value) in enumerate(valid):
        candidate = min(1.0, (family_size - rank) * value)
        running_max = max(running_max, candidate)
        adjusted[key] = running_max
    return adjusted


def attach_directional_inference(features):
    """Add exploratory confidence intervals to explicitly directional futures/options features."""
    raw_pvalues = {}
    prepared = {}
    for position, item in enumerate(features):
        if not (item.get("directional_futures") or item.get("directional_options")):
            continue
        holdout = item.get("holdout") or {}
        trials = holdout.get("directional_observation_count")
        correct = holdout.get("correct_signals")
        false = holdout.get("false_signals")
        key = str(position)
        valid_counts = (
            isinstance(trials, int) and not isinstance(trials, bool)
            and isinstance(correct, int) and not isinstance(correct, bool)
            and isinstance(false, int) and not isinstance(false, bool)
            and trials > 0 and correct >= 0 and false >= 0
            and correct + false == trials
        )
        interval = wilson_interval(correct, trials) if valid_counts else None
        pvalue = (
            exact_binomial_two_sided_pvalue(correct, trials)
            if valid_counts else None
        )
        if pvalue is not None:
            raw_pvalues[key] = pvalue
        prepared[key] = {
            "interval": interval,
            "pvalue": pvalue,
            "trials": trials if valid_counts else None,
        }

    adjusted = holm_adjust_pvalues(raw_pvalues)
    family_size = len(raw_pvalues)
    for position, item in enumerate(features):
        key = str(position)
        evidence = prepared.get(key)
        if evidence is None:
            continue
        adjusted_p = adjusted.get(key)
        interval = evidence["interval"]
        item["statistical_evidence"] = {
            "hit_rate_ci95_pct": (
                [round(interval[0], 2), round(interval[1], 2)]
                if interval is not None else None
            ),
            "p_value_vs_50pct_two_sided_nominal": (
                round(evidence["pvalue"], 8)
                if evidence["pvalue"] is not None else None
            ),
            "holm_adjusted_p_value_nominal": (
                round(adjusted_p, 8) if adjusted_p is not None else None
            ),
            "holm_family_size": family_size,
            "nominal_holm_p_below_05": (
                adjusted_p < 0.05 if adjusted_p is not None else False
            ),
        }


def attach_magnitude_threshold_inference(indices):
    """Add uncertainty and one global Holm correction to every holdout threshold test.

    A PDMP hit is a crowd-follow miss. Thresholds are learned on training data
    and evaluated once on chronological holdout data. Tests remain exploratory:
    indexes share the same market-wide CLIENT OI input and horizons overlap.
    """
    raw_pvalues = {}
    prepared = {}
    for asset, index in indices.items():
        for position, item in enumerate(index.get("client_option_quantity_magnitude_thresholds", [])):
            n = item.get("holdout_selected_observations")
            hits = item.get("pdmp_contrarian_correct_signals")
            if (
                isinstance(n, int) and not isinstance(n, bool) and n > 0
                and isinstance(hits, int) and not isinstance(hits, bool)
                and 0 <= hits <= n
            ):
                key = f"{asset}:{position}"
                prepared[key] = {
                    "interval": wilson_interval(hits, n),
                    "pvalue": exact_binomial_two_sided_pvalue(hits, n),
                    "n": n,
                    "hits": hits,
                }
                raw_pvalues[key] = prepared[key]["pvalue"]

    adjusted = holm_adjust_pvalues(raw_pvalues)
    family_size = len(raw_pvalues)
    for asset, index in indices.items():
        for position, item in enumerate(index.get("client_option_quantity_magnitude_thresholds", [])):
            key = f"{asset}:{position}"
            evidence = prepared.get(key)
            if evidence is None:
                item["statistical_evidence"] = {
                    "pdmp_hit_rate_ci95_pct": None,
                    "p_value_vs_50pct_two_sided": None,
                    "holm_adjusted_p_value": None,
                    "holm_family_size": family_size,
                    "nominal_holm_p_below_05": False,
                }
                continue
            interval = evidence["interval"]
            adjusted_p = adjusted.get(key)
            item["pdmp_contrarian_correct_signals"] = evidence["hits"]
            item["pdmp_contrarian_hit_rate_pct"] = round(
                evidence["hits"] / evidence["n"] * 100.0, 2
            )
            item["statistical_evidence"] = {
                "pdmp_hit_rate_ci95_pct": (
                    [round(interval[0], 2), round(interval[1], 2)]
                    if interval is not None else None
                ),
                "p_value_vs_50pct_two_sided": round(evidence["pvalue"], 8),
                "holm_adjusted_p_value": (
                    round(adjusted_p, 8) if adjusted_p is not None else None
                ),
                "holm_family_size": family_size,
                "nominal_holm_p_below_05": (
                    adjusted_p < 0.05 if adjusted_p is not None else False
                ),
            }


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
        is_directional = field.startswith("future_index") or field == "index_option_directional_net_quantity"
        is_directional_futures = field.startswith("future_index")
        is_directional_options = field == "index_option_directional_net_quantity"
        raw_regimes = holdout.get("regime_metrics") or {}
        regimes = {
            regime: metric_view(metrics, is_directional, regime=True)
            for regime, metrics in raw_regimes.items()
            if isinstance(metrics, dict)
        }
        raw_phases = holdout.get("non_overlapping_holdout_phases") or []
        phase_views = []
        for phase in raw_phases:
            if not isinstance(phase, dict):
                continue
            phase_views.append({
                "phase_offset_sessions": phase.get("phase_offset_sessions"),
                "anchor_signal_date": phase.get("anchor_signal_date"),
                "n": phase.get("n"),
                "directional_observation_count": phase.get("directional_observation_count"),
                "correct_signals": phase.get("correct_signals"),
                "false_signals": phase.get("false_signals"),
                "false_signal_rate_pct": phase.get("false_signal_rate_pct"),
                "directional_hit_rate_pct": phase.get("directional_hit_rate_pct"),
                "contrarian_correct_signals": phase.get("contrarian_correct_signals"),
                "contrarian_false_signals": phase.get("contrarian_false_signals"),
                "contrarian_hit_rate_pct": phase.get("contrarian_hit_rate_pct"),
                "contrarian_false_signal_rate_pct": phase.get("contrarian_false_signal_rate_pct"),
                "avg_forward_return_pct": phase.get("avg_forward_return_pct"),
            })
        features.append({
            "feature": feature,
            "participant": holdout.get("participant") or feature.split(".", 1)[0],
            "field": field,
            "horizon_sessions": horizon,
            "directional_futures": is_directional_futures,
            "directional_options": is_directional_options,
            "train": metric_view(train, is_directional),
            "holdout": metric_view(holdout, is_directional),
            "holdout_regimes": regimes,
            "non_overlapping_holdout_phases": phase_views,
        })

    attach_directional_inference(features)
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
        "non_overlapping_holdout_method",
    )
    return {
        "symbol": index.get("symbol"),
        "data_quality": {key: index.get(key) for key in quality_fields},
        "feature_horizon_count": len(features),
        "directional_inference": {
            "confidence_interval": "95% Wilson score interval",
            "chance_test": "exact two-sided binomial test against 50% directional hit rate",
            "multiple_testing": (
                "Holm family-wise correction across all explicitly directional "
                "futures and CLIENT option quantity participant/field/horizon tests"
            ),
            "family_size": sum(
                1 for item in features
                if (item.get("directional_futures") or item.get("directional_options"))
                and (item.get("statistical_evidence") or {}).get(
                    "p_value_vs_50pct_two_sided_nominal"
                ) is not None
            ),
            "dependence_warning": (
                "Nominal binomial p-values assume independent hit outcomes. Forward-return "
                "horizons overlap and participant OI is shared across index tests. "
                "Non-overlapping phase rows are descriptive alternatives and are not "
                "independent across phases; these values are exploratory, not confirmatory."
            ),
            "interpretation": "No live-score eligibility; use only as a conservative diagnostic.",
        },
        "features": features,
        "client_option_quantity_magnitude_thresholds": [
            {
                "training_quantile": row.get("training_quantile"),
                "training_nonzero_observations": row.get("training_nonzero_observations"),
                "absolute_quantity_threshold": row.get("absolute_quantity_threshold"),
                "holdout_selected_observations": row.get("holdout_selected_observations"),
                "holdout_total_rows": row.get("holdout_total_rows"),
                "crowd_follow_hit_rate_pct": row.get("crowd_follow_hit_rate_pct"),
                "crowd_follow_false_signals": row.get("crowd_follow_false_signals"),
                "pdmp_contrarian_correct_signals": row.get("crowd_follow_false_signals"),
                "pdmp_contrarian_false_signals": (
                    row.get("holdout_selected_observations") - row.get("crowd_follow_false_signals")
                    if isinstance(row.get("holdout_selected_observations"), int)
                    and isinstance(row.get("crowd_follow_false_signals"), int) else None
                ),
                "pdmp_contrarian_hit_rate_pct": row.get("pdmp_contrarian_hit_rate_pct"),
                "holdout_avg_forward_return_pct": row.get("holdout_avg_forward_return_pct"),
            }
            for row in (index.get("client_option_quantity_magnitude_threshold_diagnostics") or [])
            if isinstance(row, dict)
        ],
        "best_holdout_futures_exploratory_only": [
            {
                "feature": item["feature"],
                "horizon_sessions": item["horizon_sessions"],
                "n": item["holdout"].get("n"),
                "directional_observation_count": item["holdout"].get("directional_observation_count"),
                "hit_rate_pct": item["holdout"].get("directional_hit_rate_pct"),
                "false_signal_rate_pct": item["holdout"].get("false_signal_rate_pct"),
                "false_signals": item["holdout"].get("false_signals"),
                "statistical_evidence": item.get("statistical_evidence"),
            }
            for item in futures[:5]
        ],
        "best_holdout_options_exploratory_only": [
            {
                "feature": item["feature"],
                "horizon_sessions": item["horizon_sessions"],
                "n": item["holdout"].get("n"),
                "directional_observation_count": item["holdout"].get("directional_observation_count"),
                "hit_rate_pct": item["holdout"].get("directional_hit_rate_pct"),
                "false_signal_rate_pct": item["holdout"].get("false_signal_rate_pct"),
                "false_signals": item["holdout"].get("false_signals"),
                "statistical_evidence": item.get("statistical_evidence"),
            }
            for item in sorted(
                [
                    row for row in features
                    if row.get("directional_options")
                    and row["holdout"].get("directional_hit_rate_pct") is not None
                ],
                key=lambda row: (
                    row["holdout"].get("directional_hit_rate_pct", -1),
                    row["holdout"].get("directional_observation_count", 0),
                ),
                reverse=True,
            )[:5]
        ],
    }


def build_summary(report):
    status = report.get("status", "unavailable")
    base = {
        "schema_version": 3,
        "summary_format": "compact_v3_inference",
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
    attach_magnitude_threshold_inference(base["indices"])
    base["magnitude_threshold_inference"] = {
        "method": "95% Wilson interval and exact two-sided binomial test against 50% PDMP hit rate",
        "multiple_testing": "One Holm family-wise correction across every available index × horizon × training-quantile threshold comparison in this report",
        "family_size": sum(
            1 for index in base["indices"].values()
            for row in index.get("client_option_quantity_magnitude_thresholds", [])
            if (row.get("statistical_evidence") or {}).get("p_value_vs_50pct_two_sided") is not None
        ),
        "dependence_warning": (
            "Exploratory only. The same market-wide CLIENT OI input is reused for all index price series; "
            "1/3/5-session forward windows overlap; threshold quantiles are fixed from training data only. "
            "Holm correction controls the listed family under its assumptions but does not make these "
            "correlated observations independent or establish a tradable edge."
        ),
        "live_score_eligible": False,
    }
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
