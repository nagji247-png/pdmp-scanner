import json
import unittest
from pathlib import Path

import stock_company_research as research


class StockCompanyResearchTests(unittest.TestCase):
    def test_complete_company_batch_advances_cursor(self):
        self.assertEqual(research.next_batch_cursor(0, 10, 10, 218), 10)
        self.assertEqual(research.next_batch_cursor(210, 10, 10, 218), 2)

    def test_partial_company_batch_retries_same_cursor(self):
        self.assertEqual(research.next_batch_cursor(20, 10, 9, 218), 20)
        self.assertEqual(research.next_batch_cursor(20, 10, 0, 218), 20)

    def test_empty_universe_cursor_is_not_advanced(self):
        self.assertEqual(research.next_batch_cursor(0, 10, 10, 0), 0)

    def test_company_quote_extracts_only_present_nse_fields(self):
        payload = {
            "info": {"companyName": "Example Industries Limited", "isin": "INE123A01010"},
            "industryInfo": {"macro": "Industrials", "sector": "Capital Goods", "industry": "Engineering"},
            "priceInfo": {"lastPrice": "125.50", "pChange": "1.25"},
            "securityInfo": {"faceValue": "2"},
        }
        trade = {"marketDeptOrderBook": {"tradeInfo": {"totalMarketCap": "1234.56"}}}
        result = research.parse_company_quote(payload, trade)
        self.assertEqual(result["company_name"], "Example Industries Limited")
        self.assertEqual(result["nse_sector"], "Capital Goods")
        self.assertEqual(result["industry"], "Engineering")
        self.assertEqual(result["price"], 125.5)
        self.assertEqual(result["change_pct"], 1.25)
        self.assertEqual(result["market_cap_cr"], 1234.56)
        self.assertIsNone(result["quote_timestamp"])

    def test_shareholding_uses_latest_quarter_and_real_previous_quarter(self):
        rows = [
            {"date": "31-MAR-2026", "pr_and_prgrp": "50", "public_val": "50", "employeeTrusts": "0"},
            {"date": "30-SEP-2026", "pr_and_prgrp": "49.5", "public_val": "50.5", "employeeTrusts": "0"},
            {"date": "30-JUN-2026", "pr_and_prgrp": "49.8", "public_val": "50.2", "employeeTrusts": "0"},
        ]
        result = research.parse_shareholding(rows)
        self.assertEqual(result["as_of"], "30-SEP-2026")
        self.assertEqual(result["previous_as_of"], "30-JUN-2026")
        self.assertEqual(result["promoter_pct"], 49.5)
        self.assertEqual(result["public_pct"], 50.5)
        self.assertAlmostEqual(result["promoter_change_pp"], -0.3, places=4)
        self.assertAlmostEqual(result["public_change_pp"], 0.3, places=4)

    def test_missing_fii_dii_are_not_fabricated(self):
        result = research.parse_shareholding([
            {"date": "30-SEP-2026", "pr_and_prgrp": "60", "public_val": "40"}
        ])
        self.assertNotIn("fii_pct", result)
        self.assertNotIn("dii_pct", result)

    def test_empty_shareholding_is_unavailable(self):
        self.assertIsNone(research.parse_shareholding([]))
        self.assertIsNone(research.parse_shareholding({"data": []}))


    def test_latest_integrated_filing_prefers_newest_trusted_nse_archive(self):
        result = research.latest_integrated_filing({"data": [
            {"broadcastDate": "14-Nov-2026 10:00:00", "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/new.xml"},
            {"broadcastDate": "13-Nov-2026 10:00:00", "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/old.xml"},
            {"broadcastDate": "15-Nov-2026 10:00:00", "xbrl": "https://evil.example/corporate/xbrl/fake.xml"},
        ]})
        self.assertEqual(result["url"], "https://nsearchives.nseindia.com/corporate/xbrl/new.xml")

    def test_latest_integrated_filing_accepts_official_nseindia_in_archive_host(self):
        url = "https://nsearchives.nseindia.in/corporate/xbrl/INTEGRATED_FILING_NBFC_INDAS_1739317_15102026070629_WEB.xml"
        result = research.latest_integrated_filing({"data": [{"qe_Date": "30-SEP-2026", "xbrl": url}]})
        self.assertIsNotNone(result)
        self.assertEqual(result["url"], url)

    def test_latest_integrated_filing_uses_broadcast_time_for_same_day_rows(self):
        result = research.latest_integrated_filing({"data": [
            {"broadcast_Date": "14-Nov-2026 09:15:00",
             "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/early.xml"},
            {"broadcast_Date": "14-Nov-2026 16:45:00",
             "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/late.xml"},
        ]})
        self.assertTrue(result["url"].endswith("late.xml"))

    def test_latest_integrated_filing_supports_nse_native_metadata_keys(self):
        result = research.latest_integrated_filing({"data": [
            {"broadcast_Date": "14-Nov-2026 10:00:00", "qe_Date": "30-SEP-2026",
             "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/latest.xml"},
            {"broadcast_Date": "13-Nov-2026 10:00:00", "qe_Date": "30-SEP-2026",
             "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/older.xml"},
        ]})
        self.assertTrue(result["url"].endswith("latest.xml"))
        self.assertEqual(result["sort_date"], "14-Nov-2026 10:00:00")
        self.assertEqual(research.filing_sort_key(result["row"]), research.dt.datetime(2026, 11, 14, 10, 0, 0))

    def test_integrated_filing_without_archive_url_is_unavailable(self):
        self.assertIsNone(research.latest_integrated_filing({"data": [
            {"broadcastDate": "14-Nov-2026", "xbrl": "http://nsearchives.nseindia.com/corporate/xbrl/file.xml"},
            {"broadcastDate": "14-Nov-2026", "xbrl": "https://evil.example/corporate/xbrl/file.xml"},
            {"broadcastDate": "15-Nov-2026", "attachmentFile": "https://nsearchives.nseindia.com/corporate/xbrl/attachment.xml"},
            {"broadcastDate": "15-Nov-2026", "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/attachment.pdf"},
        ]}))

    def test_fetch_json_reseeds_nse_session_after_forbidden_response(self):
        class Response:
            def __init__(self, status, payload=None):
                self.status_code = status
                self._payload = payload or {}
            def raise_for_status(self):
                if self.status_code >= 400:
                    raise RuntimeError(f"HTTP {self.status_code}")
            def json(self):
                return self._payload

        class Session:
            def __init__(self):
                self.headers = {}
                self.responses = [Response(403), Response(200), Response(200), Response(200, {"data": [1]})]
                self.calls = []
            def get(self, url, **kwargs):
                self.calls.append(url)
                return self.responses.pop(0)

        session = Session()
        old_sleep = research.time.sleep
        research.time.sleep = lambda _seconds: None
        try:
            result = research.fetch_json(session, "https://www.nseindia.com/api/example", {}, "https://www.nseindia.com/")
        finally:
            research.time.sleep = old_sleep
        self.assertEqual(result, {"data": [1]})
        self.assertIn("https://www.nseindia.com/market-data/live-equity-market", session.calls)
        self.assertEqual(len(session.calls), 4)

    def test_archive_html_challenge_is_not_passed_to_xbrl_parser(self):
        class Response:
            status_code = 200
            headers = {"Content-Type": "text/html"}
            content = b"<!doctype html><html><title>Access Denied</title></html>"
            def raise_for_status(self):
                return None

        class Session:
            def get(self, _url, **_kwargs):
                return Response()

        with self.assertRaisesRegex(ValueError, "HTML challenge"):
            research.fetch_archive_xml(Session(), "https://nsearchives.nseindia.com/corporate/xbrl/test.xml", "https://www.nseindia.com/")

    def test_official_bhavcopy_row_parses_eod_market_fields(self):
        result = research.parse_nse_bhavcopy_row({
            "CLOSE_PRICE": "125.00",
            "PREV_CLOSE": "100.00",
            "OPEN_PRICE": "101.00",
            "HIGH_PRICE": "128.00",
            "LOW_PRICE": "99.00",
            "LAST_PRICE": "124.50",
            "AVG_PRICE": "115.00",
            "TTL_TRD_QNTY": "250000",
            "TURNOVER_LACS": "28750.00",
            "NO_OF_TRADES": "1234",
            "DELIV_QTY": "90000",
            "DELIV_PER": "36.00",
        })
        self.assertEqual(result["price"], 125.0)
        self.assertEqual(result["change_pct"], 25.0)
        self.assertEqual(result["traded_quantity"], 250000.0)
        self.assertEqual(result["delivery_quantity"], 90000.0)
        self.assertEqual(result["delivery_pct"], 36.0)

    def test_bhavcopy_missing_fields_are_not_fabricated(self):
        result = research.parse_nse_bhavcopy_row({"CLOSE_PRICE": "100", "PREV_CLOSE": "0"})
        self.assertEqual(result, {"price": 100.0})

    def test_bhavcopy_fetch_selects_only_eq_rows_for_requested_symbols(self):
        class Response:
            status_code = 200
            content = (
                b"SYMBOL,SERIES,DATE1,PREV_CLOSE,OPEN_PRICE,HIGH_PRICE,LOW_PRICE,LAST_PRICE,CLOSE_PRICE,AVG_PRICE,TTL_TRD_QNTY,TURNOVER_LACS,NO_OF_TRADES,DELIV_QTY,DELIV_PER\n"
                b"ABC,EQ,13-Nov-2026,100,101,110,99,109,108,105,1000,10,20,400,40\n"
                b"ABC,BE,13-Nov-2026,100,101,110,99,109,108,105,1000,10,20,400,40\n"
                b"XYZ,EQ,13-Nov-2026,100,101,110,99,109,108,105,1000,10,20,400,40\n"
            )
        class Session:
            def get(self, _url, **_kwargs):
                return Response()
        result = research.fetch_latest_nse_bhavcopy(Session(), {"ABC"}, today=research.dt.date(2026, 11, 16))
        self.assertEqual(set(result), {"ABC"})
        self.assertEqual(result["ABC"]["market_data_as_of"], "2026-11-13")
        self.assertEqual(result["ABC"]["market_data_type"], "end_of_day")
        self.assertEqual(result["ABC"]["quote_source"], "NSE official full bhavcopy EOD archive")

    def test_invalid_numeric_fields_remain_missing(self):
        result = research.parse_company_quote({
            "info": {"companyName": "Example"},
            "priceInfo": {"lastPrice": "unknown", "pChange": None},
        })
        self.assertIsNone(result["price"])
        self.assertIsNone(result["change_pct"])
        self.assertIsNone(result["market_cap_cr"])


    def test_eod_fallback_fills_missing_quote_fields_without_overwriting_real_quote(self):
        eod = {
            "price": 125.0,
            "previous_close": 120.0,
            "market_data_as_of": "2026-11-13",
            "market_data_type": "end_of_day",
            "quote_source": "NSE official full bhavcopy EOD archive",
        }
        fallback = research.apply_eod_fallback(
            {"price": None, "company_name": None, "quote_source": "NSE India public quote-equity API"}, eod
        )
        self.assertEqual(fallback["price"], 125.0)
        self.assertEqual(fallback["previous_close"], 120.0)
        self.assertEqual(fallback["market_data_as_of"], "2026-11-13")
        self.assertEqual(fallback["market_data_type"], "end_of_day")
        self.assertEqual(fallback["price_as_of"], "2026-11-13")
        self.assertEqual(fallback["quote_source"], "NSE official full bhavcopy EOD archive")

        preferred = research.apply_eod_fallback({"price": 130.0, "quote_source": "NSE live quote"}, eod)
        self.assertEqual(preferred["price"], 130.0)
        self.assertEqual(preferred["quote_source"], "NSE live quote")
        self.assertEqual(preferred["market_data_as_of"], "2026-11-13")

    def test_safe_source_keeps_other_sources_available_after_one_failure(self):
        calls = []
        def broken():
            calls.append("broken")
            raise RuntimeError("HTTP 403")
        def healthy():
            calls.append("healthy")
            return {"rows": 3}
        self.assertIsNone(research.safe_source("broken endpoint", broken))
        self.assertEqual(research.safe_source("healthy endpoint", healthy), {"rows": 3})
        self.assertEqual(calls, ["broken", "healthy"])

    def test_verified_master_classification_fills_missing_industry_without_overwriting_quote(self):
        master = {
            "industry": "Capital Markets",
            "sector": "Financial Services",
            "macro_sector": "Financial Services",
            "status": "verified_nse_marketlens_industry_crosswalk",
            "verified_on": "2026-11-14",
            "source": "NSE MarketLens official screener",
            "source_url": "https://marketlens.nseindia.com/screener",
            "classification_reference_url": "https://example.com/classification.pdf",
        }
        result = research.apply_verified_master_classification({"industry": None, "nse_sector": "Existing NSE sector"}, master)
        self.assertEqual(result["industry"], "Capital Markets")
        self.assertEqual(result["sector"], "Financial Services")
        self.assertEqual(result["macro_sector"], "Financial Services")
        self.assertEqual(result["industry_as_of"], "2026-11-14")
        self.assertEqual(result["nse_sector"], "Existing NSE sector")

    def test_unverified_master_classification_is_not_published(self):
        result = research.apply_verified_master_classification(
            {"industry": None},
            {"industry": "Banks", "sector": "Financial Services", "status": "pending"},
        )
        self.assertIsNone(result["industry"])
        self.assertNotIn("sector", result)

    def test_extract_company_name_uses_explicit_nse_filing_name(self):
        self.assertEqual(
            research.extract_company_name(
                {},
                {"data": [{"issuerName": "Example Industries Limited"}]},
                [],
                {},
            ),
            "Example Industries Limited",
        )
        self.assertIsNone(research.extract_company_name({}, {}, [], {"industry": "Banks"}))

    def test_quote_failure_does_not_abort_independent_filing_pipeline(self):
        original_fetch_json = research.fetch_json
        original_sleep = research.time.sleep
        calls = []
        def fake_fetch_json(_session, _url, params, _referer):
            calls.append(params)
            if len(calls) == 1:
                raise RuntimeError("HTTP 403")
            return {}
        research.fetch_json = fake_fetch_json
        research.time.sleep = lambda _seconds: None
        try:
            quote, trade, error = research.fetch_quote_payloads(
                object(), "360ONE", "https://www.nseindia.com/get-quotes/equity?symbol=360ONE"
            )
        finally:
            research.fetch_json = original_fetch_json
            research.time.sleep = original_sleep
        self.assertEqual(quote, {})
        self.assertEqual(trade, {})
        self.assertIn("HTTP 403", error)
        self.assertEqual(len(calls), 1)


    def test_nse_stock_master_has_complete_verified_218_symbol_industry_sector_coverage(self):
        master_path = Path(__file__).resolve().parents[1] / "nse-fo-stock-sector-master.json"
        master = json.loads(master_path.read_text(encoding="utf-8"))
        stocks = master.get("stocks") or {}

        self.assertEqual(master.get("universe", {}).get("count"), 218)
        self.assertEqual(len(stocks), 218)
        self.assertTrue(all(row.get("industry") and row.get("sector") for row in stocks.values()))
        self.assertTrue(all(str(row.get("status", "")).startswith("verified_") for row in stocks.values()))

        # Seven legacy mappings have verified industry/sector but no separately
        # sourced macro-sector mapping; keep that field unavailable rather than infer it.
        missing_macro = {symbol for symbol, row in stocks.items() if not row.get("macro_sector")}
        self.assertEqual(
            missing_macro,
            {"ADANIPORTS", "COALINDIA", "EICHERMOT", "HDFCBANK", "HINDALCO", "RELIANCE", "SBIN"},
        )

if __name__ == "__main__":
    unittest.main()
