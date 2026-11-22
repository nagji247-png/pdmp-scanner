import unittest

from nifty_premium_radar import build_previous_session_levels


class NiftyPremiumRadarLevelTests(unittest.TestCase):
    def test_builds_classic_pivot_support_and_resistance(self):
        levels = build_previous_session_levels(26000, 25800, 25950, 25950)
        self.assertEqual(len(levels), 7)
        by_label = {item["label"]: item["level"] for item in levels}
        pivot = (26000 + 25800 + 25950) / 3
        self.assertAlmostEqual(by_label["Pivot"], round(pivot, 2))
        self.assertAlmostEqual(by_label["R1"], round(2 * pivot - 25800, 2))
        self.assertAlmostEqual(by_label["S1"], round(2 * pivot - 26000, 2))
        self.assertEqual(by_label["पिछला High"], 26000)
        self.assertEqual(by_label["पिछला Low"], 25800)
        self.assertTrue(all(item["source"].startswith("पिछले पूरे NSE सत्र") for item in levels))

    def test_invalid_or_missing_ohlc_returns_no_levels(self):
        self.assertEqual(build_previous_session_levels(None, 25800, 25900), [])
        self.assertEqual(build_previous_session_levels(25800, 26000, 25900), [])
        self.assertEqual(build_previous_session_levels(26000, 25800, 27000), [])
        self.assertEqual(build_previous_session_levels(float("nan"), 25800, 25900), [])

    def test_levels_are_sorted_high_to_low_and_have_distance(self):
        levels = build_previous_session_levels(26000, 25800, 25900, 25950)
        values = [item["level"] for item in levels]
        self.assertEqual(values, sorted(values, reverse=True))
        self.assertTrue(all("dist_pct" in item for item in levels))


if __name__ == "__main__":
    unittest.main()
