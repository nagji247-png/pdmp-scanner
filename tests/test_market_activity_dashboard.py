import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class MarketActivityDashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dashboard = (ROOT / "dashboard.html").read_text(encoding="utf-8")
        cls.script = (ROOT / "market-activity.js").read_text(encoding="utf-8")
        cls.master = json.loads((ROOT / "nse-fo-stock-sector-master.json").read_text(encoding="utf-8"))

    def test_verified_fno_master_is_218_stocks_across_18_sectors(self):
        stocks = self.master["stocks"]
        self.assertEqual(len(stocks), 218)
        self.assertEqual(len({row["sector"] for row in stocks.values()}), 18)

    def test_activity_anchor_and_section_are_between_fpi_and_stock_list(self):
        self.assertIn('href="#market-activity"', self.dashboard)
        self.assertIn('id="market-activity"', self.dashboard)
        self.assertIn('src="market-activity.js?v=1"', self.dashboard)
        fpi = self.dashboard.index('id="fpi-sector-tilt"')
        activity = self.dashboard.index('id="market-activity-panel"')
        stocks = self.dashboard.index('<section class="panel stocks-panel">')
        self.assertLess(fpi, activity)
        self.assertLess(activity, stocks)

    def test_activity_uses_existing_static_data_and_shows_missing_values_honestly(self):
        self.assertIn("nse-fo-stock-sector-master.json", self.script)
        self.assertIn("fpi-sector-data.json", self.script)
        self.assertIn('fetch("data.json?', self.script)
        self.assertIn("डेटा उपलब्ध नहीं", self.script)
        self.assertIn("व्यक्तिगत स्टॉक FPI डेटा उपलब्ध नहीं", self.script)

    def test_existing_dashboard_safety_and_refresh_hooks_remain(self):
        self.assertIn("function updateTradeGuard(data)", self.dashboard)
        self.assertIn("const REFRESH_MS = 5 * 60 * 1000", self.dashboard)
        self.assertIn("NO TRADE", self.dashboard)


if __name__ == "__main__":
    unittest.main()
