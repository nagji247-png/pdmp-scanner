import unittest

from nse_xbrl import filing_xml_url, parse_shareholding_xbrl


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

    def test_filing_url_requires_real_url(self):
        self.assertEqual(filing_xml_url({"xbrl": "/corporate/xbrl/SHP_A.xml"}),
                         "https://nsearchives.nseindia.com/corporate/xbrl/SHP_A.xml")
        self.assertIsNone(filing_xml_url({"xbrl": "-"}))


if __name__ == "__main__":
    unittest.main()
