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
        cls.drawings = json.loads((ROOT / "stock-chart-drawings.json").read_text(encoding="utf-8"))

    def test_verified_fno_master_is_218_stocks_across_18_sectors(self):
        self.assertEqual(len(self.master["stocks"]), 218)
        self.assertEqual(len({row["sector"] for row in self.master["stocks"].values()}), 18)
        self.assertEqual(self.drawings["snapshots"], {})
        self.assertNotIn("chart_layout_id", self.drawings)

    def test_activity_panel_remains_between_fpi_and_stock_list(self):
        self.assertIn('href="#market-activity"', self.dashboard)
        self.assertIn('id="market-activity"', self.dashboard)
        self.assertIn('src="market-activity.js?v=7"', self.dashboard)
        self.assertLess(self.dashboard.index('id="fpi-sector-tilt"'),
                        self.dashboard.index('id="market-activity-panel"'))
        self.assertLess(self.dashboard.index('id="market-activity-panel"'),
                        self.dashboard.index('<section class="panel stocks-panel">'))

    def test_radar_has_four_clickable_summary_counts(self):
        for text in ("सबसे ऊपर — आज की हलचल", "MARKET ACTIVITY RADAR",
                     "तेजी वाले सेक्टर", "मंदी वाले सेक्टर", "असामान्य स्टॉक",
                     "FPI प्रवाह बदलाव", 'data-radar="bull"', 'data-radar="bear"',
                     'data-radar="unusual"', 'data-radar="fpi"', "SECTOR ACTIVITY",
                     "data-stock", "ma-sector-grid", "data-sector", "data-back",
                     "stock-chart-drawings.json", "s3.tradingview.com/snapshots",
                     "अपना TradingView Chart खोलें", "https://www.tradingview.com/chart/?symbol=NSE%3A"):
            self.assertIn(text, self.script)

    def test_sector_and_stock_order_is_activity_first(self):
        self.assertIn("function compareSectors", self.script)
        self.assertIn("function compareStocks", self.script)
        self.assertIn("function sectorOrder", self.script)
        self.assertIn("function stockOrder", self.script)
        self.assertIn("function fpiDeltaMap", self.script)
        self.assertIn("function activityAlerts()", self.script)
        self.assertIn("ma-chart-preview{border:1px solid #9272d6", self.script)
        self.assertIn("पिछली अवधि से तुलना", self.script)
        self.assertIn("LATEST ACTIVITY ALERTS", self.script)
        self.assertNotIn("218 STOCK MASTER LIST", self.script)
        self.assertNotIn("FPI FLOW + NEWS CONFIRMATION</div><div class=\"ma-intro\"", self.script)

    def test_uses_existing_static_data_and_does_not_invent_missing_fields(self):
        for text in ("nse-fo-stock-sector-master.json", "fpi-sector-data.json",
                     'fetch("data.json?', "वॉल्यूम:",
                     "crowd mood उपलब्ध नहीं", "स्टॉक-स्तरीय वास्तविक buy/sell या FPI order-flow डेटा उपलब्ध नहीं है",
                     "market_activity_quotes", "price_source"):
            self.assertIn(text, self.script)

    def test_navigation_drilldowns_stay_inside_fixed_scrollable_popup(self):
        self.assertIn('.ma-view-overlay{position:fixed', self.script)
        self.assertIn('.ma-view-dialog{width:min(100%,760px)', self.script)
        self.assertIn('overscroll-behavior:contain', self.script)
        self.assertIn('data-view-content', self.script)
        self.assertIn('data-close-view', self.script)
        self.assertIn('data-back', self.script)
        self.assertIn('function ensurePopup()', self.script)
        self.assertIn('document.body.style.overflow="hidden"', self.script)
        self.assertIn('viewRoot=popupBody', self.script)
        self.assertIn('history.pushState', self.script)
        self.assertNotIn('function scrollToActivityTop()', self.script)
        self.assertNotIn('requestAnimationFrame(scrollToActivityTop)', self.script)
        self.assertIn('window.addEventListener("popstate"', self.script)
        self.assertIn('sector:stk.getAttribute("data-sector-name")||"",scroll:0', self.script)
        self.assertIn('KNOW YOUR STOCK', self.script)

    def test_fpi_sector_rows_open_stock_list_and_stock_detail_is_company_only(self):
        self.assertIn('class="ma-flow ma-flow-button" data-sector="', self.script)
        self.assertIn("sort(function(a,b){return b.flow-a.flow;})", self.script)
        self.assertIn("कंपनी का कारोबार", self.script)
        self.assertIn("Shareholding Pattern", self.script)
        self.assertIn("Fundamental Ratios", self.script)
        self.assertIn("NSE XBRL Quarter Revenue", self.script)
        self.assertIn("NSE XBRL Quarter Net Profit", self.script)
        self.assertIn("NSE XBRL Basic EPS", self.script)
        self.assertIn("integrated_financials", self.script)
        self.assertIn("function parseNsePeriod(value)", self.script)
        self.assertIn("comparisonPeriodFresh", self.script)
        self.assertIn("पुराना रिकॉर्ड", self.script)
        self.assertIn("Integrated XBRL · ", self.script)
        self.assertIn("Valuation Scorecard", self.script)
        stock_detail = self.script.split("function renderStock(symbol,sector){", 1)[1].split("\nfunction render(){", 1)[0]
        self.assertNotIn("crowd", stock_detail.lower())
        self.assertNotIn("pdmp", stock_detail.lower())

    def test_existing_dashboard_safety_and_refresh_hooks_remain(self):
        self.assertIn("function updateTradeGuard(data)", self.dashboard)
        self.assertIn("const REFRESH_MS = 5 * 60 * 1000", self.dashboard)
        self.assertIn("NO TRADE", self.dashboard)


if __name__ == "__main__":
    unittest.main()
