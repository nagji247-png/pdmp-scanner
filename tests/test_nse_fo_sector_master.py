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

    def test_candidate_symbol_set_is_unique_and_explicitly_unreconciled(self):
        stocks = self.master["stocks"]
        self.assertEqual(self.master["universe"]["candidate_count"], len(stocks))
        self.assertEqual(len(stocks), len(set(stocks)))
        self.assertEqual(
            self.master["universe"]["verification_status"],
            "provisional_unreconciled",
        )
        self.assertIn("not yet reconciled", self.master["universe"]["source"])

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
                {"verified_existing_mapping", "pending_official_company_classification"},
                msg=symbol,
            )
            if record["status"] == "pending_official_company_classification":
                self.assertIsNone(record["sector"], msg=symbol)
                self.assertIsNone(record["industry"], msg=symbol)

    def test_only_stock_underlyings_are_included(self):
        index_symbols = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50", "NIFTYFPI"}
        self.assertTrue(index_symbols.isdisjoint(self.master["stocks"]))


if __name__ == "__main__":
    unittest.main()
