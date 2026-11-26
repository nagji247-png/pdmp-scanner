"""Real committed NSE archive integration through the production TRINETRA TEST path.

Unlike the synthetic fixture test, this reads nse_index_option_oi.json from the
checked-out PR branch and calls build_asset_component_breakdowns. No network
requests are made; unrelated inputs are stubbed as unavailable.
"""
import json
import unittest
from pathlib import Path
from datetime import datetime, timezone
from unittest import mock

import fetch_and_score


class TrinetraRealNseArchiveIntegrationTests(unittest.TestCase):
    def test_committed_archive_flows_into_index_specific_test_score_only(self):
        archive_path = Path("nse_index_option_oi.json")
        self.assertTrue(archive_path.is_file(), "real NSE archive must be present in CI checkout")
        archive = json.loads(archive_path.read_text(encoding="utf-8"))
        records = archive.get("records") or []
        self.assertGreaterEqual(len(records), 2)
        self.assertEqual(records[-1].get("date"), "2026-11-25")
        for symbol in ("NIFTY", "BANKNIFTY"):
            contracts = (records[-1].get("option_contracts") or {}).get(symbol, {}).get("contracts")
            self.assertTrue(contracts, f"real contract-level archive missing for {symbol}")

        instruments = {
            name: {"score": published_score, "headlines": []}
            for name, published_score in (
                ("NIFTY", 1.25),
                ("SENSEX", -2.50),
                ("BANKNIFTY", 3.75),
            )
        }
        expected_option_scores = {"NIFTY": 8.4088, "BANKNIFTY": 9.9773}
        now = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)

        with (
            mock.patch.object(fetch_and_score, "experimental_news_scores", return_value={}),
            mock.patch.object(fetch_and_score, "load_exchange_calendar", return_value={"calendar_year": 2026}),
            mock.patch.object(fetch_and_score, "expected_latest_completed_session", return_value="2026-11-25"),
            mock.patch.object(fetch_and_score, "load_latest_stock_basket_diagnostics", return_value={}),
            mock.patch.object(fetch_and_score, "load_client_futures_promotion", return_value={}),
            mock.patch.object(fetch_and_score, "client_oi_context", return_value=None),
            mock.patch.object(fetch_and_score, "client_marketwide_components", return_value={}),
            mock.patch.object(fetch_and_score, "index_oi_balance_component", return_value=None),
            mock.patch.object(fetch_and_score, "build_client_futures_component", return_value=None),
        ):
            fetch_and_score.build_asset_component_breakdowns(
                instruments,
                "2026-11-25T12:00:00Z",
                now,
                participant_today={},
                participant_changes_data={},
            )

        for symbol in ("NIFTY", "BANKNIFTY"):
            breakdown = instruments[symbol]["component_breakdown"]
            option = breakdown["experimental_combined_components"].get("option_buildup")
            combined = breakdown["experimental_combined_final"]
            self.assertIsNotNone(option, f"{symbol} real archive component was not included")
            self.assertTrue(option.get("test_only"))
            self.assertEqual(option.get("source_date"), "2026-11-25")
            self.assertEqual(combined.get("status"), "available")
            self.assertAlmostEqual(option.get("score"), expected_option_scores[symbol], places=4)
            # combine_components intentionally rounds the weighted result to 2 decimals.
            self.assertEqual(combined.get("score"), round(expected_option_scores[symbol], 2))
            self.assertIn("option_buildup", combined.get("included_components", []))
            self.assertFalse(breakdown["provisional_final"].get("status") == "available")
            self.assertNotIn("option_buildup", breakdown["provisional_components"])

        sensex = instruments["SENSEX"]["component_breakdown"]
        self.assertNotIn("option_buildup", sensex["experimental_combined_components"])
        self.assertEqual(sensex["experimental_combined_final"].get("status"), "unavailable")

        # The published PDMP scores must remain exactly as supplied.
        self.assertEqual(instruments["NIFTY"]["score"], 1.25)
        self.assertEqual(instruments["SENSEX"]["score"], -2.50)
        self.assertEqual(instruments["BANKNIFTY"]["score"], 3.75)


if __name__ == "__main__":
    unittest.main()
