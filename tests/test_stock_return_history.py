import datetime as dt
import unittest
from unittest.mock import Mock, patch

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

    def test_same_date_benchmark_return_requires_both_exact_archive_sessions(self):
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

    def test_index_archive_series_maps_verified_display_name_and_source(self):
        archive = {"records": [
            {
                "date": "2025-11-17",
                "source_url": "https://nsearchives.nseindia.com/old.csv",
                "indices": {"Nifty 50": 25000, "Nifty Auto": 20000},
            },
            {
                "date": "2026-11-14",
                "source_url": "https://nsearchives.nseindia.com/new.csv",
                "indices": {"Nifty 50": 27500, "Nifty Auto": 22000},
            },
        ]}
        series, sources = history.build_index_series(archive, "NIFTY AUTO")
        self.assertEqual(series[dt.date(2025, 11, 17)], 20000.0)
        self.assertEqual(series[dt.date(2026, 11, 14)], 22000.0)
        self.assertEqual(sources[dt.date(2026, 11, 14)], "https://nsearchives.nseindia.com/new.csv")

    def test_archived_benchmark_return_contains_source_urls(self):
        archive = {"records": [
            {"date": "2025-11-17", "source_url": "old.csv", "indices": {"Nifty 50": 25000}},
            {"date": "2026-11-14", "source_url": "new.csv", "indices": {"Nifty 50": 27500}},
        ]}
        result = history.calculate_archived_benchmark_return(
            archive, "NIFTY 50", "2025-11-17", "2026-11-14"
        )
        self.assertEqual(result["return_pct"], 10.0)
        self.assertEqual(result["start_source_url"], "old.csv")
        self.assertEqual(result["end_source_url"], "new.csv")

    def test_missing_or_mismatched_index_history_is_withheld(self):
        archive = {"records": [
            {"date": "2025-11-18", "indices": {"Nifty Bank": 50000}},
            {"date": "2026-11-14", "indices": {"Nifty Bank": 55000}},
        ]}
        self.assertIsNone(history.calculate_archived_benchmark_return(
            archive, "NIFTY 50", "2025-11-17", "2026-11-14"
        ))

    def test_cached_stock_period_preserves_same_dates_and_price_basis(self):
        result = history.cached_stock_period({
            "start_date": "2025-11-17",
            "end_date": "2026-11-14",
            "start_close": 100,
            "end_close": 125,
            "return_pct": 25,
        })
        self.assertEqual(result["return_pct"], 25.0)
        self.assertFalse(result["dividends_included"])
        self.assertIsNone(history.cached_stock_period({"start_date": "bad"}))

    def test_sector_crosswalk_uses_exact_official_sector_indices_only(self):
        self.assertEqual(history.SECTOR_INDEX["Information Technology"], "NIFTY IT")
        self.assertEqual(history.SECTOR_INDEX["Healthcare"], "NIFTY HEALTHCARE")
        self.assertEqual(history.SECTOR_INDEX["Capital Goods"], "NIFTY CAPITAL GOODS")
        self.assertEqual(history.SECTOR_INDEX["Consumer Services"], "NIFTY CONSUMER SERVICES")
        self.assertEqual(history.SECTOR_INDEX["Telecommunication"], "NIFTY TELECOMMUNICATIONS")
        self.assertEqual(history.SECTOR_INDEX["Power"], "NIFTY POWER")
        self.assertEqual(history.SECTOR_INDEX["Oil, Gas & Consumable Fuels"], "NIFTY OIL AND GAS INDEX")
        self.assertNotIn("Services", history.SECTOR_INDEX)
        self.assertNotIn("Construction Materials", history.SECTOR_INDEX)
        self.assertNotIn("Textiles", history.SECTOR_INDEX)

    def test_stock_history_fetch_uses_one_request_without_retry(self):
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
