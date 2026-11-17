import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class MarketActivityDashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dashboard = (ROOT / "dashboard.html").read_text(encoding="utf-8")
        cls.market_activity = (ROOT / "market-activity.js").read_text(encoding="utf-8")
        cls.fpi_script = (ROOT / "fpi-sector-tilt.js").read_text(encoding="utf-8")
        cls.master = json.loads((ROOT / "nse-fo-stock-sector-master.json").read_text(encoding="utf-8"))
        cls.drawings = json.loads((ROOT / "stock-chart-drawings.json").read_text(encoding="utf-8"))

    def test_verified_fno_master_is_218_stocks_across_18_sectors(self):
        self.assertEqual(len(self.master["stocks"]), 218)
        self.assertEqual(len({row["sector"] for row in self.master["stocks"].values()}), 18)
        self.assertEqual(self.drawings["snapshots"], {})
        self.assertNotIn("chart_layout_id", self.drawings)

    def test_market_activity_remains_separate_and_pre_fpi_drilldown(self):
        self.assertIn('id="market-activity"', self.dashboard)
        self.assertIn('src="market-activity.js?v=13"', self.dashboard)
        self.assertIn('id="fpi-sector-tilt"', self.dashboard)
        self.assertLess(self.dashboard.index('id="fpi-sector-tilt"'),
                        self.dashboard.index('id="market-activity-panel"'))
        self.assertLess(self.dashboard.index('id="market-activity-panel"'),
                        self.dashboard.index('<section class="panel stocks-panel">'))
        blob = b"blob " + str(len(self.market_activity.encode("utf-8"))).encode("ascii") + b"\0" + self.market_activity.encode("utf-8")
        self.assertEqual(hashlib.sha1(blob).hexdigest(), "345a7ecd989b5416caa4e73680bf221c2ba6cf00")
        self.assertNotIn("KNOW YOUR STOCK", self.market_activity)
        self.assertNotIn("data-fpi-sector-eye", self.market_activity)

    def test_sector_direction_requires_broad_quote_coverage(self):
        self.assertIn("d.minRequired=Math.max(5,Math.ceil(rows.length*0.6))", self.market_activity)
        self.assertIn("if(!d.qualified)return 1", self.market_activity)
        self.assertIn("if(!d.qualified)", self.market_activity)
        self.assertIn("कम-से-कम 5 स्टॉक", self.market_activity)
        self.assertIn("दिशा के लिए कम-से-कम", self.market_activity)

    def test_fpi_eye_is_inline_between_sector_name_and_net_amount(self):
        self.assertIn('class="fpi-eye" data-fpi-sector-eye=', self.dashboard)
        self.assertIn('title="इस सेक्टर के स्टॉक देखें">👁️</button><b class="', self.dashboard)
        self.assertIn('<script src="fpi-sector-tilt.js?v=6" defer></script>', self.dashboard)

    def test_fpi_sector_popup_uses_verified_sector_master(self):
        for text in ("nse-fo-stock-sector-master.json", "data-fpi-sector-eye",
                     "function openSector(sector)", "function renderSector(sector)",
                     "getStocks(sector)", "data-fpi-stock", "fpi-stock-overlay",
                     "इस NSDL सेक्टर के लिए सत्यापित NSE F&O stock mapping उपलब्ध नहीं"):
            self.assertIn(text, self.fpi_script)

    def test_stock_detail_includes_company_and_verified_financial_sections(self):
        for text in ("stock-company-data.json", "कंपनी का कारोबार",
                     "KNOW YOUR STOCK", "Market Snapshot",
                     "Shareholding Pattern", "Fundamental Ratios",
                     "NSE XBRL Quarter Revenue", "NSE XBRL Quarter Net Profit",
                     "NSE XBRL Basic EPS", "Quality Scorecard",
                     "Valuation Scorecard", "Insights & Sector Position",
                     "Price & Trading Activity", "पुराना रिकॉर्ड",
                     "डेटा उपलब्ध नहीं", "TradingView Chart खोलें"):
            self.assertIn(text, self.fpi_script)
        self.assertIn("window.setInterval(loadData,5*60*1000)", self.fpi_script)

    def test_existing_dashboard_safety_and_refresh_hooks_remain(self):
        self.assertIn("function updateTradeGuard(data)", self.dashboard)
        self.assertIn("const REFRESH_MS = 5 * 60 * 1000", self.dashboard)
        self.assertIn("NO TRADE", self.dashboard)

if __name__ == "__main__":
    unittest.main()
