import unittest
from daily_stock_buying_activity import build_report, build_price_volume_outcomes


class DailyStockBuyingActivityTests(unittest.TestCase):
    def test_signal_outcomes_score_only_matured_forward_sessions(self):
        sessions = [
            {"date": "2026-11-12"},
            {"date": "2026-11-13"},
            {"date": "2026-11-16"},
            {"date": "2026-11-17"},
        ]
        maps = [
            {"ABC": {"close": 100, "previous_close": 100, "volume": 10000}},
            {"ABC": {"close": 102, "previous_close": 100, "volume": 20000}},
            {"ABC": {"close": 103, "previous_close": 102, "volume": 10000}},
            {"ABC": {"close": 104, "previous_close": 103, "volume": 10000}},
        ]
        history, summary = build_price_volume_outcomes(sessions, maps)
        signal = next(item for item in history if item["date"] == "2026-11-13")
        self.assertEqual(signal["outcomes"]["1D"], "RIGHT")
        self.assertEqual(signal["outcomes"]["3D"], "PENDING")
        self.assertEqual(signal["outcomes"]["5D"], "PENDING")
        self.assertGreaterEqual(summary[1]["right"], 1)
        self.assertGreaterEqual(summary[3]["pending"], 1)

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
        deals_archive = {"records": [
            {"date": "2026-11-17", "verified_report_count": 2, "rows": [
                {"symbol": "ABC", "kind": "Bulk", "client": "DISCLOSED BUYER",
                 "side": "BUY", "quantity": 250000, "price": 104.5}
            ]}
        ]}
        report = build_report(archive, master, generated_at="2026-11-18T08:00:00+05:30",
                              fo_archive=fo_archive, deals_archive=deals_archive)
        row = next(row for row in report["rows"] if row["symbol"] == "ABC")
        self.assertEqual(row["signal"], "LONG BUILD-UP")
        self.assertEqual(row["strength"], "STRONG")
        self.assertEqual(report["strength_summary"]["STRONG"], 1)
        self.assertEqual(report["strength_summary"]["WATCH"], 0)
        self.assertEqual(report["strength_summary"]["EARLY"], 0)
        self.assertEqual(row["deal_evidence"][0]["client"], "DISCLOSED BUYER")
        self.assertTrue(any("NSE disclosed" in item for item in row["evidence"]))
        self.assertEqual(row["oi_change_pct"], 10.0)
        self.assertEqual(row["futures_change_pct"], 5.0)
        self.assertEqual(row["futures_expiry"], "2026-11-26")
        self.assertEqual(row["average_volume_sessions"], 1)
        self.assertIsNone(row["delivery_pct"])

    def test_valid_same_expiry_contract_is_used_when_other_symbol_expiry_is_invalid(self):
        archive = {"records": [
            {"date": "2026-11-16", "equity_rows": [
                {"symbol": "ABC", "close": 100, "previous_close": 99, "volume": 100000}]},
            {"date": "2026-11-17", "equity_rows": [
                {"symbol": "ABC", "close": 105, "previous_close": 100, "volume": 200000}]},
        ]}
        # available=False records that another expiry for ABC was invalid.
        # The exact common expiry below is independently validated and usable.
        fo_archive = {"records": [
            {"date": "2026-11-16", "stock_futures": {"ABC": {"available": False, "by_expiry": {
                "2026-11-26": {"open_interest": 1000, "close": 100.0}}}}},
            {"date": "2026-11-17", "stock_futures": {"ABC": {"available": False, "by_expiry": {
                "2026-11-26": {"open_interest": 1100, "close": 105.0}}}}},
        ]}
        report = build_report(archive, {"stocks": {"ABC": {}}}, fo_archive=fo_archive)
        row = next(row for row in report["rows"] if row["symbol"] == "ABC")
        self.assertEqual(row["oi_change_pct"], 10.0)
        self.assertEqual(row["futures_change_pct"], 5.0)
        self.assertEqual(row["futures_expiry"], "2026-11-26")
        self.assertEqual(report["coverage_counts"]["fno_symbols_with_same_expiry_oi"], 1)
        self.assertEqual(report["coverage"]["futures_oi"], "verified_for_matched_stock_futures")

    def test_futures_oi_is_unavailable_when_previous_cash_session_archive_is_missing(self):
        archive = {"records": [
            {"date": "2026-11-16", "equity_rows": [
                {"symbol": "ABC", "close": 100, "previous_close": 99, "volume": 100000}]},
            {"date": "2026-11-17", "equity_rows": [
                {"symbol": "ABC", "close": 102, "previous_close": 100, "volume": 120000}]},
            {"date": "2026-11-18", "equity_rows": [
                {"symbol": "ABC", "close": 105, "previous_close": 102, "volume": 200000}]},
        ]}
        fo_archive = {"records": [
            {"date": "2026-11-16", "stock_futures": {"ABC": {"available": True, "by_expiry": {
                "2026-11-26": {"open_interest": 1000, "close": 100.0}}}}},
            # 17-Nov is intentionally missing; 16-Nov must not be used as a stale substitute.
            {"date": "2026-11-18", "stock_futures": {"ABC": {"available": True, "by_expiry": {
                "2026-11-26": {"open_interest": 1300, "close": 105.0}}}}},
        ]}
        report = build_report(archive, {"stocks": {"ABC": {}}}, fo_archive=fo_archive)
        row = next(row for row in report["rows"] if row["symbol"] == "ABC")
        self.assertIsNone(row["oi_change_pct"])
        self.assertIsNone(row["futures_change_pct"])
        self.assertIsNone(row["futures_expiry"])
        self.assertIn("Futures OI", row["missing_fields"])

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
        self.assertEqual(by_symbol["ABC"]["average_volume_sessions"], 1)
        self.assertEqual(by_symbol["FNO1"]["category"], "F&O")
        self.assertEqual(by_symbol["ABC"]["signal"], "EARLY BUYING WATCH")
        self.assertIsNone(by_symbol["ABC"]["oi_change_pct"])
        self.assertIsNone(by_symbol["ABC"]["delivery_pct"])
        self.assertNotIn("LOWVOL", by_symbol)
        self.assertEqual(report["coverage"]["intraday"], "not_available_in_this_eod_scan")

    def test_delivery_watch_requires_historical_jump_and_does_not_claim_buying(self):
        archive = {"records": [
            {"date": "2026-11-13", "equity_rows": [
                {"symbol": "ABC", "close": 100, "previous_close": 100, "volume": 100000}]},
            {"date": "2026-11-16", "equity_rows": [
                {"symbol": "ABC", "close": 100, "previous_close": 100, "volume": 100000}]},
            {"date": "2026-11-17", "equity_rows": [
                {"symbol": "ABC", "close": 100, "previous_close": 100, "volume": 200000}]},
        ]}
        delivery = {"records": [
            {"date": "2026-11-13", "rows": {"ABC": {"delivery_pct": 25.0}}},
            {"date": "2026-11-16", "rows": {"ABC": {"delivery_pct": 28.0}}},
            {"date": "2026-11-17", "rows": {"ABC": {"delivery_pct": 45.0}}},
        ]}
        report = build_report(archive, {"stocks": {}}, delivery_archive=delivery)
        row = report["rows"][0]
        self.assertEqual(row["signal"], "DELIVERY WATCH")
        self.assertEqual(row["strength"], "WATCH")
        self.assertEqual(row["delivery_avg_pct_20"], 26.5)
        self.assertTrue(any("खरीददार की पहचान नहीं" in item for item in row["evidence"]))

    def test_delivery_watch_keeps_same_day_buy_deal_evidence_without_becoming_strong(self):
        archive = {"records": [
            {"date": "2026-11-13", "equity_rows": [
                {"symbol": "ABC", "close": 100, "previous_close": 100, "volume": 100000}]},
            {"date": "2026-11-16", "equity_rows": [
                {"symbol": "ABC", "close": 100, "previous_close": 100, "volume": 100000}]},
            {"date": "2026-11-17", "equity_rows": [
                {"symbol": "ABC", "close": 100, "previous_close": 100, "volume": 200000}]},
        ]}
        delivery = {"records": [
            {"date": "2026-11-13", "rows": {"ABC": {"delivery_pct": 25.0}}},
            {"date": "2026-11-16", "rows": {"ABC": {"delivery_pct": 28.0}}},
            {"date": "2026-11-17", "rows": {"ABC": {"delivery_pct": 45.0}}},
        ]}
        deals = {"records": [
            {"date": "2026-11-17", "verified_report_count": 2, "rows": [
                {"symbol": "ABC", "kind": "Bulk", "client": "DISCLOSED BUYER",
                 "side": "BUY", "quantity": 75000, "price": 100.25}]}
        ]}
        report = build_report(archive, {"stocks": {}}, delivery_archive=delivery, deals_archive=deals)
        row = report["rows"][0]
        self.assertEqual(row["signal"], "DELIVERY WATCH")
        self.assertEqual(row["strength"], "WATCH")
        self.assertEqual(row["deal_evidence"][0]["client"], "DISCLOSED BUYER")
        self.assertEqual(row["deal_evidence"][0]["quantity"], 75000)
        self.assertTrue(any("disclosed BUY deal" in item for item in row["evidence"]))
        self.assertEqual(report["strength_summary"]["STRONG"], 0)
        self.assertEqual(report["strength_summary"]["WATCH"], 1)

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
        self.assertEqual(report["coverage"]["delivery_pct"], "verified_for_matched_symbols")

    def test_delivery_record_without_valid_matching_pct_is_not_verified(self):
        archive = {"records": [
            {"date": "2026-11-16", "equity_rows": [
                {"symbol": "ABC", "close": 100, "previous_close": 99, "volume": 100000}]},
            {"date": "2026-11-17", "equity_rows": [
                {"symbol": "ABC", "close": 105, "previous_close": 100, "volume": 200000}]},
        ]}
        delivery = {"records": [
            {"date": "2026-11-17", "rows": {
                "ABC": {"delivery_qty": 50000, "delivery_pct": None}
            }}
        ]}
        report = build_report(archive, {"stocks": {}}, delivery_archive=delivery)
        self.assertEqual(report["coverage"]["delivery_pct"], "record_without_valid_symbol_matches")
        self.assertEqual(report["coverage_counts"]["delivery_symbols_matched"], 0)
        self.assertEqual(report["coverage_counts"]["delivery_eq_symbols_scanned"], 1)

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


    def test_covering_and_unwinding_deals_are_watch_only_and_side_matched(self):
        archive = {"records": [
            {"date": "2026-11-16", "equity_rows": [
                {"symbol": "COVER", "close": 100, "previous_close": 99, "volume": 100000},
                {"symbol": "UNWIND", "close": 100, "previous_close": 101, "volume": 100000},
            ]},
            {"date": "2026-11-17", "equity_rows": [
                {"symbol": "COVER", "close": 105, "previous_close": 100, "volume": 200000},
                {"symbol": "UNWIND", "close": 95, "previous_close": 100, "volume": 200000},
            ]},
        ]}
        fo_archive = {"records": [
            {"date": "2026-11-16", "stock_futures": {
                "COVER": {"available": True, "by_expiry": {
                    "2026-11-26": {"open_interest": 1000, "close": 100.0}}},
                "UNWIND": {"available": True, "by_expiry": {
                    "2026-11-26": {"open_interest": 1000, "close": 100.0}}},
            }},
            {"date": "2026-11-17", "stock_futures": {
                "COVER": {"available": True, "by_expiry": {
                    "2026-11-26": {"open_interest": 900, "close": 105.0}}},
                "UNWIND": {"available": True, "by_expiry": {
                    "2026-11-26": {"open_interest": 900, "close": 95.0}}},
            }},
        ]}
        deals = {"records": [
            {"date": "2026-11-17", "verified_report_count": 2, "rows": [
                {"symbol": "COVER", "kind": "Block", "client": "BUY CLIENT",
                 "side": "BUY", "quantity": 50000, "price": 104.0},
                {"symbol": "UNWIND", "kind": "Bulk", "client": "SELL CLIENT",
                 "side": "SELL", "quantity": 60000, "price": 96.0},
                # Opposite-side deal must not be attached to either signal.
                {"symbol": "COVER", "kind": "Bulk", "client": "WRONG SIDE",
                 "side": "SELL", "quantity": 70000, "price": 104.0},
            ]}
        ]}
        report = build_report(archive, {"stocks": {"COVER": {}, "UNWIND": {}}},
                              fo_archive=fo_archive, deals_archive=deals)
        rows = {row["symbol"]: row for row in report["rows"]}
        self.assertEqual(rows["COVER"]["signal"], "SHORT COVERING")
        self.assertEqual(rows["COVER"]["strength"], "WATCH")
        self.assertEqual([d["client"] for d in rows["COVER"]["deal_evidence"]], ["BUY CLIENT"])
        self.assertEqual(rows["UNWIND"]["signal"], "LONG UNWINDING")
        self.assertEqual(rows["UNWIND"]["strength"], "WATCH")
        self.assertEqual([d["client"] for d in rows["UNWIND"]["deal_evidence"]], ["SELL CLIENT"])
        self.assertEqual(report["strength_summary"]["STRONG"], 0)
        self.assertEqual(report["strength_summary"]["WATCH"], 2)



    def test_source_coverage_is_independent_of_alert_rows(self):
        archive = {"records": [
            {"date": "2026-11-16", "equity_rows": [
                {"symbol": "ABC", "close": 100, "previous_close": 99, "volume": 100000},
            ]},
            {"date": "2026-11-17", "equity_rows": [
                {"symbol": "ABC", "close": 100, "previous_close": 100, "volume": 100000},
            ]},
        ]}
        fo_archive = {"records": [
            {"date": "2026-11-16", "stock_futures": {"ABC": {"available": True, "by_expiry": {
                "2026-11-26": {"open_interest": 1000, "close": 100.0}}}}},
            {"date": "2026-11-17", "stock_futures": {"ABC": {"available": True, "by_expiry": {
                "2026-11-26": {"open_interest": 1050, "close": 100.0}}}}},
        ]}
        delivery_archive = {"records": [
            {"date": "2026-11-17", "rows": {"ABC": {
                "delivery_qty": 50000, "delivery_pct": 50.0, "traded_qty": 100000}}},
        ]}
        deals_archive = {"records": [
            {"date": "2026-11-17", "verified_report_count": 2, "rows": []},
        ]}
        report = build_report(archive, {"stocks": {"ABC": {}}},
                              fo_archive=fo_archive,
                              delivery_archive=delivery_archive,
                              deals_archive=deals_archive)
        self.assertEqual(report["rows"], [])
        self.assertEqual(report["coverage"]["futures_oi"], "verified_for_matched_stock_futures")
        self.assertEqual(report["coverage_counts"]["fno_symbols_with_same_expiry_oi"], 1)
        self.assertEqual(report["coverage_counts"]["delivery_symbols_matched"], 1)
        self.assertEqual(report["coverage"]["delivery_pct"], "verified_for_matched_symbols")
        self.assertEqual(report["coverage_counts"]["bulk_block_reports_verified"], 2)
        self.assertEqual(report["coverage_counts"]["bulk_block_deal_rows"], 0)



    def test_zero_previous_oi_is_not_counted_as_usable_coverage(self):
        archive = {"records": [
            {"date": "2026-11-16", "equity_rows": [
                {"symbol": "ABC", "close": 100, "previous_close": 99, "volume": 100000}]},
            {"date": "2026-11-17", "equity_rows": [
                {"symbol": "ABC", "close": 100, "previous_close": 100, "volume": 100000}]},
        ]}
        fo_archive = {"records": [
            {"date": "2026-11-16", "stock_futures": {"ABC": {"available": True, "by_expiry": {
                "2026-11-26": {"open_interest": 0, "close": 100.0}}}}},
            {"date": "2026-11-17", "stock_futures": {"ABC": {"available": True, "by_expiry": {
                "2026-11-26": {"open_interest": 100, "close": 100.0}}}}},
        ]}
        report = build_report(archive, {"stocks": {"ABC": {}}}, fo_archive=fo_archive)
        self.assertEqual(report["coverage"]["futures_oi"], "not_yet_connected")
        self.assertEqual(report["coverage_counts"]["fno_symbols_with_same_expiry_oi"], 0)
        self.assertEqual(report["rows"], [])

    def test_futures_oi_and_disclosed_deals_survive_without_high_cash_volume(self):
        archive = {"records": [
            {"date": "2026-11-16", "equity_rows": [
                {"symbol": "ABC", "close": 100, "previous_close": 99, "volume": 100000},
                {"symbol": "BDEAL", "close": 50, "previous_close": 50, "volume": 50000},
            ]},
            {"date": "2026-11-17", "equity_rows": [
                {"symbol": "ABC", "close": 101, "previous_close": 100, "volume": 110000},
                {"symbol": "BDEAL", "close": 50, "previous_close": 50, "volume": 50000},
            ]},
        ]}
        fo_archive = {"records": [
            {"date": "2026-11-16", "stock_futures": {"ABC": {"available": True, "by_expiry": {
                "2026-11-26": {"open_interest": 1000, "close": 100.0}}}}},
            {"date": "2026-11-17", "stock_futures": {"ABC": {"available": True, "by_expiry": {
                "2026-11-26": {"open_interest": 1100, "close": 101.0}}}}},
        ]}
        deals_archive = {"records": [
            {"date": "2026-11-17", "verified_report_count": 2, "rows": [
                {"symbol": "BDEAL", "kind": "Bulk", "client": "DISCLOSED BUYER",
                 "side": "BUY", "quantity": 25000, "price": 50.0}
            ]}
        ]}
        report = build_report(archive, {"stocks": {"ABC": {}, "BDEAL": {}}},
                              fo_archive=fo_archive, deals_archive=deals_archive)
        by_symbol = {row["symbol"]: row for row in report["rows"]}
        self.assertEqual(by_symbol["ABC"]["signal"], "LONG BUILD-UP")
        self.assertEqual(by_symbol["ABC"]["volume_ratio"], 1.1)
        self.assertEqual(by_symbol["BDEAL"]["signal"], "DISCLOSED BUY DEAL WATCH")
        self.assertEqual(by_symbol["BDEAL"]["strength"], "WATCH")
        self.assertEqual(by_symbol["BDEAL"]["volume_ratio"], 1.0)



    def test_oi_signal_survives_when_cash_volume_baseline_is_unavailable(self):
        archive = {"records": [
            {"date": "2026-11-16", "equity_rows": [
                {"symbol": "ABC", "close": 100, "previous_close": 99, "volume": None}]},
            {"date": "2026-11-17", "equity_rows": [
                {"symbol": "ABC", "close": 101, "previous_close": 100, "volume": 50000}]},
        ]}
        fo_archive = {"records": [
            {"date": "2026-11-16", "stock_futures": {"ABC": {"available": True, "by_expiry": {
                "2026-11-26": {"open_interest": 1000, "close": 100.0}}}}},
            {"date": "2026-11-17", "stock_futures": {"ABC": {"available": True, "by_expiry": {
                "2026-11-26": {"open_interest": 1100, "close": 101.0}}}}},
        ]}
        report = build_report(archive, {"stocks": {"ABC": {}}}, fo_archive=fo_archive)
        row = report["rows"][0]
        self.assertEqual(row["signal"], "LONG BUILD-UP")
        self.assertIsNone(row["volume_ratio"])


    def test_oi_signal_survives_when_current_cash_volume_is_unavailable(self):
        archive = {"records": [
            {"date": "2026-11-16", "equity_rows": [
                {"symbol": "ABC", "close": 100, "previous_close": 99, "volume": 100000}]},
            {"date": "2026-11-17", "equity_rows": [
                {"symbol": "ABC", "close": 101, "previous_close": 100, "volume": None}]},
        ]}
        fo_archive = {"records": [
            {"date": "2026-11-16", "stock_futures": {"ABC": {"available": True, "by_expiry": {
                "2026-11-26": {"open_interest": 1000, "close": 100.0}}}}},
            {"date": "2026-11-17", "stock_futures": {"ABC": {"available": True, "by_expiry": {
                "2026-11-26": {"open_interest": 1100, "close": 101.0}}}}},
        ]}
        report = build_report(archive, {"stocks": {"ABC": {}}}, fo_archive=fo_archive)
        row = report["rows"][0]
        self.assertEqual(row["signal"], "LONG BUILD-UP")
        self.assertEqual(row["oi_change_pct"], 10.0)
        self.assertIsNone(row["volume"])
        self.assertIsNone(row["volume_ratio"])
        self.assertIn("Cash Volume", row["missing_fields"])
        self.assertTrue(any("कैश वॉल्यूम उपलब्ध नहीं" in item for item in row["evidence"]))


if __name__ == "__main__":
    unittest.main()
