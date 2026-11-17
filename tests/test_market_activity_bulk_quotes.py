import unittest
from datetime import datetime, timedelta, timezone
import fetch_and_score
from market_activity_eod import build_nse_eod_market_activity_quotes

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

class NSEMarketActivityEODFallbackTests(unittest.TestCase):
    def test_uses_latest_official_session_and_exact_eq_symbols(self):
        now = datetime(2026, 11, 17, 11, 44, tzinfo=IST)
        archive = {"records": [
            {"date": "2026-11-13", "equity_rows": [
                {"symbol": "AAA", "series": "EQ", "close": 100, "previous_close": 98, "volume": 10}
            ]},
            {"date": "2026-11-16", "equity_rows": [
                {"symbol": "AAA", "series": "EQ", "close": 110, "previous_close": 100, "volume": 20},
                {"symbol": "BBB", "series": "EQ", "close": 90, "previous_close": 100, "volume": 30},
                {"symbol": "CCC", "series": "BE", "close": 50, "previous_close": 45, "volume": 40},
                {"symbol": "NOT_EXPECTED", "series": "EQ", "close": 5, "previous_close": 4, "volume": 1},
            ]},
        ]}
        result = build_nse_eod_market_activity_quotes(archive, {"AAA", "BBB"}, now=now)
        self.assertEqual(result["coverage"], {
            "expected": 2, "matched": 2, "live_matched": 0, "eod_matched": 2
        })
        self.assertEqual(result["instruments"]["AAA"]["price"], 110)
        self.assertEqual(result["instruments"]["AAA"]["change_pct"], 10.0)
        self.assertEqual(result["instruments"]["BBB"]["change_pct"], -10.0)
        self.assertEqual(result["instruments"]["AAA"]["quote_kind"], "eod")
        self.assertEqual(result["instruments"]["AAA"]["price_as_of"], "16/11/2026")
        self.assertNotIn("CCC", result["instruments"])
        self.assertNotIn("NOT_EXPECTED", result["instruments"])

    def test_rejects_future_or_over_age_archive_sessions(self):
        now = datetime(2026, 11, 17, 11, 44, tzinfo=IST)
        for day in ("2026-11-18", "2026-11-01"):
            result = build_nse_eod_market_activity_quotes(
                {"records": [{"date": day, "equity_rows": [
                    {"symbol": "AAA", "series": "EQ", "close": 100, "previous_close": 99}
                ]}]}, {"AAA"}, now=now
            )
            self.assertEqual(result["coverage"]["matched"], 0)
            self.assertIsNone(result["source_timestamp"])

    def test_rejects_invalid_close_and_previous_close(self):
        now = datetime(2026, 11, 17, 11, 44, tzinfo=IST)
        result = build_nse_eod_market_activity_quotes(
            {"records": [{"date": "2026-11-16", "equity_rows": [
                {"symbol": "AAA", "series": "EQ", "close": 0, "previous_close": 99},
                {"symbol": "BBB", "series": "EQ", "close": 100, "previous_close": "bad"},
            ]}]}, {"AAA", "BBB"}, now=now
        )
        self.assertEqual(result["coverage"]["matched"], 0)


if __name__ == "__main__":
    unittest.main()
