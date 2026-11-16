import datetime as dt
import json
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

    def test_index_parser_reads_niftyindices_double_json_response(self):
        payload = {"d": json.dumps([
            {"INDEX_NAME": "NIFTY 50", "HistoricalDate": "17 Nov 2025", "CLOSE": "25000"},
            {"INDEX_NAME": "NIFTY 50", "HistoricalDate": "14 Nov 2026", "CLOSE": "27500"},
        ])}
        rows = history.parse_index_history(payload, expected_index="NIFTY 50")
        self.assertEqual(rows[dt.date(2025, 11, 17)], 25000.0)
        self.assertEqual(rows[dt.date(2026, 11, 14)], 27500.0)

    def test_index_parser_accepts_official_financial_services_response_alias(self):
        payload = {"d": json.dumps([
            {"INDEX_NAME": "NIFTY FIN SERVICE", "HistoricalDate": "17 Nov 2025", "CLOSE": "25000"},
            {"INDEX_NAME": "NIFTY FIN SERVICE", "HistoricalDate": "14 Nov 2026", "CLOSE": "27500"},
        ])}
        self.assertEqual(
            len(history.parse_index_history(payload, expected_index="NIFTY FINANCIAL SERVICES")), 2
        )

    def test_index_parser_rejects_wrong_index_name(self):
        payload = {"d": json.dumps([
            {"INDEX_NAME": "NIFTY BANK", "HistoricalDate": "17 Nov 2025", "CLOSE": "25000"}
        ])}
        with self.assertRaisesRegex(ValueError, "name mismatch"):
            history.parse_index_history(payload, expected_index="NIFTY 50")

    def test_index_history_fetch_uses_one_official_post_request(self):
        from unittest.mock import Mock
        session = Mock()
        response = Mock(
            status_code=200,
            content=(
                b"\\xef\\xbb\\xbf" + json.dumps({"d": json.dumps([
                    {"INDEX_NAME": "NIFTY 50", "HistoricalDate": "14 Nov 2026", "CLOSE": "26000"}
                ])}).encode("utf-8")
            ),
            headers={"Content-Type": "application/json"},
            url="https://www.niftyindices.com/Backpage.aspx/getHistoricaldatatabletoString",
        )
        session.post.return_value = response
        rows, url = history.fetch_index_history(
            session, "NIFTY 50", dt.date(2025, 11, 16), dt.date(2026, 11, 16)
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(session.post.call_count, 1)
        payload = session.post.call_args.kwargs["json"]
        self.assertIn("'name':'NIFTY 50'", payload["cinfo"])
        self.assertIn("'startDate':'16 Nov 2025'", payload["cinfo"])
        self.assertEqual(url, response.url)

    def test_healthcare_index_uses_verified_official_long_name(self):
        from unittest.mock import Mock
        session = Mock()
        response = Mock(
            status_code=200,
            content=json.dumps({"d": json.dumps([
                {"INDEX_NAME": "NIFTY HEALTHCARE", "HistoricalDate": "14 Nov 2026", "CLOSE": "15000"}
            ])}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            url="https://www.niftyindices.com/Backpage.aspx/getHistoricaldatatabletoString",
        )
        session.post.return_value = response
        history.fetch_index_history(
            session, "NIFTY HEALTHCARE", dt.date(2025, 11, 16), dt.date(2026, 11, 16)
        )
        cinfo = session.post.call_args.kwargs["json"]["cinfo"]
        self.assertIn("'name':'NIFTY HEALTHCARE INDEX'", cinfo)
        self.assertIn("'indexName':'NIFTY HEALTHCARE'", cinfo)

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

    def test_sector_crosswalk_uses_current_official_sector_index_names(self):
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

    def test_session_bootstrap_continues_after_http_403(self):
        from unittest.mock import Mock, patch
        session = Mock()
        session.get.side_effect = [Mock(status_code=403), Mock(status_code=200)]
        with patch.object(history.time, "sleep"):
            history.seed_session(session)
        self.assertEqual(session.get.call_count, 2)
        self.assertIn("/report-detail/eq_security", session.get.call_args_list[1].args[0])

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
