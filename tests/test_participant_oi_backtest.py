import datetime as dt
import unittest

import backtest_participant_oi as backtest


def synthetic_prices(values):
    start = dt.date(2026, 1, 1)
    return {
        (start + dt.timedelta(days=i)).isoformat(): {
            "open": float(value), "close": float(value)
        }
        for i, value in enumerate(values)
    }


def participant_row(date):
    participant = {
        "future_index_long": 100, "future_index_short": 80,
        "index_call_long": 200, "index_call_short": 180,
        "index_put_long": 220, "index_put_short": 210,
    }
    return {
        "date": date,
        "participants": {
            group: dict(participant) for group in ("FII", "DII", "PRO", "CLIENT")
        },
    }


class ParticipantOIBacktestTests(unittest.TestCase):
    def test_false_signal_counts_for_futures(self):
        rows = [
            {"signal": 1.0, "forward_return_pct": 0.4},
            {"signal": -1.0, "forward_return_pct": -0.3},
            {"signal": 2.0, "forward_return_pct": -0.1},
            {"signal": -2.0, "forward_return_pct": 0.2},
            {"signal": 0.0, "forward_return_pct": 0.1},
            {"signal": 1.0, "forward_return_pct": 0.0},
        ]
        result = backtest.calculate_metrics(rows, directional=True)
        self.assertEqual(result["n"], 6)
        self.assertEqual(result["directional_signal_count"], 5)
        self.assertEqual(result["directional_observation_count"], 4)
        self.assertEqual(result["correct_signals"], 2)
        self.assertEqual(result["false_signals"], 2)
        self.assertEqual(result["false_bullish_signals"], 1)
        self.assertEqual(result["false_bearish_signals"], 1)
        self.assertEqual(result["directional_hit_rate_pct"], 50.0)
        self.assertEqual(result["false_signal_rate_pct"], 50.0)
        self.assertEqual(result["signal_coverage_pct"], 83.33)

    def test_options_remain_correlation_only(self):
        rows = [
            {"signal": 1.0, "forward_return_pct": 0.5},
            {"signal": -1.0, "forward_return_pct": -0.2},
            {"signal": 2.0, "forward_return_pct": 0.1},
            {"signal": -2.0, "forward_return_pct": -0.1},
            {"signal": 3.0, "forward_return_pct": 0.4},
        ]
        result = backtest.calculate_metrics(rows, directional=False)
        self.assertIsNotNone(result["pearson_r"])
        self.assertIsNone(result["directional_hit_rate_pct"])
        self.assertIsNone(result["false_signal_rate_pct"])
        self.assertIsNone(result["false_signals"])

    def test_bull_bear_and_sideways_regimes(self):
        bull = synthetic_prices([100 + i for i in range(35)])
        bear = synthetic_prices([140 - i for i in range(35)])
        sideways = synthetic_prices([100 for _ in range(35)])
        self.assertEqual(list(backtest.classify_regimes(bull).values())[-1], "bull")
        self.assertEqual(list(backtest.classify_regimes(bear).values())[-1], "bear")
        self.assertEqual(list(backtest.classify_regimes(sideways).values())[-1], "sideways")

    def test_date_alignment_reports_missing_and_unmatched_sessions(self):
        result = backtest.summarize_date_alignment(
            ["2026-01-01", "2026-01-02", "2026-01-05"],
            ["2026-01-01", "2026-01-05", "2026-01-06"],
        )
        self.assertEqual(result["price_sessions_in_oi_date_range"], 3)
        self.assertEqual(result["missing_oi_sessions_inside_price_range"], 1)
        self.assertEqual(result["missing_oi_dates_sample"], ["2026-01-02"])
        self.assertEqual(result["oi_dates_without_price"], 1)
        self.assertEqual(result["oi_to_price_date_match_pct"], 66.67)

    def test_duplicate_oi_dates_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate OI dates"):
            backtest.validate_oi_records([
                participant_row("2026-01-01"), participant_row("2026-01-01")
            ])

    def test_missing_participant_field_is_rejected(self):
        row = participant_row("2026-01-01")
        del row["participants"]["CLIENT"]["index_put_short"]
        with self.assertRaisesRegex(ValueError, "invalid OI rows"):
            backtest.validate_oi_records([row])

    def test_regime_requires_enough_past_sessions(self):
        short = synthetic_prices([100 + i for i in range(24)])
        self.assertEqual(list(backtest.classify_regimes(short).values())[-1], "unknown")
        longer = synthetic_prices([100 + i for i in range(30)])
        self.assertEqual(list(backtest.classify_regimes(longer).values())[-1], "bull")


if __name__ == "__main__":
    unittest.main()
