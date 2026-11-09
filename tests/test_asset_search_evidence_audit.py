import unittest
from datetime import datetime, timezone

from component_score_consolidated_verify import summarize_asset_search


class PerAssetSearchEvidenceAuditTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 9, 5, 0, tzinfo=timezone.utc)

    def test_five_assets_require_their_own_seed_and_keep_neutral_only_unscored(self):
        cases = [
            ("NIFTY", "index_search_shadow", "nifty"),
            ("SENSEX", "index_search_shadow", "sensex"),
            ("BANKNIFTY", "index_search_shadow", "bank nifty"),
            ("GOLD", "asset_search_shadow", "gold price"),
            ("SILVER", "asset_search_shadow", "silver price"),
        ]
        for asset, field, seed in cases:
            with self.subTest(asset=asset):
                instrument = {field: {
                    "valid": True, "seed": seed, "source": "Google Trends related_queries",
                    "timeframe": "now 1-d", "source_data_time": "2026-11-09T04:00:00Z",
                    "bull_pct": 0, "bear_pct": 0, "neutral_pct": 100,
                    "directional_bull_pct": None, "classification_coverage_pct": 40,
                    "classified_queries": 8, "raw_queries": 20,
                }}
                result = summarize_asset_search(asset, instrument, self.now)
                self.assertEqual(result["status"], "NEUTRAL_ONLY")
                self.assertEqual(result["actual_seed"], seed)
                self.assertEqual(result["neutral_pct"], 100)
                self.assertFalse(result["status"] == "DIRECTIONAL_EVIDENCE_PRESENT")

    def test_cross_asset_seed_is_rejected(self):
        result = summarize_asset_search("SENSEX", {
            "index_search_shadow": {
                "valid": True, "seed": "nifty", "timeframe": "now 1-d",
                "source_data_time": "2026-11-09T04:00:00Z",
                "bull_pct": 50, "bear_pct": 50, "neutral_pct": 0,
                "directional_bull_pct": 50,
            }
        }, self.now)
        self.assertEqual(result["status"], "SEED_MISMATCH")

    def test_stale_snapshot_is_rejected(self):
        result = summarize_asset_search("GOLD", {
            "asset_search_shadow": {
                "valid": True, "seed": "gold price", "timeframe": "now 1-d",
                "source_data_time": "2026-11-08T20:00:00Z",
                "bull_pct": 60, "bear_pct": 40, "neutral_pct": 0,
                "directional_bull_pct": 60,
            }
        }, self.now)
        self.assertEqual(result["status"], "STALE_OR_INVALID_TIMESTAMP")


if __name__ == "__main__":
    unittest.main()
