import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from signal_performance import build_summary, direction_from_signal, next_session, update_tracker


class SignalPerformanceTests(unittest.TestCase):
    def test_daily_buying_directions(self):
        self.assertEqual(direction_from_signal("LONG BUILD-UP"), "BULLISH")
        self.assertEqual(direction_from_signal("SHORT BUILD-UP"), "BEARISH")
        self.assertIsNone(direction_from_signal("UNUSUAL ACTIVITY WATCH"))

    def test_next_session_respects_holiday(self):
        calendar = {"calendar_year": 2026, "holidays": [{"date": "2026-11-26"}], "special_sessions": {}}
        self.assertEqual(next_session(__import__("datetime").date(2026, 11, 25), calendar), "2026-11-27")

    def test_summary_accuracy_and_profit(self):
        events = [
            {"department": "MARKET ACTIVITY RADAR", "status": "evaluated", "result": "CORRECT", "return_pct": 1.2},
            {"department": "MARKET ACTIVITY RADAR", "status": "evaluated", "result": "INCORRECT", "return_pct": -0.4},
            {"department": "MARKET ACTIVITY RADAR", "status": "pending", "result": None, "return_pct": None},
        ]
        x = build_summary(events)["MARKET ACTIVITY RADAR"]
        self.assertEqual(x["accuracy_pct"], 50.0)
        self.assertEqual(x["sample_size"], 2)
        self.assertEqual(x["net_return_pct"], 0.8)
        self.assertEqual(x["pending"], 1)

    def test_tracker_does_not_overwrite_existing_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data.json").write_text('{"updated":"2026-11-25T10:00:00Z","market_activity_quotes":{"instruments":{}}}')
            (root / "nse-fo-stock-sector-master.json").write_text('{"stocks":{}}')
            (root / "daily_stock_buying_activity.json").write_text('{"rows":[]}')
            (root / "contrarian.json").write_text('[]')
            (root / "exchange_calendar.json").write_text('{"calendar_year":2026,"holidays":[],"special_sessions":{}}')
            old = {"id":"x","department":"MARKET ACTIVITY RADAR","status":"evaluated","result":"CORRECT","return_pct":1.0}
            (root / "signal-performance.json").write_text(__import__("json").dumps({"events":[old]}))
            result = update_tracker(*(str(root / name) for name in ["data.json","nse-fo-stock-sector-master.json","daily_stock_buying_activity.json","contrarian.json","exchange_calendar.json"]), ledger_path=root / "signal-performance.json")
            self.assertEqual(len(result["events"]), 1)
            self.assertEqual(result["events"][0]["result"], "CORRECT")


if __name__ == "__main__":
    unittest.main()
