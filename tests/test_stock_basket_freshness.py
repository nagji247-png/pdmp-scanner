import datetime as dt
import unittest

from stock_basket_freshness import (
    expected_latest_completed_session,
    exchange_sessions_in_window,
    is_exchange_session,
)

CALENDAR = {
    "holidays": [{"date": "2026-11-10", "name": "Exchange holiday"}],
    "special_sessions": {"2026-11-08": {"name": "Muhurat session"}},
}


class StockBasketFreshnessTests(unittest.TestCase):
    def test_before_eod_cutoff_uses_previous_completed_session(self):
        self.assertEqual(
            expected_latest_completed_session("2026-11-13T14:00:00Z", CALENDAR),
            "2026-11-12",
        )

    def test_after_eod_cutoff_expects_current_session(self):
        self.assertEqual(
            expected_latest_completed_session("2026-11-13T15:00:00Z", CALENDAR),
            "2026-11-13",
        )

    def test_weekend_rolls_back_to_friday_session(self):
        self.assertEqual(
            expected_latest_completed_session("2026-11-14T16:00:00Z", CALENDAR),
            "2026-11-13",
        )

    def test_exchange_holiday_rolls_back_to_previous_session(self):
        self.assertFalse(is_exchange_session("2026-11-10", CALENDAR))
        self.assertEqual(
            expected_latest_completed_session("2026-11-10T16:00:00Z", CALENDAR),
            "2026-11-09",
        )

    def test_special_sunday_session_is_recognized(self):
        self.assertTrue(is_exchange_session("2026-11-08", CALENDAR))
        self.assertEqual(
            expected_latest_completed_session("2026-11-08T15:00:00Z", CALENDAR),
            "2026-11-08",
        )

    def test_window_includes_sessions_even_when_archives_are_missing(self):
        sessions = exchange_sessions_in_window("2026-11-13", 7, CALENDAR)
        self.assertEqual(
            [day.isoformat() for day in sessions],
            ["2026-11-08", "2026-11-09", "2026-11-11", "2026-11-12", "2026-11-13"],
        )


if __name__ == "__main__":
    unittest.main()
