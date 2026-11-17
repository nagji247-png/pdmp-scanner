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


    def test_expanded_hindi_and_colloquial_direction_words_are_classified(self):
        bullish = [
            "निफ्टी में मजबूती", "निफ्टी उछलेगा", "निफ्टी चढ़ रहा है",
            "निफ्टी में तेज उछाल", "निफ्टी भागेगा",
        ]
        bearish = [
            "निफ्टी धड़ाम", "निफ्टी लुढ़क गया", "निफ्टी फिसल रहा है",
            "निफ्टी टूट गया", "निफ्टी में बिकवाली का दबाव",
        ]
        neutral = [
            "निफ्टी स्थिरता", "निफ्टी सीमित दायरे में",
            "निफ्टी दायरेबंद", "निफ्टी रेंज में",
        ]
        for term in bullish:
            with self.subTest(term=term):
                self.assertEqual(fetch_and_score._asset_search_direction(term, "NIFTY"), "bull")
        for term in bearish:
            with self.subTest(term=term):
                self.assertEqual(fetch_and_score._asset_search_direction(term, "NIFTY"), "bear")
        for term in neutral:
            with self.subTest(term=term):
                self.assertEqual(fetch_and_score._asset_search_direction(term, "NIFTY"), "neutral")

    def test_expanded_terms_remain_asset_scoped(self):
        self.assertIsNone(fetch_and_score._asset_search_direction("निफ्टी में मजबूती", "SENSEX"))
        self.assertIsNone(fetch_and_score._asset_search_direction("सोना धड़ाम", "SILVER"))

    def test_other_assets_and_bare_asset_names_do_not_become_neutral(self):
        self.assertIsNone(fetch_and_score._asset_search_direction("sensex live", "NIFTY"))
        self.assertIsNone(fetch_and_score._asset_search_direction("gold silver price today", "GOLD"))
        self.assertIsNone(fetch_and_score._asset_search_direction("nifty", "NIFTY"))


if __name__ == "__main__":
    unittest.main()
