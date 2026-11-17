import unittest
from pathlib import Path


class FpiStockPopupTests(unittest.TestCase):
    def test_debt_equity_prefers_current_integrated_xbrl_ratio(self):
        source = Path("fpi-sector-tilt.js").read_text(encoding="utf-8")
        self.assertIn('num(iq.debt_equity_ratio)!==null', source)
        self.assertIn('" · NSE Integrated XBRL · "+missing(filing.quarter_end)', source)
        self.assertIn('+" · "+missing(filing.consolidated)', source)

    def test_reported_ratio_fallback_remains_available(self):
        source = Path("fpi-sector-tilt.js").read_text(encoding="utf-8")
        self.assertIn('fresh&&latest.debt_equity!==null&&latest.debt_equity!==undefined', source)
        self.assertIn('old(latest.debt_equity)', source)

    def test_integrated_xbrl_coverage_ratios_are_displayed_with_filing_context(self):
        source = Path("fpi-sector-tilt.js").read_text(encoding="utf-8")
        self.assertIn('iq.debt_service_coverage_ratio', source)
        self.assertIn('iq.interest_service_coverage_ratio', source)
        self.assertIn('" · NSE Integrated XBRL · "+missing(filing.quarter_end)', source)

    def test_dashboard_uses_new_popup_cache_version(self):
        source = Path("dashboard.html").read_text(encoding="utf-8")
        self.assertIn("fpi-sector-tilt.js?v=8", source)
        self.assertNotIn("fpi-sector-tilt.js?v=6", source)


if __name__ == "__main__":
    unittest.main()
