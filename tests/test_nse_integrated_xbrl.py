import unittest

from nse_integrated_xbrl import parse_integrated_financial_xbrl


class IntegratedFinancialXbrlTests(unittest.TestCase):
    def xml(self):
        return """<?xml version="1.0"?>
        <xbrl xmlns="http://www.xbrl.org/2003/instance"
              xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
          <unit id="INR"><measure>iso4217:INR</measure></unit>
          <unit id="USD"><measure>iso4217:USD</measure></unit>
          <context id="OneD"><entity><identifier>INE000A</identifier></entity>
            <period><startDate>2026-07-01</startDate><endDate>2026-09-30</endDate></period></context>
          <context id="FourD"><entity><identifier>INE000A</identifier></entity>
            <period><startDate>2026-04-01</startDate><endDate>2026-09-30</endDate></period></context>
          <context id="OneI"><entity><identifier>INE000A</identifier></entity>
            <period><instant>2026-09-30</instant></period></context>
          <context id="PY_I"><entity><identifier>INE000A</identifier></entity>
            <period><instant>2025-09-30</instant></period></context>
          <RevenueFromOperations unitRef="INR" contextRef="OneD">211276500000</RevenueFromOperations>
          <ProfitLossForPeriod unitRef="INR" contextRef="OneD">18750000000</ProfitLossForPeriod>
          <BasicEarningsLossPerShareFromContinuingOperations unitRef="INR" contextRef="OneD">12.5</BasicEarningsLossPerShareFromContinuingOperations>
          <Assets unitRef="INR" contextRef="OneI">900000000000</Assets>
          <EquityAndLiabilities unitRef="INR" contextRef="OneI">900000000000</EquityAndLiabilities>
          <Equity unitRef="INR" contextRef="OneI">300000000000</Equity>
          <CurrentFinancialLiabilities unitRef="INR" contextRef="OneI">100000000000</CurrentFinancialLiabilities>
          <NoncurrentFinancialLiabilities unitRef="INR" contextRef="OneI">50000000000</NoncurrentFinancialLiabilities>
          <RevenueFromOperations unitRef="INR" contextRef="FourD">566710500000</RevenueFromOperations>
          <RevenueFromOperations unitRef="USD" contextRef="OneD">999999999999</RevenueFromOperations>
          <RevenueFromOperations unitRef="INR" contextRef="PY_I">999999999999</RevenueFromOperations>
        </xbrl>"""

    def test_quarter_ytd_and_balance_sheet_mapping(self):
        data = parse_integrated_financial_xbrl(self.xml())
        self.assertEqual(data["quarter"]["revenue_cr"], 21127.65)
        self.assertNotEqual(data["quarter"]["revenue_cr"], 99999.9999999)
        self.assertEqual(data["quarter"]["net_profit_cr"], 1875.0)
        self.assertEqual(data["quarter"]["basic_eps"], 12.5)
        self.assertEqual(data["ytd"]["revenue_cr"], 56671.05)
        self.assertEqual(data["balance_sheet"]["total_assets_cr"], 90000.0)
        self.assertEqual(data["balance_sheet"]["total_equity_cr"], 30000.0)
        self.assertNotIn("debt_equity_ratio", data["balance_sheet"])
        self.assertNotIn("EquityAndLiabilities", data["raw_facts"])
        self.assertEqual(data["raw_facts"]["RevenueFromOperations"]["prior_balance_sheet"], 99999.9999999)

    def test_equity_and_liabilities_alone_does_not_masquerade_as_assets(self):
        xml = self.xml().replace(
            '<Assets unitRef="INR" contextRef="OneI">900000000000</Assets>', ''
        )
        data = parse_integrated_financial_xbrl(xml)
        self.assertNotIn("total_assets_cr", data["balance_sheet"])

    def test_unknown_or_invalid_xml_is_unavailable(self):
        self.assertIsNone(parse_integrated_financial_xbrl("<xbrl/>"))
        self.assertIsNone(parse_integrated_financial_xbrl("not xml"))


if __name__ == "__main__":
    unittest.main()
