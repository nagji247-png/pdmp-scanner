import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from signal_performance import evaluate_pending, make_event, summarize

IST = ZoneInfo("Asia/Kolkata")


class SignalPerformanceTests(unittest.TestCase):
    def test_stock_signal_scores_only_after_next_session_close(self):
        event = make_event(
            "LATEST ACTIVITY ALERTS", "RELIANCE", "BULLISH",
            datetime(2026, 11, 24, 10, 0, tzinfo=IST).date(),
            datetime(2026, 11, 24, 10, 0, tzinfo=IST),
            price=100, source="test"
        )
        data = {
            "updated": "2026-11-25T10:00:00+05:30",
            "instruments": {"RELIANCE": {"price": 105, "price_as_of": "25/11/2026"}},
        }
        evaluate_pending([event], data, datetime(2026, 11, 25, 10, 0, tzinfo=IST))
        self.assertEqual(event["status"], "PENDING")
        evaluate_pending([event], data, datetime(2026, 11, 25, 15, 50, tzinfo=IST))
        self.assertEqual(event["status"], "CORRECT")
        self.assertAlmostEqual(event["signed_return_pct"], 5.0, places=3)

    def test_bearish_return_is_direction_adjusted(self):
        event = make_event(
            "DAILY STOCK BUYING ACTIVITY", "SBIN", "BEARISH",
            datetime(2026, 11, 24, 10, 0, tzinfo=IST).date(),
            datetime(2026, 11, 24, 10, 0, tzinfo=IST),
            price=100, source="test"
        )
        data = {
            "updated": "2026-11-25T15:50:00+05:30",
            "instruments": {"SBIN": {"price": 95, "price_as_of": "25/11/2026"}},
        }
        evaluate_pending([event], data, datetime(2026, 11, 25, 15, 50, tzinfo=IST))
        self.assertEqual(event["status"], "CORRECT")
        self.assertAlmostEqual(event["signed_return_pct"], 5.0, places=3)

    def test_sector_requires_minimum_coverage(self):
        event = make_event(
            "SECTOR ACTIVITY", "BANKS", "BULLISH",
            datetime(2026, 11, 24, 10, 0, tzinfo=IST).date(),
            datetime(2026, 11, 24, 10, 0, tzinfo=IST),
            members={"A": 100, "B": 100, "C": 100, "D": 100, "E": 100},
            source="test"
        )
        data = {
            "updated": "2026-11-25T15:50:00+05:30",
            "instruments": {
                "A": {"price": 101, "price_as_of": "25/11/2026"},
                "B": {"price": 102, "price_as_of": "25/11/2026"},
            },
        }
        evaluate_pending([event], data, datetime(2026, 11, 25, 15, 50, tzinfo=IST))
        self.assertEqual(event["status"], "UNVERIFIED")

    def test_summary_keeps_unverified_out_of_accuracy(self):
        events = [
            {"department": "MARKET ACTIVITY RADAR", "status": "CORRECT", "signed_return_pct": 2.0},
            {"department": "MARKET ACTIVITY RADAR", "status": "INCORRECT", "signed_return_pct": -1.0},
            {"department": "MARKET ACTIVITY RADAR", "status": "UNVERIFIED", "signed_return_pct": None},
        ]
        row = summarize(events)["MARKET ACTIVITY RADAR"]
        self.assertEqual(row["accuracy_pct"], 50.0)
        self.assertEqual(row["sample_size"], 2)
        self.assertEqual(row["unverified"], 1)


if __name__ == "__main__":
    unittest.main()
