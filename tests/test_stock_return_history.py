import datetime as dt
import unittest

import stock_return_history as history


class StockReturnHistoryTests(unittest.TestCase):
    def test_stock_csv_parser_keeps_only_requested_eq_symbol(self):
        payload = (
            "Date,Symbol,Series,Close Price\n"
            "17-11-2025,RELIANCE,EQ,1200\n"
            "16-11-2025,RELIANCE,BE,1190\n"
            "17-11-2025,HDFCBANK,EQ,800\n"
            "14-11-2026,RELIANCE,EQ,1500\n"
        )
        rows = history.parse_stock_history_csv(payload, "RELIANCE")
        self.assertEqual(rows, {
            dt.date(2025, 11, 17): 1200.0,
            dt.date(2026, 11, 14): 1500.0,
        })

    def test_stock_csv_duplicate_eq_date_fails_closed(self):
        payload = (
            "Date,Symbol,Series,Close Price\n"
            "17-11-2025,RELIANCE,EQ,1200\n"
            "17-11-2025,RELIANCE,EQ,1201\n"
        )
        with self.assertRaisesRegex(ValueError, "duplicate EQ date"):
            history.parse_stock_history_csv(payload, "RELIANCE")

    def test_index_parser_reads_official_nse_close_records(self):
        payload = {"data": {"indexCloseOnlineRecords": [
            {"EOD_TIMESTAMP": "17-Nov-2025", "EOD_CLOSE_INDEX_VAL": "25000"},
            {"EOD_TIMESTAMP": "14-Nov-2026", "EOD_CLOSE_INDEX_VAL": "27500"},
        ]}}
        rows = history.parse_index_history(payload)
        self.assertEqual(rows[dt.date(2025, 11, 17)], 25000.0)
        self.assertEqual(rows[dt.date(2026, 11, 14)], 27500.0)

    def test_one_year_return_uses_latest_date_and_first_session_after_target(self):
        rows = {
            dt.date(2025, 11, 17): 100.0,
            dt.date(2026, 1, 2): 110.0,
            dt.date(2026, 11, 14): 125.0,
        }
        result = history.calculate_price_return(rows, today=dt.date(2026, 11, 16))
        self.assertEqual(result["start_date"], "2025-11-17")
        self.assertEqual(result["end_date"], "2026-11-14")
        self.assertEqual(result["return_pct"], 25.0)
        self.assertFalse(result["corporate_actions_adjusted"])

    def test_stale_or_insufficient_history_is_withheld(self):
        rows = {
            dt.date(2025, 11, 17): 100.0,
            dt.date(2026, 10, 1): 110.0,
        }
        self.assertIsNone(history.calculate_price_return(rows, today=dt.date(2026, 11, 16)))
        short = {
            dt.date(2026, 1, 2): 100.0,
            dt.date(2026, 11, 14): 110.0,
        }
        self.assertIsNone(history.calculate_price_return(short, today=dt.date(2026, 11, 16)))

    def test_sector_and_market_must_match_exact_stock_dates(self):
        rows = {
            dt.date(2025, 11, 17): 200.0,
            dt.date(2026, 11, 14): 220.0,
        }
        result = history.calculate_return_for_same_dates(
            rows, "2025-11-17", "2026-11-14"
        )
        self.assertEqual(result["return_pct"], 10.0)
        self.assertIsNone(history.calculate_return_for_same_dates(
            {dt.date(2025, 11, 18): 200.0, dt.date(2026, 11, 14): 220.0},
            "2025-11-17", "2026-11-14"
        ))

    def test_sector_crosswalk_is_exact_and_does_not_guess_broad_categories(self):
        self.assertEqual(history.SECTOR_INDEX["Information Technology"], "NIFTY IT")
        self.assertEqual(history.SECTOR_INDEX["Healthcare"], "NIFTY HEALTHCARE")
        self.assertNotIn("Services", history.SECTOR_INDEX)
        self.assertNotIn("Construction Materials", history.SECTOR_INDEX)
        self.assertNotIn("Textiles", history.SECTOR_INDEX)

    def test_stock_history_fetch_uses_one_request_without_retry(self):
        from unittest.mock import Mock
        session = Mock()
        session.get.return_value = Mock(
            status_code=200,
            content=b"Date,Symbol,Series,Close Price\n14-11-2026,RELIANCE,EQ,1500\n",
            url="https://www.nseindia.com/history",
        )
        rows, url = history.fetch_stock_history(
            session, "RELIANCE", dt.date(2025, 11, 1), dt.date(2026, 11, 16)
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(session.get.call_count, 1)
        self.assertEqual(url, "https://www.nseindia.com/history")


if __name__ == "__main__":
    unittest.main()
