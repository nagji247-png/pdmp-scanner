import unittest

from nse_integrated_xbrl import parse_integrated_financial_xbrl


class IntegratedFinancialXbrlTests(unittest.TestCase):
    def xml(self):
        return """<?xml version="1.0"?>
        <xbrl xmlns="http://www.xbrl.org/2003/instance"
              xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
          <context id="OneD"><entity><identifier>INE000A</identifier></entity>
            <period><startDate>2026-07-01</startDate><endDate>2026-09-30</endDate></period></context>
          <context id="FourD"><entity><identifier>INE000A</identifier></entity>
            <period><startDate>2026-04-01</startDate><endDate>2026-09-30</endDate></period></context>
          <context id="OneI"><entity><identifier>INE000A</identifier></entity>
            <period><instant>2026-09-30</instant></period></context>
          <context id="PY_I"><entity><identifier>INE000A</identifier></entity>
            <period><instant>2025-09-30</instant></period></context>
          <RevenueFromOperations contextRef="OneD">211276500000</RevenueFromOperations>
          <ProfitLossForPeriod contextRef="OneD">18750000000</ProfitLossForPeriod>
          <BasicEarningsLossPerShareFromContinuingOperations contextRef="OneD">12.5</BasicEarningsLossPerShareFromContinuingOperations>
          <EquityAndLiabilities contextRef="OneI">900000000000</EquityAndLiabilities>
          <Equity contextRef="OneI">300000000000</Equity>
          <CurrentFinancialLiabilities contextRef="OneI">100000000000</CurrentFinancialLiabilities>
          <NoncurrentFinancialLiabilities contextRef="OneI">50000000000</NoncurrentFinancialLiabilities>
          <RevenueFromOperations contextRef="FourD">566710500000</RevenueFromOperations>
          <RevenueFromOperations contextRef="PY_I">999999999999</RevenueFromOperations>
        </xbrl>"""

    def test_quarter_ytd_and_balance_sheet_mapping(self):
        data = parse_integrated_financial_xbrl(self.xml())
        self.assertEqual(data["quarter"]["revenue_cr"], 21127.65)
        self.assertEqual(data["quarter"]["net_profit_cr"], 1875.0)
        self.assertEqual(data["quarter"]["basic_eps"], 12.5)
        self.assertEqual(data["ytd"]["revenue_cr"], 56671.05)
        self.assertEqual(data["balance_sheet"]["total_assets_cr"], 90000.0)
        self.assertNotIn("debt_equity_ratio", data["balance_sheet"])
        self.assertEqual(data["raw_facts"]["RevenueFromOperations"]["prior_balance_sheet"], 99999.9999999)

    def test_unknown_or_invalid_xml_is_unavailable(self):
        self.assertIsNone(parse_integrated_financial_xbrl("<xbrl/>"))
        self.assertIsNone(parse_integrated_financial_xbrl("not xml"))


if __name__ == "__main__":
    unittest.main()
