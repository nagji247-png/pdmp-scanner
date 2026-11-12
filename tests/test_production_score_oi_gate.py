import unittest

from fetch_and_score import retail_adjust, validated_news_crowd_score


class ProductionScoreOIGateTests(unittest.TestCase):
    def test_client_oi_is_preserved_as_diagnostic_but_not_a_score_input(self):
        bullish_oi = {
            "ok": True,
            "date": "2026-11-11",
            "participants": {
                "CLIENT": {
                    "index_call_long": 70,
                    "index_call_short": 30,
                    "index_put_long": 30,
                    "index_put_short": 70,
                }
            },
        }
        bearish_oi = {
            "ok": True,
            "date": "2026-11-11",
            "participants": {
                "CLIENT": {
                    "index_call_long": 30,
                    "index_call_short": 70,
                    "index_put_long": 70,
                    "index_put_short": 30,
                }
            },
        }

        bullish_adjustment, bullish_diagnostic = retail_adjust(bullish_oi)
        bearish_adjustment, bearish_diagnostic = retail_adjust(bearish_oi)
        self.assertEqual(bullish_adjustment, 2.0)
        self.assertEqual(bearish_adjustment, -2.0)
        self.assertIsNotNone(bullish_diagnostic)
        self.assertIsNotNone(bearish_diagnostic)

        bullish_score = validated_news_crowd_score(6.0, 2.0, True)
        bearish_score = validated_news_crowd_score(6.0, 2.0, True)
        self.assertEqual(bullish_score, (4.0, "news_crowd", {"news": 50.0, "crowd": 50.0}))
        self.assertEqual(bearish_score, bullish_score)

    def test_missing_or_invalid_crowd_renormalizes_to_news_only(self):
        score, mode, weights = validated_news_crowd_score(6.0, 2.0, False)
        self.assertEqual(score, 6.0)
        self.assertEqual(mode, "news_only")
        self.assertEqual(weights, {"news": 100.0})

    def test_score_is_clamped_to_the_documented_range(self):
        score, mode, weights = validated_news_crowd_score(12.0, 12.0, True)
        self.assertEqual(score, 10.0)
        self.assertEqual(mode, "news_crowd")
        self.assertEqual(weights, {"news": 50.0, "crowd": 50.0})


if __name__ == "__main__":
    unittest.main()
