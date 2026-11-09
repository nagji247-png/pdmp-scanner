import unittest

from summarize_participant_oi_backtest import (
    build_summary,
    exact_binomial_two_sided_pvalue,
    holm_adjust_pvalues,
    wilson_interval,
)


def metric(feature, participant, field, horizon, sample, hit=None, false_rate=None, regimes=None):
    directional = field.startswith("future_index")
    observations = 18 if directional else None
    correct = round(observations * hit / 100) if directional and hit is not None else None
    false = observations - correct if directional and correct is not None else None
    return {
        "feature": feature,
        "participant": participant,
        "field": field,
        "horizon_sessions": horizon,
        "sample": sample,
        "n": 20,
        "directional_observation_count": observations,
        "correct_signals": correct,
        "directional_hit_rate_pct": hit,
        "false_signal_rate_pct": false_rate,
        "false_signals": false,
        "pearson_r": 0.12,
        "spearman_r": 0.2,
        "regime_metrics": regimes or {},
    }


class ParticipantOISummaryTests(unittest.TestCase):
    def test_preserves_train_holdout_and_regime_metrics(self):
        futures = "FII.future_index_long_change_pct_prior_gross"
        options = "CLIENT.index_call_long_change_pct_prior_gross"
        report = {
            "status": "exploratory_only",
            "generated_at_utc": "2026-11-06T15:15:00+00:00",
            "oi_source": "NSE official participant-wise EOD OI CSV archive",
            "oi_scope_warning": "Aggregate Index F&O totals; not per-index OI.",
            "oi_sessions": 250,
            "oi_first_date": "2025-10-31",
            "oi_last_date": "2026-11-05",
            "archive_validation": {"valid_oi_sessions": 250, "duplicate_oi_dates": 0},
            "data_adequacy": {"target_sessions": 250, "target_met": True},
            "validation": {"score_changed": False, "eligible_for_live_score": False},
            "indices": {
                "NIFTY": {
                    "symbol": "^NSEI",
                    "ohlc_sessions": 247,
                    "aligned_oi_dates": 249,
                    "missing_oi_sessions_inside_price_range": 0,
                    "regime_counts_on_aligned_dates": {"bull": 90, "bear": 80, "sideways": 79, "unknown": 0},
                    "metrics": [
                        metric(futures, "FII", "future_index_long_change_pct_prior_gross", 1, "train_first_70pct", 55.0, 45.0),
                        metric(futures, "FII", "future_index_long_change_pct_prior_gross", 1, "chronological_holdout_last_30pct", 60.0, 40.0, {
                            "bull": {"n": 8, "directional_hit_rate_pct": 62.5},
                            "bear": {"n": 6, "directional_hit_rate_pct": 50.0},
                            "sideways": {"n": 4, "directional_hit_rate_pct": 75.0},
                        }),
                        metric(options, "CLIENT", "index_call_long_change_pct_prior_gross", 3, "train_first_70pct"),
                        metric(options, "CLIENT", "index_call_long_change_pct_prior_gross", 3, "chronological_holdout_last_30pct"),
                    ],
                },
            },
        }
        report["indices"]["NIFTY"]["metrics"][1]["non_overlapping_holdout_phases"] = [
            {
                "phase_offset_sessions": 0,
                "anchor_signal_date": "2026-10-01",
                "n": 6,
                "directional_observation_count": 6,
                "correct_signals": 4,
                "false_signals": 2,
                "false_signal_rate_pct": 33.33,
                "directional_hit_rate_pct": 66.67,
                "avg_forward_return_pct": 0.12,
                "regime_metrics": {
                    "bull": {
                        "n": 2,
                        "directional_observation_count": 2,
                        "directional_hit_rate_pct": 100.0,
                        "false_signals": 0,
                        "false_signal_rate_pct": 0.0,
                        "avg_forward_return_pct": 0.2,
                    }
                },
            }
        ]
        result = build_summary(report)
        nifty = result["indices"]["NIFTY"]
        self.assertEqual(result["oi_sessions"], 250)
        self.assertEqual(nifty["data_quality"]["aligned_oi_dates"], 249)
        self.assertEqual(nifty["feature_horizon_count"], 2)
        future = next(x for x in nifty["features"] if x["directional_futures"])
        self.assertEqual(future["train"]["directional_hit_rate_pct"], 55.0)
        self.assertEqual(future["holdout"]["directional_hit_rate_pct"], 60.0)
        self.assertEqual(future["holdout_regimes"]["sideways"]["n"], 4)
        phase = future["non_overlapping_holdout_phases"][0]
        self.assertEqual(phase["phase_offset_sessions"], 0)
        self.assertEqual(phase["directional_hit_rate_pct"], 66.67)
        self.assertEqual(phase["regime_metrics"]["bull"]["n"], 2)
        self.assertEqual(nifty["best_holdout_futures_exploratory_only"][0]["feature"], futures)
        self.assertEqual(future["statistical_evidence"]["holm_family_size"], 1)
        self.assertEqual(nifty["directional_inference"]["family_size"], 1)
        self.assertIsNotNone(future["statistical_evidence"]["hit_rate_ci95_pct"])
        self.assertFalse(future["statistical_evidence"]["nominal_holm_p_below_05"])
        option = next(x for x in nifty["features"] if not x["directional_futures"])
        self.assertIsNone(option["holdout"].get("directional_hit_rate_pct"))
        self.assertNotIn("statistical_evidence", option)
        self.assertFalse(result["score_changed"])
        self.assertFalse(result["eligible_for_live_score"])

    def test_wilson_interval_and_exact_binomial_probability(self):
        interval = wilson_interval(10, 20)
        self.assertIsNotNone(interval)
        self.assertLess(interval[0], 50.0)
        self.assertGreater(interval[1], 50.0)
        self.assertIsNone(wilson_interval(0, 0))
        self.assertAlmostEqual(exact_binomial_two_sided_pvalue(10, 20), 1.0)
        self.assertAlmostEqual(
            exact_binomial_two_sided_pvalue(20, 20),
            2 / (2 ** 20),
            places=10,
        )
        self.assertIsNone(exact_binomial_two_sided_pvalue(2, 0))

    def test_holm_adjustment_is_monotone_and_not_smaller_than_raw_p(self):
        adjusted = holm_adjust_pvalues({"a": 0.01, "b": 0.04, "c": 0.03})
        self.assertAlmostEqual(adjusted["a"], 0.03)
        self.assertAlmostEqual(adjusted["c"], 0.06)
        self.assertAlmostEqual(adjusted["b"], 0.06)
        self.assertTrue(all(adjusted[key] >= value for key, value in {
            "a": 0.01, "b": 0.04, "c": 0.03
        }.items()))

    def test_unavailable_report_stays_unavailable(self):
        result = build_summary({
            "status": "unavailable",
            "reason": "Yahoo Finance history unavailable",
            "generated_at_utc": "2026-11-06T15:15:00+00:00",
        })
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["reason"], "Yahoo Finance history unavailable")
        self.assertEqual(result["indices"], {})
        self.assertFalse(result["score_changed"])

    def test_exploratory_report_without_indices_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "no index results"):
            build_summary({"status": "exploratory_only", "indices": {}})


if __name__ == "__main__":
    unittest.main()
