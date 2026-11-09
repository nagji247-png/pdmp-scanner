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


    def test_mcx_public_fallback_skips_a_fresh_cached_quote_during_session(self):
        now = datetime(2026, 11, 9, 10, 0, tzinfo=IST)
        quote = {"source_time": "2026-11-09 09:30 IST"}
        self.assertFalse(fetch_and_score.mcx_reference_fallback_needed(quote, now=now))

    def test_mcx_public_fallback_runs_for_a_stale_quote_during_session(self):
        now = datetime(2026, 11, 9, 10, 0, tzinfo=IST)
        quote = {"source_time": "2026-11-09 09:00 IST"}
        self.assertTrue(fetch_and_score.mcx_reference_fallback_needed(quote, now=now))

    def test_mcx_public_fallback_skips_when_quote_is_missing_outside_session(self):
        now = datetime(2026, 11, 7, 19, 45, tzinfo=IST)
        self.assertFalse(fetch_and_score.mcx_reference_fallback_needed({}, now=now))

    def test_mcx_public_fallback_skips_stale_quote_after_market_hours(self):
        now = datetime(2026, 11, 9, 23, 45, tzinfo=IST)
        quote = {"source_time": "2026-11-09 20:00 IST"}
        self.assertFalse(fetch_and_score.mcx_reference_fallback_needed(quote, now=now))

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
            fetch_and_score, "intraday_quote", return_value=None
        ) as quote:
            result = fetch_and_score.fetch_usdinr_reference(previous)
        quote.assert_called_once_with("INR=X")
        self.assertEqual(result["reference_price"], 93.89)
        self.assertTrue(result["reference_stale"])
        self.assertIn("लाइव नहीं", result["reference_source"])


if __name__ == "__main__":
    unittest.main()
