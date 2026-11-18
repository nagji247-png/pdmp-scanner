import unittest
from daily_stock_buying_activity import build_report


class DailyStockBuyingActivityTests(unittest.TestCase):
    def test_same_expiry_futures_price_and_oi_create_long_buildup(self):
        master = {"stocks": {"ABC": {}}}
        archive = {"records": [
            {"date": "2026-11-16", "equity_rows": [
                {"symbol": "ABC", "close": 100, "previous_close": 99, "volume": 100000},
            ]},
            {"date": "2026-11-17", "equity_rows": [
                {"symbol": "ABC", "close": 105, "previous_close": 100, "volume": 200000},
            ]},
        ]}
        fo_archive = {"records": [
            {"date": "2026-11-16", "stock_futures": {"ABC": {"available": True, "by_expiry": {
                "2026-11-26": {"open_interest": 1000, "close": 100.0}
            }}}},
            {"date": "2026-11-17", "stock_futures": {"ABC": {"available": True, "by_expiry": {
                "2026-11-26": {"open_interest": 1100, "close": 105.0}
            }}}},
        ]}
        report = build_report(archive, master, generated_at="2026-11-18T08:00:00+05:30", fo_archive=fo_archive)
        row = next(row for row in report["rows"] if row["symbol"] == "ABC")
        self.assertEqual(row["signal"], "LONG BUILD-UP")
        self.assertEqual(row["strength"], "WATCH")
        self.assertEqual(row["oi_change_pct"], 10.0)
        self.assertEqual(row["futures_change_pct"], 5.0)
        self.assertEqual(row["futures_expiry"], "2026-11-26")
        self.assertIsNone(row["delivery_pct"])

    def test_scans_outside_fno_and_marks_only_verified_early_alert(self):
        master = {"stocks": {"FNO1": {}}}
        archive = {"records": [
            {"date": "2026-11-16", "equity_rows": [
                {"symbol": "ABC", "close": 100, "previous_close": 99, "volume": 100000},
                {"symbol": "FNO1", "close": 200, "previous_close": 200, "volume": 100000},
            ]},
            {"date": "2026-11-17", "equity_rows": [
                {"symbol": "ABC", "close": 105, "previous_close": 100, "volume": 200000},
                {"symbol": "FNO1", "close": 202, "previous_close": 200, "volume": 200000},
                {"symbol": "LOWVOL", "close": 110, "previous_close": 100, "volume": 1000},
            ]},
        ]}
        report = build_report(archive, master, generated_at="2026-11-18T08:00:00+05:30")
        by_symbol = {row["symbol"]: row for row in report["rows"]}
        self.assertEqual(by_symbol["ABC"]["category"], "अन्य NSE")
        self.assertEqual(by_symbol["FNO1"]["category"], "F&O")
        self.assertEqual(by_symbol["ABC"]["signal"], "EARLY BUYING WATCH")
        self.assertIsNone(by_symbol["ABC"]["oi_change_pct"])
        self.assertIsNone(by_symbol["ABC"]["delivery_pct"])
        self.assertNotIn("LOWVOL", by_symbol)
        self.assertEqual(report["coverage"]["intraday"], "not_available_in_this_eod_scan")

    def test_negative_price_with_unusual_volume_is_selling_watch(self):
        archive = {"records": [
            {"date": "2026-11-16", "equity_rows": [
                {"symbol": "XYZ", "close": 100, "previous_close": 100, "volume": 100000}]},
            {"date": "2026-11-17", "equity_rows": [
                {"symbol": "XYZ", "close": 98, "previous_close": 100, "volume": 200000}]},
        ]}
        report = build_report(archive, {"stocks": {}})
        self.assertEqual(report["rows"][0]["signal"], "SELLING WATCH")

    def test_missing_history_does_not_create_fake_signal(self):
        archive = {"records": [{"date": "2026-11-17", "equity_rows": [
            {"symbol": "XYZ", "close": 105, "previous_close": 100, "volume": 200000}]}]}
        report = build_report(archive, {"stocks": {}})
        self.assertEqual(report["rows"], [])


if __name__ == "__main__":
    unittest.main()
