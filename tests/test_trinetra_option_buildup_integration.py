import unittest
from datetime import datetime, timezone
from unittest import mock

import fetch_and_score


class TrinetraOptionBuildupIntegrationTests(unittest.TestCase):
    def test_option_buildup_enters_only_its_own_index_test_score(self):
        now = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)
        instruments = {
            name: {"score": original, "headlines": []}
            for name, original in (
                ("NIFTY", 1.25),
                ("SENSEX", -2.50),
                ("BANKNIFTY", 3.75),
            )
        }
        option_scores = {"NIFTY": 4.0, "BANKNIFTY": -6.0}
        requested_assets = []

        def option_diagnostic(_archive, asset, **kwargs):
            requested_assets.append(asset)
            return {"asset": asset}

        def option_component(diagnostic, source_date, weight):
            score = option_scores[diagnostic["asset"]]
            return (
                fetch_and_score.build_component(
                    score,
                    "Synthetic NSE option build-up fixture",
                    source_date,
                    weight,
                    test_only=True,
                ),
                None,
            )

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
            mock.patch.object(fetch_and_score, "build_option_buildup_diagnostic", side_effect=option_diagnostic),
            mock.patch.object(fetch_and_score, "validate_option_buildup_diagnostic", side_effect=lambda value, **kwargs: value),
            mock.patch.object(fetch_and_score, "option_buildup_test_component", side_effect=option_component),
            mock.patch("builtins.open", side_effect=FileNotFoundError),
        ):
            fetch_and_score.build_asset_component_breakdowns(
                instruments,
                "2026-11-25T12:00:00Z",
                now,
                participant_today={},
                participant_changes_data={},
            )

        self.assertEqual(requested_assets, ["NIFTY", "BANKNIFTY"])
        nifty = instruments["NIFTY"]["component_breakdown"]
        banknifty = instruments["BANKNIFTY"]["component_breakdown"]
        sensex = instruments["SENSEX"]["component_breakdown"]

        self.assertEqual(nifty["experimental_combined_final"]["score"], 4.0)
        self.assertEqual(banknifty["experimental_combined_final"]["score"], -6.0)
        self.assertIsNone(sensex["experimental_combined_final"])
        self.assertNotIn("option_buildup", sensex["experimental_combined_components"])
        self.assertEqual(nifty["experimental_combined_components"]["option_buildup"]["score"], 4.0)
        self.assertEqual(banknifty["experimental_combined_components"]["option_buildup"]["score"], -6.0)

        # The published PDMP score must remain untouched by the TEST component.
        self.assertEqual(instruments["NIFTY"]["score"], 1.25)
        self.assertEqual(instruments["SENSEX"]["score"], -2.50)
        self.assertEqual(instruments["BANKNIFTY"]["score"], 3.75)


if __name__ == "__main__":
    unittest.main()
