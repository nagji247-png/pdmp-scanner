import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MASTER_PATH = ROOT / "nse-fo-stock-sector-master.json"
WATCHLIST_MAP_PATH = ROOT / "fpi-stock-sector-map.json"
FPI_DATA_PATH = ROOT / "fpi-sector-data.json"


class NseFoSectorMasterTests(unittest.TestCase):
    def setUp(self):
        self.master = json.loads(MASTER_PATH.read_text(encoding="utf-8"))
        self.watchlist = json.loads(WATCHLIST_MAP_PATH.read_text(encoding="utf-8"))
        self.allowed_fpi_sectors = {
            item["name"]
            for item in json.loads(FPI_DATA_PATH.read_text(encoding="utf-8"))["history"][0]["sectors"]
        }

    def test_official_nse_fo_universe_count_and_uniqueness(self):
        stocks = self.master["stocks"]
        universe = self.master["universe"]
        self.assertEqual(universe["count"], 218)
        self.assertEqual(len(stocks), 218)
        self.assertEqual(len(stocks), len(set(stocks)))
        self.assertEqual(
            universe["verification_status"],
            "reconciled_to_official_nse_underlyings_page",
        )
        self.assertEqual(
            universe["source"],
            "NSE List of Underlyings and Information · Derivatives on Individual Securities",
        )
        self.assertEqual(universe["updated_on"], "2026-11-11")
        self.assertIn("nseindia.com", universe["source_url"])

    def test_existing_watchlist_mappings_are_preserved(self):
        original_watchlist_symbols = {
            "RELIANCE", "HDFCBANK", "HINDALCO", "ADANIPORTS",
            "COALINDIA", "EICHERMOT", "SBIN",
        }
        for symbol, mapping in self.watchlist["stocks"].items():
            self.assertIn(symbol, self.master["stocks"])
            record = self.master["stocks"][symbol]
            self.assertEqual(record["sector"], mapping["sector"])
            self.assertEqual(record["industry"], mapping["industry"])
            expected_status = (
                "verified_existing_mapping"
                if symbol in original_watchlist_symbols
                else "verified_nse_marketlens_industry_crosswalk"
            )
            self.assertEqual(record["status"], expected_status)

    def test_unverified_symbols_fail_closed(self):
        allowed_statuses = {
            "verified_existing_mapping",
            "verified_nse_marketlens_industry_crosswalk",
            "pending_official_company_classification",
        }
        for symbol, record in self.master["stocks"].items():
            self.assertIn(record["status"], allowed_statuses, msg=symbol)
            if record["status"] == "pending_official_company_classification":
                self.assertIsNone(record["sector"], msg=symbol)
                self.assertIsNone(record["industry"], msg=symbol)

    def test_marketlens_verified_rows_use_exact_fpi_sector_labels_and_macro_check(self):
        for symbol, record in self.master["stocks"].items():
            if record["status"] == "verified_nse_marketlens_industry_crosswalk":
                self.assertIn(record["sector"], self.allowed_fpi_sectors, msg=symbol)
                self.assertIn("marketlens.nseindia.com", record["source_url"])
                self.assertIn("niftyindices.com", record["classification_reference_url"])
                self.assertIsNotNone(record["industry"])
                self.assertIn(record["macro_sector"], {
                    "Commodities", "Consumer Discretionary", "Energy",
                    "Fast Moving Consumer Goods", "Financial Services",
                    "Healthcare", "Industrials", "Information Technology",
                    "Services", "Telecommunication", "Utilities",
                })

    def test_classification_counts_reconcile(self):
        verified = sum(1 for x in self.master["stocks"].values() if x["status"] != "pending_official_company_classification")
        pending = sum(1 for x in self.master["stocks"].values() if x["status"] == "pending_official_company_classification")
        self.assertEqual(self.master["classification"]["verified_count"], verified)
        self.assertEqual(self.master["classification"]["pending_count"], pending)
        self.assertEqual(verified + pending, 218)

    def test_future_effective_symbols_are_not_included_early(self):
        # NSE circular dated 06-Nov-2026 makes these contracts effective
        # only from 25-Nov-2026; the 11-Nov underlying snapshot must exclude them.
        future_effective_symbols = {"ACUTAAS", "APARINDS"}
        self.assertTrue(future_effective_symbols.isdisjoint(self.master["stocks"]))

    def test_tata_motors_current_underlying_uses_tmpv(self):
        # The demerged Tata Motors F&O underlying is TMPV, not the retired ticker.
        self.assertIn("TMPV", self.master["stocks"])
        self.assertNotIn("TATAMOTORS", self.master["stocks"])

    def test_fpi_sector_taxonomy_provenance_is_explicit(self):
        classification = self.master["classification"]
        self.assertIn("NSDL", classification["fpi_reference_source"])
        self.assertIn("BSE", classification["fpi_reference_source"])
        self.assertIn("nsdl.co.in", classification["fpi_reference_source_url"])
        self.assertIn("bseindia.com", classification["common_structure_source_url"])
        self.assertIn("not represented as independently audited BSE", classification["note"])

    def test_only_stock_underlyings_are_included(self):
        index_symbols = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50", "NIFTYFPI"}
        self.assertTrue(index_symbols.isdisjoint(self.master["stocks"]))


if __name__ == "__main__":
    unittest.main()
