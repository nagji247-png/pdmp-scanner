import unittest
import pandas as pd
from datetime import datetime, timedelta, timezone
from unittest import mock

import fetch_and_score


IST = timezone(timedelta(hours=5, minutes=30))


class WeekendPriceSourceRegressionTests(unittest.TestCase):
    def test_market_status_marks_sunday_closed_without_provider_request(self):
        sunday_utc = datetime(2026, 11, 8, 6, 0, tzinfo=timezone.utc)
        with mock.patch.object(fetch_and_score.yf, "Ticker") as ticker:
            self.assertTrue(fetch_and_score.market_closed_today(now_utc=sunday_utc))
        ticker.assert_not_called()

    def test_market_status_keeps_regular_monday_session_open(self):
        monday_utc = datetime(2026, 11, 9, 5, 30, tzinfo=timezone.utc)
        self.assertFalse(fetch_and_score.market_closed_today(now_utc=monday_utc))

    def test_market_status_marks_official_nse_weekday_holiday_closed(self):
        republic_day_utc = datetime(2026, 1, 26, 4, 0, tzinfo=timezone.utc)  # 09:30 IST
        with mock.patch.object(fetch_and_score.yf, "Ticker") as ticker:
            self.assertTrue(fetch_and_score.market_closed_today(now_utc=republic_day_utc))
        ticker.assert_not_called()

    def test_market_status_marks_diwali_balipratipada_holiday_closed(self):
        holiday_utc = datetime(2026, 11, 10, 4, 0, tzinfo=timezone.utc)  # 09:30 IST
        with mock.patch.object(fetch_and_score.yf, "Ticker") as ticker:
            self.assertTrue(fetch_and_score.market_closed_today(now_utc=holiday_utc))
        ticker.assert_not_called()

    def test_market_status_recognizes_diwali_muhurat_session_on_sunday(self):
        before_session_utc = datetime(2026, 11, 8, 8, 49, tzinfo=timezone.utc)  # 14:19 IST
        during_session_utc = datetime(2026, 11, 8, 8, 50, tzinfo=timezone.utc)  # 14:20 IST
        after_session_utc = datetime(2026, 11, 8, 10, 10, tzinfo=timezone.utc)  # 15:40 IST
        self.assertTrue(fetch_and_score.market_closed_today(now_utc=before_session_utc))
        self.assertFalse(fetch_and_score.market_closed_today(now_utc=during_session_utc))
        self.assertTrue(fetch_and_score.market_closed_today(now_utc=after_session_utc))

    def test_friday_mcx_close_remains_visible_on_saturday_evening(self):
        now = datetime(2026, 11, 7, 19, 45, tzinfo=IST)
        quote = {"source_time": "2026-11-06 23:54 IST"}
        self.assertTrue(fetch_and_score.mcx_reference_is_fresh(quote, now=now))
        self.assertFalse(fetch_and_score.mcx_reference_is_live(quote, now=now))

    def test_mcx_quote_older_than_four_days_is_rejected(self):
        now = datetime(2026, 11, 7, 19, 45, tzinfo=IST)
        quote = {"source_time": "2026-11-02 10:00 IST"}
        self.assertFalse(fetch_and_score.mcx_reference_is_fresh(quote, now=now))


    def test_mcx_prices_have_no_third_party_fallback(self):
        # MCX quote refresh is exchange-only; missing/stale quotes remain unavailable.
        self.assertTrue(callable(fetch_and_score.fetch_mcx_market_watch_rows))
        self.assertTrue(callable(fetch_and_score.parse_mcx_market_watch_rows))
        self.assertFalse(hasattr(fetch_and_score, "mcx_reference_fallback_needed"))
        self.assertFalse(hasattr(fetch_and_score, "parse_upstox_mcx_quote"))

    def test_nse_equity_friday_close_remains_valid_on_saturday_evening(self):
        now = datetime(2026, 11, 7, 19, 45, tzinfo=IST)
        payload = {
            "equityResponse": [{
                "metaData": {
                    "symbol": "RELIANCE",
                    "lastPrice": "1320.00",
                    "lastUpdateTime": "06-Nov-2026 15:30:00",
                    "previousClose": "1300.00",
                },
                "tradeInfo": {"lastPrice": "1320.00"},
            }]
        }
        quote = fetch_and_score.parse_nse_direct_equity_payload(
            "RELIANCE", payload, now=now
        )
        self.assertIsNotNone(quote)
        self.assertEqual(quote["price"], 1320.0)
        self.assertIn("पिछला बंद भाव", quote["source"])

    def test_nse_equity_quote_older_than_four_days_is_rejected(self):
        now = datetime(2026, 11, 7, 19, 45, tzinfo=IST)
        payload = {
            "equityResponse": [{
                "metaData": {
                    "symbol": "RELIANCE",
                    "lastPrice": "1320.00",
                    "lastUpdateTime": "02-Nov-2026 15:30:00",
                    "previousClose": "1300.00",
                },
                "tradeInfo": {"lastPrice": "1320.00"},
            }]
        }
        self.assertIsNone(fetch_and_score.parse_nse_direct_equity_payload(
            "RELIANCE", payload, now=now
        ))

    def test_yahoo_chart_fallback_stops_after_first_http_429(self):
        empty_history = pd.DataFrame(columns=["Close"])
        ticker = mock.Mock()
        ticker.history.return_value = empty_history
        throttled = mock.Mock(status_code=429)
        with mock.patch.object(fetch_and_score.yf, "Ticker", return_value=ticker), \
             mock.patch.object(fetch_and_score.requests, "get", return_value=throttled) as request:
            result = fetch_and_score.intraday_quote("INR=X")
        self.assertIsNone(result)
        self.assertEqual(request.call_count, 1)

    def test_usdinr_uses_recent_cached_reference_if_free_api_is_unavailable(self):
        today = datetime.now(timezone.utc).date()
        previous = {
            "reference_price": 93.89,
            "reference_date": (today - timedelta(days=1)).isoformat(),
        }
        with mock.patch.object(
            fetch_and_score.requests, "get",
            side_effect=RuntimeError("offline"),
        ) as request:
            result = fetch_and_score.fetch_usdinr_reference(previous)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(result["reference_price"], 93.89)
        self.assertTrue(result["reference_stale"])
        self.assertIn("लाइव नहीं", result["reference_source"])


if __name__ == "__main__":
    unittest.main()
