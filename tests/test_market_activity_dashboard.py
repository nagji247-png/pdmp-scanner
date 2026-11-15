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
        self.assertEqual(len(self.master["stocks"]), 218)
        self.assertEqual(len({row["sector"] for row in self.master["stocks"].values()}), 18)

    def test_activity_panel_remains_between_fpi_and_stock_list(self):
        self.assertIn('href="#market-activity"', self.dashboard)
        self.assertIn('id="market-activity"', self.dashboard)
        self.assertIn('src="market-activity.js?v=1"', self.dashboard)
        self.assertLess(self.dashboard.index('id="fpi-sector-tilt"'),
                        self.dashboard.index('id="market-activity-panel"'))
        self.assertLess(self.dashboard.index('id="market-activity-panel"'),
                        self.dashboard.index('<section class="panel stocks-panel">'))

    def test_radar_has_requested_interactive_sections(self):
        for text in ("MARKET ACTIVITY RADAR", "LATEST ACTIVITY ALERTS",
                     "SECTOR ACTIVITY", "FPI FLOW + NEWS CONFIRMATION",
                     "218 STOCK MASTER LIST", "ma-stock-", "data-stock",
                     "ma-sector-grid", "स्टॉक-स्तरीय खबर उपलब्ध नहीं"):
            self.assertIn(text, self.script)

    def test_uses_existing_static_data_and_does_not_invent_missing_fields(self):
        for text in ("nse-fo-stock-sector-master.json", "fpi-sector-data.json",
                     'fetch("data.json?', "वॉल्यूम: डेटा उपलब्ध नहीं",
                     "भीड़ का रुख: डेटा उपलब्ध नहीं", "व्यक्तिगत स्टॉक FPI उपलब्ध नहीं"):
            self.assertIn(text, self.script)

    def test_existing_dashboard_safety_and_refresh_hooks_remain(self):
        self.assertIn("function updateTradeGuard(data)", self.dashboard)
        self.assertIn("const REFRESH_MS = 5 * 60 * 1000", self.dashboard)
        self.assertIn("NO TRADE", self.dashboard)


if __name__ == "__main__":
    unittest.main()
