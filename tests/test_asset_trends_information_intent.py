import unittest

import fetch_and_score


class AssetTrendsInformationIntentTests(unittest.TestCase):
    def test_asset_matched_information_queries_are_not_sentiment(self):
        cases = [
            ("nifty today", "NIFTY"),
            ("nifty live price chart", "NIFTY"),
            ("sensex live today", "SENSEX"),
            ("bank nifty option chain", "BANKNIFTY"),
            ("gold price today", "GOLD"),
            ("silver rate today", "SILVER"),
        ]
        for term, asset in cases:
            with self.subTest(term=term, asset=asset):
                self.assertEqual(
                    fetch_and_score._asset_search_direction(term, asset),
                    "informational",
                )

    def test_directional_terms_take_precedence_over_information_intent(self):
        self.assertEqual(fetch_and_score._asset_search_direction("nifty today breakout", "NIFTY"), "bull")
        self.assertEqual(fetch_and_score._asset_search_direction("sensex live crash", "SENSEX"), "bear")

    def test_mixed_or_negated_direction_is_not_relabelled_neutral(self):
        self.assertIsNone(fetch_and_score._asset_search_direction("nifty rally crash", "NIFTY"))
        self.assertIsNone(fetch_and_score._asset_search_direction("nifty not bullish", "NIFTY"))

    def test_other_assets_and_bare_asset_names_do_not_become_neutral(self):
        self.assertIsNone(fetch_and_score._asset_search_direction("sensex live", "NIFTY"))
        self.assertIsNone(fetch_and_score._asset_search_direction("gold silver price today", "GOLD"))
        self.assertIsNone(fetch_and_score._asset_search_direction("nifty", "NIFTY"))


if __name__ == "__main__":
    unittest.main()
