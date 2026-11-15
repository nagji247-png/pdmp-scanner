import unittest

from nse_xbrl import filing_xml_url, parse_financial_results_comparison, parse_shareholding_xbrl


class ShareholdingXbrlTests(unittest.TestCase):
    def xml(self, promoter="5049", public="4951", fii="1200", dii="900"):
        return f"""<?xml version="1.0"?>
        <xbrl xmlns="http://www.xbrl.org/2003/instance">
          <context id="p"><entity><identifier>INE000A</identifier><segment>
            <explicitMember dimension="d">in-bse-shp:ShareholdingOfPromoterAndPromoterGroupMember</explicitMember>
          </segment></entity><period><instant>2026-09-30</instant></period></context>
          <context id="u"><entity><identifier>INE000A</identifier><segment>
            <explicitMember dimension="d">in-bse-shp:PublicShareholdingMember</explicitMember>
          </segment></entity><period><instant>2026-09-30</instant></period></context>
          <context id="f"><entity><identifier>INE000A</identifier><segment>
            <explicitMember dimension="d">in-bse-shp:InstitutionsForeignMember</explicitMember>
          </segment></entity><period><instant>2026-09-30</instant></period></context>
          <context id="d"><entity><identifier>INE000A</identifier><segment>
            <explicitMember dimension="d">in-bse-shp:InstitutionsDomesticMember</explicitMember>
          </segment></entity><period><instant>2026-09-30</instant></period></context>
          <in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="p">{promoter}</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
          <in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="u">{public}</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
          <in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="f">{fii}</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
          <in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="d">{dii}</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
        </xbrl>""".replace("<xbrl ", "<xbrl xmlns:in-bse-shp='http://www.bseindia.com/xbrl/shp/2025-10-31/in-bse-shp' ", 1)

    def test_legacy_percent_scale(self):
        parsed = parse_shareholding_xbrl(self.xml())
        self.assertEqual(parsed["promoter_pct"], 50.49)
        self.assertEqual(parsed["public_pct"], 49.51)
        self.assertEqual(parsed["fii_pct"], 12.0)
        self.assertEqual(parsed["dii_pct"], 9.0)

    def test_fraction_scale(self):
        parsed = parse_shareholding_xbrl(self.xml("0.5049", "0.4951", "0.12", "0.09"))
        self.assertEqual(parsed["promoter_pct"], 50.49)
        self.assertEqual(parsed["public_pct"], 49.51)

    def test_unknown_and_empty_documents_are_unavailable(self):
        self.assertIsNone(parse_shareholding_xbrl("<xbrl/>"))
        self.assertIsNone(parse_shareholding_xbrl("not xml"))

    def test_financial_results_lakhs_converted_to_crore_and_period_sorted(self):
        payload = {"resCmpData": [
            {"re_to_dt": "31-DEC-2025", "re_total_inc": "150000",
             "re_net_profit": "12000", "re_basic_eps_for_cont_dic_opr": "12.5",
             "re_debt_eqt_rat": "0.4"},
            {"re_to_dt": "30-SEP-2025", "re_total_inc": "100000",
             "re_net_profit": "9000", "re_basic_eps": "9.5",
             "re_debt_eqt_rat": "0.5"},
        ]}
        parsed = parse_financial_results_comparison(payload)
        self.assertEqual(parsed["latest"]["period_end"], "31-DEC-2025")
        self.assertEqual(parsed["latest"]["revenue_cr"], 1500.0)
        self.assertEqual(parsed["latest"]["net_profit_cr"], 120.0)
        self.assertEqual(parsed["latest"]["eps"], 12.5)
        self.assertEqual(parsed["latest"]["debt_equity"], 0.4)
        self.assertEqual(len(parsed["quarters"]), 2)

    def test_financial_results_missing_values_stay_missing(self):
        self.assertIsNone(parse_financial_results_comparison({}))
        parsed = parse_financial_results_comparison({"resCmpData": [
            {"re_to_dt": "31-MAR-2026", "re_total_inc": None,
             "re_net_profit": None, "re_basic_eps": None}
        ]})
        self.assertIsNone(parsed["latest"]["revenue_cr"])
        self.assertIsNone(parsed["latest"]["net_profit_cr"])
        self.assertIsNone(parsed["latest"]["eps"])

    def test_filing_url_requires_real_url(self):
        self.assertEqual(filing_xml_url({"xbrl": "/corporate/xbrl/SHP_A.xml"}),
                         "https://nsearchives.nseindia.com/corporate/xbrl/SHP_A.xml")
        self.assertIsNone(filing_xml_url({"xbrl": "-"}))


if __name__ == "__main__":
    unittest.main()
