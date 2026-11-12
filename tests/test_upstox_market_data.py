import unittest
from unittest.mock import Mock

from upstox_market_data import fetch_upstox_candles, instrument_key_for


class UpstoxMarketDataTests(unittest.TestCase):
    def test_known_index_and_equity_keys(self):
        self.assertEqual(instrument_key_for("^NSEI"), "NSE_INDEX|Nifty 50")
        self.assertEqual(instrument_key_for("^NSEBANK"), "NSE_INDEX|Nifty Bank")
        self.assertEqual(instrument_key_for("RELIANCE.NS"), "NSE_EQ|INE002A01018")
        self.assertIsNone(instrument_key_for("^BSESN"))

    def test_fetches_and_normalizes_v3_candles(self):
        session = Mock()
        session.get.return_value = Mock(status_code=200, json=lambda: {
            "status": "success",
            "data": {"candles": [
                ["2026-11-12T09:15:00+05:30", 100, 105, 99, 104, 1000, 20],
                ["2026-11-12T09:45:00+05:30", 104, 106, 103, 105, 1200, 21],
            ]},
        })
        rows = fetch_upstox_candles("^NSEI", 30, token="test-token", session=session)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["close"], 104.0)
        self.assertEqual(rows[0]["volume"], 1000.0)
        self.assertEqual(rows[0]["open_interest"], 20.0)
        self.assertEqual(rows[0]["source"], "Upstox API V3")
        self.assertEqual(session.get.call_count, 1)
        self.assertIn("NSE_INDEX%7CNifty%2050", session.get.call_args.args[0])
        self.assertEqual(session.get.call_args.kwargs["headers"]["Authorization"], "Bearer test-token")

    def test_invalid_ohlc_rows_are_rejected(self):
        session = Mock()
        session.get.return_value = Mock(status_code=200, json=lambda: {
            "status": "success",
            "data": {"candles": [
                ["2026-11-12T09:15:00+05:30", 100, 98, 99, 104, 1000, 0],
            ]},
        })
        self.assertEqual(fetch_upstox_candles("^NSEI", 30, token="test-token", session=session), [])

    def test_missing_token_and_unknown_instrument_do_not_request(self):
        session = Mock()
        self.assertEqual(fetch_upstox_candles("^NSEI", 30, token="", session=session), [])
        self.assertEqual(fetch_upstox_candles("^BSESN", 30, token="test-token", session=session), [])
        session.get.assert_not_called()

    def test_bad_interval_does_not_request(self):
        session = Mock()
        self.assertEqual(fetch_upstox_candles("^NSEI", 301, token="test-token", session=session), [])
        session.get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
