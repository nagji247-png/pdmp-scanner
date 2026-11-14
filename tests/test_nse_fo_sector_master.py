import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MASTER_PATH = ROOT / "nse-fo-stock-sector-master.json"
WATCHLIST_MAP_PATH = ROOT / "fpi-stock-sector-map.json"


class NseFoSectorMasterTests(unittest.TestCase):
    def setUp(self):
        self.master = json.loads(MASTER_PATH.read_text(encoding="utf-8"))
        self.watchlist = json.loads(WATCHLIST_MAP_PATH.read_text(encoding="utf-8"))

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
        for symbol, mapping in self.watchlist["stocks"].items():
            self.assertIn(symbol, self.master["stocks"])
            record = self.master["stocks"][symbol]
            self.assertEqual(record["sector"], mapping["sector"])
            self.assertEqual(record["industry"], mapping["industry"])
            self.assertEqual(record["status"], "verified_existing_mapping")

    def test_unverified_symbols_fail_closed(self):
        for symbol, record in self.master["stocks"].items():
            self.assertIn(
                record["status"],
                {"verified_existing_mapping", "verified_nse_marketlens_sector_match", "pending_official_company_classification"},
                msg=symbol,
            )
            if record["status"] == "pending_official_company_classification":
                self.assertIsNone(record["sector"], msg=symbol)
                self.assertIsNone(record["industry"], msg=symbol)

    def test_marketlens_verified_rows_use_exact_fpi_sector_labels(self):
        allowed_sectors = {
            "Financial Services", "Information Technology", "Fast Moving Consumer Goods",
            "Healthcare", "Telecommunication", "Utilities", "Services",
        }
        for symbol, record in self.master["stocks"].items():
            if record["status"] == "verified_nse_marketlens_sector_match":
                self.assertIn(record["sector"], allowed_sectors, msg=symbol)
                self.assertIn("marketlens.nseindia.com", record["source_url"])
                self.assertIsNotNone(record["industry"])

    def test_classification_counts_reconcile(self):
        verified = sum(1 for x in self.master["stocks"].values() if x["status"] != "pending_official_company_classification")
        pending = sum(1 for x in self.master["stocks"].values() if x["status"] == "pending_official_company_classification")
        self.assertEqual(self.master["classification"]["verified_count"], verified)
        self.assertEqual(self.master["classification"]["pending_count"], pending)
        self.assertEqual(verified + pending, 218)

    def test_only_stock_underlyings_are_included(self):
        index_symbols = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50", "NIFTYFPI"}
        self.assertTrue(index_symbols.isdisjoint(self.master["stocks"]))


if __name__ == "__main__":
    unittest.main()
