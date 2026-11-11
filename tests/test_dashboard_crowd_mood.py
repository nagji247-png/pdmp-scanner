import json
import shutil
import subprocess
import unittest


class DashboardThreeWayCrowdMoodTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("node"):
            raise unittest.SkipTest("Node.js is required to execute dashboard mood logic")
        script = r"""
const fs = require("fs");
const html = fs.readFileSync("dashboard.html", "utf8");
const start = html.indexOf("function classifyThreeWayCrowdMood(t) {");
const end = html.indexOf("\n}\n\nfunction renderCrowd", start) + 2;
if (start < 0 || end < 2) throw new Error("three-way mood helper not found");
eval(html.slice(start, end));
const result = {
  neutral: classifyThreeWayCrowdMood({ bull_score_pct: 1.4, bear_score_pct: 0.4, neutral_score_pct: 98.1 }),
  bullish: classifyThreeWayCrowdMood({ bull_score_pct: 80, bear_score_pct: 10, neutral_score_pct: 10 }),
  bearish: classifyThreeWayCrowdMood({ bull_score_pct: 10, bear_score_pct: 80, neutral_score_pct: 10 }),
  balanced: classifyThreeWayCrowdMood({ bull_score_pct: 40, bear_score_pct: 35, neutral_score_pct: 25 }),
  invalid: classifyThreeWayCrowdMood({ bull_score_pct: 80, bear_score_pct: 10, neutral_score_pct: 30 })
};
console.log(JSON.stringify(result));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            check=True,
            capture_output=True,
            text=True,
        )
        cls.results = json.loads(completed.stdout.strip())

    def test_neutral_dominance_overrides_directional_only_bull_ratio(self):
        result = self.results["neutral"]
        self.assertEqual(result["state"], "NEUTRAL")
        self.assertFalse(result["extreme"])

    def test_extreme_bullish_and_bearish_need_70_percent_three_way_share(self):
        self.assertEqual(self.results["bullish"]["state"], "EXTREMELY BULLISH")
        self.assertTrue(self.results["bullish"]["extreme"])
        self.assertEqual(self.results["bearish"]["state"], "EXTREMELY BEARISH")
        self.assertTrue(self.results["bearish"]["extreme"])

    def test_non_extreme_direction_is_not_a_trap_trigger(self):
        result = self.results["balanced"]
        self.assertEqual(result["state"], "BULLISH")
        self.assertFalse(result["extreme"])

    def test_invalid_percentages_fail_closed(self):
        self.assertIsNone(self.results["invalid"])


if __name__ == "__main__":
    unittest.main()
