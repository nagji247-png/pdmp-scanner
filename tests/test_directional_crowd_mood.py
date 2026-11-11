import unittest

import fetch_and_score


class DirectionalCrowdMoodTests(unittest.TestCase):
    def test_directional_bias_is_not_overridden_by_information_searches(self):
        mood, _ = fetch_and_score.three_way_crowd_mood(1.4, 0.4, 98.2)
        self.assertEqual(mood, "BULLISH")
        self.assertAlmostEqual(
            fetch_and_score.three_way_crowd_component(1.4, 0.4, 98.2),
            5.6,
            places=1,
        )

    def test_neutral_only_queries_remain_neutral_without_a_directional_score(self):
        mood, _ = fetch_and_score.three_way_crowd_mood(0, 0, 100)
        self.assertEqual(mood, "NEUTRAL")
        self.assertIsNone(fetch_and_score.three_way_crowd_component(0, 0, 100))

    def test_weak_directional_interest_is_not_enough_to_set_mood(self):
        mood, _ = fetch_and_score.three_way_crowd_mood(0.4, 0.3, 99.3)
        self.assertEqual(mood, "NEUTRAL")
        self.assertIsNone(fetch_and_score.three_way_crowd_component(0.4, 0.3, 99.3))

    def test_balanced_directional_queries_are_neutral(self):
        mood, _ = fetch_and_score.three_way_crowd_mood(35, 35, 30)
        self.assertEqual(mood, "NEUTRAL")
        self.assertEqual(fetch_and_score.three_way_crowd_component(35, 35, 30), 0.0)

    def test_invalid_percentages_fail_closed(self):
        mood, _ = fetch_and_score.three_way_crowd_mood(80, 10, 30)
        self.assertEqual(mood, "NO DATA")
        self.assertIsNone(fetch_and_score.three_way_crowd_component(80, 10, 30))


if __name__ == "__main__":
    unittest.main()
