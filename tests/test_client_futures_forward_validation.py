"""Tests for the new-session CLIENT Futures forward validation window."""
import datetime as dt
import unittest

from backtest_participant_oi import client_futures_recent_direction_check


class ClientFuturesForwardValidationTests(unittest.TestCase):
    def make_data(self, signal_sessions=14):
        start = dt.date(2026, 11, 12)
        dates = [(start + dt.timedelta(days=i)).isoformat() for i in range(signal_sessions + 2)]
        records = []
        for index, date in enumerate(dates):
            records.append({
                "date": date,
                "participants": {
                    "CLIENT": {
                        "future_index_long": 200000 - index * 1000,
                        "future_index_short": 50000 + index * 1000,
                    }
                },
            })
        prices = {
            date: {"close": 25000 + index * 100}
            for index, date in enumerate(dates)
        }
        return records, prices

    def test_only_new_sessions_after_anchor_are_counted(self):
        records, prices = self.make_data(7)
        result = client_futures_recent_direction_check(
            records, prices, sessions=7, anchor_date="2026-11-12"
        )
        self.assertEqual(result["sample_sessions"], 7)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["first_signal_date"], "2026-11-13")
        self.assertEqual(result["last_signal_date"], "2026-11-19")
        self.assertEqual(result["directional_hit_rate_pct"], 0.0)
        self.assertEqual(result["contrarian_hit_rate_pct"], 100.0)

    def test_fourteen_session_window_and_progress(self):
        records, prices = self.make_data(14)
        result = client_futures_recent_direction_check(
            records, prices, sessions=14, anchor_date="2026-11-12"
        )
        self.assertEqual(result["sample_sessions"], 14)
        self.assertEqual(result["remaining_observations"], 0)
        self.assertEqual(result["status"], "ready")

    def test_incomplete_new_window_reports_progress_not_fake_zero(self):
        records, prices = self.make_data(4)
        result = client_futures_recent_direction_check(
            records, prices, sessions=14, anchor_date="2026-11-12"
        )
        self.assertEqual(result["sample_sessions"], 4)
        self.assertEqual(result["remaining_observations"], 10)
        self.assertEqual(result["status"], "insufficient_sessions")
        self.assertEqual(result["collection_status"], "collecting_new_sessions")


if __name__ == "__main__":
    unittest.main()
