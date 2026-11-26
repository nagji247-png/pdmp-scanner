"""End-to-end TRINETRA TEST wiring using real NSE option-build-up logic.

Synthetic contract rows exercise the production diagnostic/validation/scoring
functions without network access. This is not a claim that archived live data
was loaded or that the live dashboard scan was executed.
"""
import io
import json
import unittest
from datetime import datetime, timezone
from unittest import mock

import fetch_and_score


def _archive_for(symbol, side, premium_delta, oi_delta):
    contracts_previous = []
    contracts_current = []
    for index in range(120):
        strike = 20000.0 + index * 50
        common = {
            "expiry": "2026-12-31",
            "side": side,
            "strike": strike,
        }
        contracts_previous.append({
            **common, "close": 100.0, "open_interest": 1000,
        })
        contracts_current.append({
            **common,
            "close": 100.0 + premium_delta,
            "open_interest": 1000 + oi_delta,
        })
    return [
        {
            "date": "2026-11-23",
            "option_contracts": {symbol: {"contracts": contracts_previous}},
        },
        {
            "date": "2026-11-25",
            "option_contracts": {symbol: {"contracts": contracts_current}},
        },
    ]


class TrinetraOptionBuildupArchiveIntegrationTests(unittest.TestCase):
    def test_real_diagnostic_and_component_enter_only_matching_test_score(self):
        archive = {
            "records": (
                _archive_for("NIFTY", "CE", 10.0, 100)
                + _archive_for("BANKNIFTY", "PE", 10.0, 100)
            )
        }
        archive_text = json.dumps(archive)

        def archive_open(path, *args, **kwargs):
            if str(path) == "nse_index_option_oi.json":
                return io.StringIO(archive_text)
            raise FileNotFoundError(path)

        instruments = {
            name: {"score": original_score, "headlines": []}
            for name, original_score in (
                ("NIFTY", 1.25),
                ("SENSEX", -2.50),
                ("BANKNIFTY", 3.75),
            )
        }
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
            mock.patch("builtins.open", side_effect=archive_open),
        ):
            fetch_and_score.build_asset_component_breakdowns(
                instruments,
                "2026-11-25T12:00:00Z",
                now,
                participant_today={},
                participant_changes_data={},
            )

        nifty = instruments["NIFTY"]["component_breakdown"]
        banknifty = instruments["BANKNIFTY"]["component_breakdown"]
        sensex = instruments["SENSEX"]["component_breakdown"]

        self.assertEqual(nifty["experimental_combined_final"]["status"], "available")
        self.assertAlmostEqual(nifty["experimental_combined_final"]["score"], 10.0)
        self.assertEqual(banknifty["experimental_combined_final"]["status"], "available")
        self.assertAlmostEqual(banknifty["experimental_combined_final"]["score"], -10.0)
        self.assertIn("option_buildup", nifty["experimental_combined_components"])
        self.assertIn("option_buildup", banknifty["experimental_combined_components"])
        self.assertNotIn("option_buildup", sensex["experimental_combined_components"])
        self.assertEqual(sensex["experimental_combined_final"]["status"], "unavailable")

        # Experimental option data must never overwrite published PDMP scores.
        self.assertEqual(instruments["NIFTY"]["score"], 1.25)
        self.assertEqual(instruments["SENSEX"]["score"], -2.50)
        self.assertEqual(instruments["BANKNIFTY"]["score"], 3.75)


if __name__ == "__main__":
    unittest.main()
