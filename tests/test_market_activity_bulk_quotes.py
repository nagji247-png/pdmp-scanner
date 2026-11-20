import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
import fetch_and_score

IST = timezone(timedelta(hours=5, minutes=30))

class NSEMarketActivityBulkQuoteTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 15, 18, 0, tzinfo=IST)
        self.payload = {"timestamp": "13-Nov-2026 15:30:00", "data": [
            {"symbol": "AAA", "lastPrice": 123.45, "pChange": 1.25, "totalTradedVolume": 123456},
            {"symbol": "BBB", "lastPrice": 80, "pChange": -0.5, "totalTradedVolume": 9876},
            {"symbol": "NOT_IN_MASTER", "lastPrice": 999, "pChange": 9, "totalTradedVolume": 999999},
        ]}

    def test_maps_exact_master_symbols_and_real_price_change_volume(self):
        result = fetch_and_score.parse_nse_market_activity_bulk_payload(self.payload, {"AAA", "BBB"}, now=self.now)
        self.assertEqual(result["coverage"], {"expected": 2, "matched": 2})
        self.assertEqual(result["instruments"]["AAA"]["price"], 123.45)
        self.assertEqual(result["instruments"]["AAA"]["change_pct"], 1.25)
        self.assertEqual(result["instruments"]["AAA"]["volume"], 123456)
        self.assertEqual(result["instruments"]["BBB"]["change_pct"], -0.5)
        self.assertNotIn("NOT_IN_MASTER", result["instruments"])
        self.assertEqual(result["instruments"]["AAA"]["price_as_of"], "13/11/2026")

    def test_adapts_nse_mcp_equity_batch_and_preserves_exchange_timestamp(self):
        rows = [
            {"type": "CM", "symbol": "AAA", "series": "EQ",
             "lastTradedPrice": 123.45, "perChange": 1.25, "volume": 123456,
             "latestTimestamp": "2026-11-19 16:00:28"},
            {"type": "CM", "symbol": "BBB", "series": "EQ",
             "lastTradedPrice": 80, "perChange": -0.5, "volume": 9876,
             "latestTimestamp": "2026-11-19 16:00:28"},
            {"type": "CM", "symbol": "NOT_IN_MASTER", "series": "EQ",
             "lastTradedPrice": 999, "perChange": 9, "volume": 999999,
             "latestTimestamp": "2026-11-19 16:00:28"},
            {"type": "OPTFUT", "symbol": "AAA", "series": "EQ",
             "lastTradedPrice": 500, "perChange": 5, "volume": 10,
             "latestTimestamp": "2026-11-19 16:00:28"},
        ]
        now = datetime(2026, 11, 19, 16, 5, tzinfo=IST)
        result = fetch_and_score.parse_nse_mcp_equity_stocks(rows, {"AAA", "BBB"}, now=now)
        self.assertEqual(result["coverage"], {"expected": 2, "matched": 2})
        self.assertEqual(result["instruments"]["AAA"]["price"], 123.45)
        self.assertEqual(result["instruments"]["AAA"]["change_pct"], 1.25)
        self.assertEqual(result["instruments"]["AAA"]["volume"], 123456)
        self.assertEqual(result["instruments"]["BBB"]["change_pct"], -0.5)
        self.assertEqual(result["instruments"]["AAA"]["price_as_of"], "19/11/2026")
        self.assertEqual(result["source_timestamp"], "19-Nov-2026 16:00:28")
        self.assertNotIn("NOT_IN_MASTER", result["instruments"])

    def test_mcp_adapter_rejects_stale_or_missing_timestamps(self):
        now = datetime(2026, 11, 20, 10, 0, tzinfo=IST)
        rows = [
            {"type": "CM", "symbol": "AAA", "series": "EQ",
             "lastTradedPrice": 123.45, "perChange": 1.25, "volume": 123456,
             "latestTimestamp": "2026-11-19 16:00:28"},
            {"type": "CM", "symbol": "BBB", "series": "EQ",
             "lastTradedPrice": 80, "perChange": -0.5, "volume": 9876},
        ]
        result = fetch_and_score.parse_nse_mcp_equity_stocks(rows, {"AAA", "BBB"}, now=now)
        self.assertEqual(result["coverage"], {"expected": 2, "matched": 0})
        self.assertEqual(result["instruments"], {})
        self.assertIsNone(result["source_timestamp"])

    def test_mcp_adapter_rejects_invalid_prices_and_keeps_zero_volume(self):
        now = datetime(2026, 11, 19, 16, 5, tzinfo=IST)
        rows = [
            {"type": "CM", "symbol": "AAA", "series": "EQ",
             "lastTradedPrice": 0, "perChange": 1, "volume": 2,
             "latestTimestamp": "2026-11-19 16:00:28"},
            {"type": "CM", "symbol": "BBB", "series": "EQ",
             "lastTradedPrice": 80, "perChange": 0, "volume": 0,
             "latestTimestamp": "2026-11-19 16:00:28"},
        ]
        result = fetch_and_score.parse_nse_mcp_equity_stocks(rows, {"AAA", "BBB"}, now=now)
        self.assertEqual(result["coverage"]["matched"], 1)
        self.assertEqual(result["instruments"]["BBB"]["volume"], 0)
        self.assertNotIn("AAA", result["instruments"])

    def test_retired_intraday_bulk_route_is_not_called(self):
        with patch.object(fetch_and_score.NSE_MCP_HTTP, "get") as get:
            result = fetch_and_score.fetch_nse_market_activity_bulk_quotes({"AAA", "BBB"})
        get.assert_not_called()
        self.assertEqual(result["coverage"], {"expected": 2, "matched": 0})
        self.assertIn("retired", result["source"])
    def test_full_eod_snapshot_includes_all_cm_eq_and_delivery_fields(self):
        csv_text = """SYMBOL,SERIES,DATE1,PREV_CLOSE,OPEN_PRICE,HIGH_PRICE,LOW_PRICE,LAST_PRICE,CLOSE_PRICE,AVG_PRICE,TTL_TRD_QNTY,TURNOVER_LACS,NO_OF_TRADES,DELIV_QTY,DELIV_PER
FNOAAA,EQ,19-Nov-2026,100,101,105,99,104,103,102,123456,1260,5000,60000,48.5
CASHBBB,EQ,19-Nov-2026,80,81,82,79,80,80,80,900,1,20,450,50
BEONLY,BE,19-Nov-2026,50,51,52,49,50,50,50,100,1,5,40,40
"""
        trade_date = datetime(2026, 11, 19).date()
        result = fetch_and_score.parse_nse_eod_bhavdata_csv(csv_text, None, expected_date=trade_date)
        self.assertEqual(result["scope"], "CM/EQ")
        self.assertEqual(result["coverage"], {"expected": 2, "matched": 2})
        self.assertEqual(set(result["instruments"]), {"FNOAAA", "CASHBBB"})
        self.assertEqual(result["instruments"]["FNOAAA"]["delivery_qty"], 60000)
        self.assertEqual(result["instruments"]["FNOAAA"]["delivery_pct"], 48.5)
        self.assertEqual(result["instruments"]["FNOAAA"]["trades"], 5000)
        self.assertNotIn("BEONLY", result["instruments"])

    def test_parses_official_eod_bhavdata_for_exact_eq_symbols(self):
        csv_text = """SYMBOL,SERIES,DATE1,PREV_CLOSE,OPEN_PRICE,HIGH_PRICE,LOW_PRICE,LAST_PRICE,CLOSE_PRICE,AVG_PRICE,TTL_TRD_QNTY,TURNOVER_LACS,NO_OF_TRADES,DELIV_QTY,DELIV_PER
AAA,EQ,13-Nov-2026,100,101,105,99,104,103,102,123456,1260,5000,60000,48.5
BBB,BE,13-Nov-2026,80,81,82,79,80,80,80,900,1,20,0,0
NOT_IN_MASTER,EQ,13-Nov-2026,10,10,11,9,11,11,10,100,1,5,50,50
"""
        trade_date = datetime(2026, 11, 13).date()
        result = fetch_and_score.parse_nse_eod_bhavdata_csv(csv_text, {"AAA", "BBB"}, expected_date=trade_date)
        self.assertEqual(result["coverage"], {"expected": 2, "matched": 1})
        self.assertEqual(result["instruments"]["AAA"]["price"], 103.0)
        self.assertEqual(result["instruments"]["AAA"]["previous_close"], 100.0)
        self.assertEqual(result["instruments"]["AAA"]["change_pct"], 3.0)
        self.assertEqual(result["instruments"]["AAA"]["volume"], 123456)
        self.assertEqual(result["instruments"]["AAA"]["vwap"], 102.0)
        self.assertIn("EOD", result["source"])

    def test_reuses_same_day_full_eod_snapshot_after_1800_ist(self):
        snapshot = {"source": "NSE official sec_bhavdata_full · EOD previous close · CM/EQ",
                    "source_timestamp": "20-Nov-2026 15:30:00"}
        now = datetime(2026, 11, 20, 23, 0, tzinfo=IST)
        self.assertTrue(fetch_and_score.cached_nse_eod_bhavdata_is_current(snapshot, now=now))

    def test_reuses_previous_weekday_eod_snapshot_before_1800_ist(self):
        snapshot = {"source": "NSE official sec_bhavdata_full · EOD previous close · CM/EQ",
                    "source_timestamp": "20-Nov-2026 15:30:00"}
        now = datetime(2026, 11, 21, 12, 0, tzinfo=IST)
        self.assertTrue(fetch_and_score.cached_nse_eod_bhavdata_is_current(snapshot, now=now))

    def test_does_not_reuse_old_eod_snapshot_after_new_trading_day_close(self):
        snapshot = {"source": "NSE official sec_bhavdata_full · EOD previous close · CM/EQ",
                    "source_timestamp": "20-Nov-2026 15:30:00"}
        now = datetime(2026, 11, 23, 19, 0, tzinfo=IST)
        self.assertFalse(fetch_and_score.cached_nse_eod_bhavdata_is_current(snapshot, now=now))

    def test_reuses_latest_session_across_nse_holiday(self):
        snapshot = {"source": "NSE official sec_bhavdata_full · EOD previous close · CM/EQ",
                    "source_timestamp": "23-Nov-2026 15:30:00"}
        holiday_evening = datetime(2026, 11, 24, 19, 0, tzinfo=IST)
        self.assertTrue(fetch_and_score.cached_nse_eod_bhavdata_is_current(snapshot, now=holiday_evening))

    def test_does_not_expect_holiday_eod_snapshot(self):
        snapshot = {"source": "NSE official sec_bhavdata_full · EOD previous close · CM/EQ",
                    "source_timestamp": "24-Nov-2026 15:30:00"}
        holiday_evening = datetime(2026, 11, 24, 19, 0, tzinfo=IST)
        self.assertFalse(fetch_and_score.cached_nse_eod_bhavdata_is_current(snapshot, now=holiday_evening))

    def test_eod_reference_remains_available_during_next_cash_session(self):
        snapshot = {"source": "NSE official sec_bhavdata_full · EOD previous close",
                    "source_timestamp": "13-Nov-2026 15:30:00"}
        during_session = datetime(2026, 11, 16, 10, 0, tzinfo=IST)
        self.assertTrue(fetch_and_score.market_activity_snapshot_is_fresh(snapshot, now=during_session))
        too_old = datetime(2026, 11, 19, 10, 0, tzinfo=IST)
        self.assertFalse(fetch_and_score.market_activity_snapshot_is_fresh(snapshot, now=too_old))
    def test_rejects_missing_exchange_timestamp(self):
        payload = dict(self.payload); payload.pop("timestamp")
        with self.assertRaisesRegex(ValueError, "exchange timestamp"):
            fetch_and_score.parse_nse_market_activity_bulk_payload(payload, {"AAA"}, now=self.now)

    def test_rejects_stale_exchange_timestamp(self):
        payload = dict(self.payload); payload["timestamp"] = "02-Nov-2026 15:30:00"
        with self.assertRaisesRegex(ValueError, "outside"):
            fetch_and_score.parse_nse_market_activity_bulk_payload(payload, {"AAA"}, now=self.now)

    def test_rejects_invalid_or_nonpositive_prices(self):
        payload = {"timestamp": "13-Nov-2026 15:30:00", "data": [
            {"symbol": "AAA", "lastPrice": 0, "pChange": 1, "totalTradedVolume": 2},
            {"symbol": "BBB", "lastPrice": "bad", "pChange": -1, "totalTradedVolume": 2}]}
        result = fetch_and_score.parse_nse_market_activity_bulk_payload(payload, {"AAA", "BBB"}, now=self.now)
        self.assertEqual(result["coverage"]["matched"], 0)
        self.assertEqual(result["instruments"], {})

    def test_cached_snapshot_respects_closed_market_age_limit(self):
        self.assertTrue(fetch_and_score.market_activity_snapshot_is_fresh({"source_timestamp": "13-Nov-2026 15:30:00"}, now=self.now))
        self.assertFalse(fetch_and_score.market_activity_snapshot_is_fresh({"source_timestamp": "10-Nov-2026 15:30:00"}, now=self.now))

if __name__ == "__main__":
    unittest.main()
