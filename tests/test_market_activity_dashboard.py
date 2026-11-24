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
        self.assertIn('src="market-activity.js?v=24"', self.dashboard)
        self.assertIn('id="fpi-sector-tilt"', self.dashboard)
        self.assertLess(self.dashboard.index('id="fpi-sector-tilt"'),
                        self.dashboard.index('id="market-activity-panel"'))
        self.assertLess(self.dashboard.index('id="market-activity-panel"'),
                        self.dashboard.index('<section class="panel stocks-panel">'))
        self.assertLess(self.market_activity.index("render();"), self.market_activity.index('fetchJson(DRAWING_API+"/api/drawings?t="+Date.now(),"Drawing API",12000)'))
        self.assertIn("Optional Drawing API unavailable", self.market_activity)
        self.assertIn("function fetchJson(url,label,timeoutMs)", self.market_activity)
        self.assertIn('fetchJson("nse-fo-stock-sector-master.json?t="+Date.now(),"NSE master",15000)', self.market_activity)
        self.assertIn('fetchJson("data.json?t="+Date.now(),"Market data",15000)', self.market_activity)
        self.assertIn('fetchJson("fpi-sector-data.json?t="+Date.now(),"FPI data",12000)', self.market_activity)
        self.assertIn("FPI and drawings are supplementary: neither may delay the sector radar.", self.market_activity)
        self.assertIn("window.__TRINETRA_MA_STARTED__=true;", self.market_activity)
        self.assertIn("Market Activity अभी शुरू नहीं हो पाया।", self.dashboard)
        self.assertNotIn("KNOW YOUR STOCK", self.market_activity)
        self.assertNotIn("data-fpi-sector-eye", self.market_activity)

    def test_market_activity_includes_non_fno_eod_cash_symbols_without_fake_sector_mapping(self):
        self.assertIn('names["सेक्टर मैपिंग उपलब्ध नहीं"]=true', self.market_activity)
        self.assertIn('symbols=symbols.concat(Object.keys(quotes).filter(function(s){return !known[s];}))', self.market_activity)
        self.assertIn('industry:"इंडस्ट्री/सेक्टर मैपिंग उपलब्ध नहीं"', self.market_activity)
        self.assertIn('Delivery Quantity:', self.market_activity)
        self.assertIn('Delivery %:', self.market_activity)
        self.assertIn('कुल Trades:', self.market_activity)
        self.assertIn('universe=Object.assign({},master.stocks||{},marketData&&marketData.market_activity_quotes', self.market_activity)

    def test_market_activity_counts_all_sector_quotes_and_warns_on_small_samples(self):
        self.assertIn("symbols.filter(function(k){var q=quote(k);", self.market_activity)
        self.assertNotIn("Object.keys(marketData&&marketData.instruments||{}).filter", self.market_activity)
        self.assertIn("coverageCaution(d,s.rows.length)", self.market_activity)
        self.assertIn("दिशा केवल उपलब्ध ", self.market_activity)
        self.assertIn("src=\"market-activity.js?v=24\"", self.dashboard)

    def test_fpi_eye_is_inline_between_sector_name_and_net_amount(self):
        self.assertIn('class="fpi-eye" data-fpi-sector-eye=', self.dashboard)
        self.assertIn('title="इस सेक्टर के स्टॉक देखें">👁️</button><b class="', self.dashboard)
        self.assertIn('<script src="fpi-sector-tilt.js?v=8" defer></script>', self.dashboard)

    def test_fpi_sector_popup_uses_verified_sector_master(self):
        for text in ("nse-fo-stock-sector-master.json", "data-fpi-sector-eye",
                     "function openSector(sector)", "function renderSector(sector)",
                     "getStocks(sector)", "data-fpi-stock", "fpi-stock-overlay",
                     "इस NSDL सेक्टर के लिए सत्यापित NSE F&O stock mapping उपलब्ध नहीं"):
            self.assertIn(text, self.fpi_script)

    def test_fpi_detail_reads_full_universe_eod_quote_fallback(self):
        self.assertIn("function stockQuote(symbol)", self.fpi_script)
        self.assertIn("marketData.market_activity_quotes", self.fpi_script)
        self.assertIn("stockQuote(r.symbol)", self.fpi_script)
        self.assertIn("stockQuote(symbol)", self.fpi_script)

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


    def test_latest_activity_alerts_reserve_visible_slots_for_high_watch_and_flow(self):
        self.assertIn("function selectActivityAlerts(out)", self.market_activity)
        self.assertIn('["high","watch","flow"].forEach', self.market_activity)
        self.assertIn('limits={high:3,watch:3,flow:3}', self.market_activity)
        self.assertIn("return selectActivityAlerts(out);", self.market_activity)
        self.assertIn("selected.slice(0,8)", self.market_activity)

    def test_existing_dashboard_safety_and_refresh_hooks_remain(self):
        self.assertIn("function updateTradeGuard(data)", self.dashboard)
        self.assertIn("const REFRESH_MS = 5 * 60 * 1000", self.dashboard)
        self.assertIn("NO TRADE", self.dashboard)

    def test_radar_uses_two_buy_sell_panels_with_four_clickable_signal_groups(self):
        for marker in (
            ".ma-buy-sell-layout{gap:14px}",
            ".ma-buy-sell-layout>.ma-sector-group.bull",
            ".ma-buy-sell-layout>.ma-sector-group.bear",
            ".ma-signal-subgroup",
            "EARLY BUYING",
            "CONFIRMED BUYING",
            "EARLY SELLING",
            "SELLING WATCH",
            "function sectorBuyingState(s)",
            "news.total>=2&&news.positive>news.negative",
            "news.total>=2&&news.negative>news.positive",
            "तुलनात्मक वॉल्यूम डेटा सत्यापित न होने पर",
        ):
            self.assertIn(marker, self.market_activity)
        self.assertIn('class="ma-quick-summary"', self.market_activity)
        for key, label in (("bull", "तेजी वाले सेक्टर"), ("bear", "मंदी वाले सेक्टर"),
                           ("unusual", "असामान्य स्टॉक"), ("fpi", "FPI प्रवाह बदलाव")):
            self.assertIn('data-radar="' + key + '"', self.market_activity)
            self.assertIn(label, self.market_activity)
        for key in ('early-buying', 'confirmed-buying', 'early-selling', 'selling-watch'):
            self.assertIn('key:"' + key + '"', self.market_activity)
        self.assertIn('data-radar=', self.market_activity)
        self.assertIn('g.key', self.market_activity)
        self.assertIn('closest("[data-radar]")', self.market_activity)
        self.assertIn('push({type:"radar",kind:radar.getAttribute("data-radar")', self.market_activity)

if __name__ == "__main__":
    unittest.main()
