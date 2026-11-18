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
        self.assertTrue(by_symbol["ABC"]["new_discovery"])
        self.assertEqual(by_symbol["ABC"]["activity_days"], 1)
        self.assertEqual(by_symbol["FNO1"]["category"], "F&O")
        self.assertEqual(by_symbol["ABC"]["signal"], "EARLY BUYING WATCH")
        self.assertIsNone(by_symbol["ABC"]["oi_change_pct"])
        self.assertIsNone(by_symbol["ABC"]["delivery_pct"])
        self.assertNotIn("LOWVOL", by_symbol)
        self.assertEqual(report["coverage"]["intraday"], "not_available_in_this_eod_scan")

    def test_official_delivery_archive_is_joined_by_exact_session_and_symbol(self):
        archive = {"records": [
            {"date": "2026-11-16", "equity_rows": [
                {"symbol": "ABC", "close": 100, "previous_close": 99, "volume": 100000}]},
            {"date": "2026-11-17", "equity_rows": [
                {"symbol": "ABC", "close": 105, "previous_close": 100, "volume": 200000}]},
        ]}
        delivery = {"records": [
            {"date": "2026-11-16", "rows": {"ABC": {"delivery_qty": 50000, "delivery_pct": 50.0}}},
            {"date": "2026-11-17", "rows": {"ABC": {"delivery_qty": 120000, "delivery_pct": 60.0}}},
        ]}
        report = build_report(archive, {"stocks": {}}, delivery_archive=delivery)
        row = report["rows"][0]
        self.assertEqual(row["delivery_pct"], 60.0)
        self.assertEqual(row["delivery_qty"], 120000)
        self.assertEqual(report["coverage"]["delivery_pct"], "verified")

    def test_official_bulk_block_deals_join_only_exact_session(self):
        archive = {"records": [
            {"date": "2026-11-17", "equity_rows": [
                {"symbol": "ABC", "close": 100, "previous_close": 99, "volume": 100000}]},
            {"date": "2026-11-18", "equity_rows": [
                {"symbol": "ABC", "close": 105, "previous_close": 100, "volume": 200000}]},
        ]}
        deals = {"records": [
            {"date": "2026-11-17", "verified_report_count": 2, "rows": [
                {"symbol": "OLD", "kind": "Bulk", "client": "OLD CLIENT", "side": "BUY", "quantity": 1000, "price": 10}]},
            {"date": "2026-11-18", "verified_report_count": 2, "rows": [
                {"symbol": "ABC", "kind": "Block", "client": "DISCLOSED CLIENT", "side": "SELL", "quantity": 50000, "price": 104.5}]},
        ]}
        report = build_report(archive, {"stocks": {}}, deals_archive=deals)
        self.assertEqual(report["bulk_block_deals"][0]["client"], "DISCLOSED CLIENT")
        self.assertEqual(report["bulk_block_deals"][0]["side"], "SELL")
        self.assertEqual(report["coverage"]["bulk_block_deals"], "verified")

    def test_negative_price_with_unusual_volume_is_selling_watch(self):
        archive = {"records": [
            {"date": "2026-11-16", "equity_rows": [
                {"symbol": "XYZ", "close": 100, "previous_close": 100, "volume": 100000}]},
            {"date": "2026-11-17", "equity_rows": [
                {"symbol": "XYZ", "close": 98, "previous_close": 100, "volume": 200000}]},
        ]}
        report = build_report(archive, {"stocks": {}})
        self.assertEqual(report["rows"][0]["signal"], "SELLING WATCH")

    def test_consecutive_activity_days_counts_back_to_first_inactive_session(self):
        archive = {"records": [
            {"date": "2026-11-13", "equity_rows": [{"symbol": "ABC", "close": 100, "previous_close": 100, "volume": 10000}]},
            {"date": "2026-11-16", "equity_rows": [{"symbol": "ABC", "close": 101, "previous_close": 100, "volume": 20000}]},
            {"date": "2026-11-17", "equity_rows": [{"symbol": "ABC", "close": 102, "previous_close": 101, "volume": 30000}]},
            {"date": "2026-11-18", "equity_rows": [{"symbol": "ABC", "close": 103, "previous_close": 102, "volume": 40000}]},
        ]}
        report = build_report(archive, {"stocks": {}})
        self.assertEqual(report["rows"][0]["activity_days"], 3)

    def test_flat_price_with_unusual_volume_is_visible_as_early_activity(self):
        archive = {"records": [
            {"date": "2026-11-16", "equity_rows": [
                {"symbol": "SMALL", "close": 20, "previous_close": 20, "volume": 5000}]},
            {"date": "2026-11-17", "equity_rows": [
                {"symbol": "SMALL", "close": 20, "previous_close": 20, "volume": 8000}]},
        ]}
        report = build_report(archive, {"stocks": {}})
        self.assertEqual(report["rows"][0]["signal"], "UNUSUAL ACTIVITY WATCH")
        self.assertEqual(report["rows"][0]["strength"], "EARLY")

    def test_missing_history_does_not_create_fake_signal(self):
        archive = {"records": [{"date": "2026-11-17", "equity_rows": [
            {"symbol": "XYZ", "close": 105, "previous_close": 100, "volume": 200000}]}]}
        report = build_report(archive, {"stocks": {}})
        self.assertEqual(report["rows"], [])


if __name__ == "__main__":
    unittest.main()
