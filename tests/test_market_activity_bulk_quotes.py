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

    def test_fetch_uses_current_nse_fno_bulk_route(self):
        class Response:
            def raise_for_status(self):
                return None
            def json(self):
                return self.payload

        response = Response()
        response.payload = self.payload
        parsed = {"coverage": {"expected": 2, "matched": 2}, "instruments": {"AAA": {}}}
        with patch.object(fetch_and_score, "NSE_DIRECT_WARMED", True), \
             patch.object(fetch_and_score.NSE_MCP_HTTP, "get", return_value=response) as get, \
             patch.object(fetch_and_score, "parse_nse_market_activity_bulk_payload", return_value=parsed):
            result = fetch_and_score.fetch_nse_market_activity_bulk_quotes({"AAA", "BBB"})
        self.assertEqual(result, parsed)
        self.assertIn("/api/equity-stockIndices?index=SECURITIES%20IN%20F%26O", get.call_args.args[0])

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
