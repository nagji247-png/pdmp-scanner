import datetime as dt
import unittest
from unittest.mock import patch

import pandas as pd

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

    def test_client_futures_recent_seven_session_direction_check(self):
        start = dt.date(2026, 1, 1)
        records = []
        prices = {}
        for position in range(9):
            date = (start + dt.timedelta(days=position)).isoformat()
            client = {
                "future_index_long": 100 + position * 10,
                "future_index_short": 80,
            }
            records.append({"date": date, "participants": {"CLIENT": client}})
            close = 100.0 + position
            prices[date] = {"open": close, "close": close}
        # Two of the seven next-session outcomes move against the bullish signal.
        prices[(start + dt.timedelta(days=4)).isoformat()]["close"] = 99.0
        prices[(start + dt.timedelta(days=6)).isoformat()]["close"] = 100.0
        result = backtest.client_futures_recent_direction_check(records, prices, sessions=7)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["sample_sessions"], 7)
        self.assertEqual(result["directional_observation_count"], 7)
        self.assertEqual(result["correct_signals"], 5)
        self.assertEqual(result["wrong_signals"], 2)
        self.assertEqual(result["directional_hit_rate_pct"], 71.43)
        self.assertEqual(result["contrarian_correct_signals"], 2)
        self.assertEqual(result["contrarian_hit_rate_pct"], 28.57)
        self.assertFalse(result["eligible_for_live_score"])
        self.assertEqual(result["observations"][0]["signal_date"], "2026-01-02")

    def test_client_futures_recent_check_reports_insufficient_sessions(self):
        prices = {"2026-01-01": {"close": 100}, "2026-01-02": {"close": 101}}
        records = [
            {"date": "2026-01-01", "participants": {"CLIENT": {"future_index_long": 10, "future_index_short": 5}}},
            {"date": "2026-01-02", "participants": {"CLIENT": {"future_index_long": 11, "future_index_short": 5}}},
        ]
        result = backtest.client_futures_recent_direction_check(records, prices, sessions=7)
        self.assertEqual(result["status"], "insufficient_sessions")
        self.assertEqual(result["sample_sessions"], 0)
        self.assertIsNone(result["directional_hit_rate_pct"])

    def test_incomplete_current_daily_bar_is_excluded_before_1600_ist(self):
        completed = pd.date_range(
            end="2026-11-11 15:30", periods=30, freq="B", tz="Asia/Kolkata"
        )
        index = completed.append(
            pd.DatetimeIndex(["2026-11-12 13:30"], tz="Asia/Kolkata")
        )
        values = [100.0 + position for position in range(len(index))]
        frame = pd.DataFrame(
            {"Open": values, "Close": [value + 0.5 for value in values]},
            index=index,
        )

        class FakeTicker:
            def history(self, **kwargs):
                return frame

        now_utc = dt.datetime(2026, 11, 12, 7, 57, tzinfo=dt.timezone.utc)
        with patch.object(backtest.yf, "Ticker", return_value=FakeTicker()):
            prices, validation = backtest.load_index_prices("^NSEI", now_utc=now_utc)

        self.assertEqual(len(prices), 30)
        self.assertEqual(min(prices), "2026-10-01")
        self.assertEqual(max(prices), "2026-11-11")
        self.assertEqual(validation["ohlc_sessions"], 30)
        self.assertEqual(
            validation["incomplete_current_session_excluded_date"],
            "2026-11-12",
        )

    def test_current_daily_bar_is_allowed_after_1600_ist(self):
        completed = pd.date_range(
            end="2026-11-11 15:30", periods=30, freq="B", tz="Asia/Kolkata"
        )
        index = completed.append(
            pd.DatetimeIndex(["2026-11-12 15:30"], tz="Asia/Kolkata")
        )
        values = [100.0 + position for position in range(len(index))]
        frame = pd.DataFrame(
            {"Open": values, "Close": [value + 0.5 for value in values]},
            index=index,
        )

        class FakeTicker:
            def history(self, **kwargs):
                return frame

        now_utc = dt.datetime(2026, 11, 12, 10, 31, tzinfo=dt.timezone.utc)
        with patch.object(backtest.yf, "Ticker", return_value=FakeTicker()):
            prices, validation = backtest.load_index_prices("^NSEI", now_utc=now_utc)

        self.assertIn("2026-11-12", prices)
        self.assertIsNone(validation["incomplete_current_session_excluded_date"])

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
        self.assertEqual(result["contrarian_correct_signals"], 2)
        self.assertEqual(result["contrarian_false_signals"], 2)
        self.assertEqual(result["contrarian_hit_rate_pct"], 50.0)
        self.assertEqual(result["contrarian_false_signal_rate_pct"], 50.0)
        self.assertEqual(result["signal_coverage_pct"], 83.33)


    def test_client_option_quantity_features_use_directional_put_sign(self):
        previous = {
            "index_call_long": 2112701,
            "index_call_short": 2081906,
            "index_put_long": 2426932,
            "index_put_short": 2810271,
        }
        current = {
            "index_call_long": 3045743,
            "index_call_short": 2706602,
            "index_put_long": 2722311,
            "index_put_short": 3140961,
        }
        features = backtest.client_option_quantity_features(current, previous)
        self.assertEqual(features["index_call_net_quantity"], 308346)
        self.assertEqual(features["index_put_raw_net_quantity"], -35311)
        self.assertEqual(features["index_put_directional_net_quantity"], 35311)
        self.assertEqual(features["index_option_user_arithmetic_net_quantity"], 273035)
        self.assertEqual(features["index_option_directional_net_quantity"], 343657)

    def test_client_option_quantity_rejects_missing_legs(self):
        self.assertEqual(
            backtest.client_option_quantity_features(
                {"index_call_long": 100}, {"index_call_long": 90}
            ),
            {},
        )

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

    def test_non_overlapping_phases_separate_forward_windows(self):
        rows = [
            {
                "signal_session_position": position,
                "date": f"2026-01-{position + 1:02d}",
                "signal": 1.0 if position % 2 == 0 else -1.0,
                "forward_return_pct": 0.2 if position % 2 == 0 else -0.1,
                "regime": ("bull", "bear", "sideways")[position % 3],
            }
            for position in range(10, 18)
        ]
        phases = backtest.partition_non_overlapping_rows(rows, 3)
        self.assertEqual([len(phase) for phase in phases], [3, 3, 2])
        flattened = [row for phase in phases for row in phase]
        self.assertEqual(
            sorted(row["signal_session_position"] for row in flattened),
            list(range(10, 18)),
        )
        for phase in phases:
            positions = [row["signal_session_position"] for row in phase]
            self.assertTrue(
                all(right - left >= 3 for left, right in zip(positions, positions[1:]))
            )
        metrics = backtest.non_overlapping_phase_metrics(
            rows, 3, directional=True
        )
        self.assertEqual(
            [row["phase_offset_sessions"] for row in metrics], [0, 1, 2]
        )
        self.assertEqual(metrics[0]["directional_observation_count"], 3)
        self.assertEqual(metrics[0]["false_signals"], 0)
        self.assertNotIn("regime_metrics", metrics[0])

    def test_non_overlapping_phase_rejects_invalid_horizon(self):
        with self.assertRaisesRegex(ValueError, "positive integer"):
            backtest.partition_non_overlapping_rows([], 0)

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
