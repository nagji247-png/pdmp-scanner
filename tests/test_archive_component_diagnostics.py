import unittest

from archive_component_diagnostics import build_report


class ArchiveComponentDiagnosticsTests(unittest.TestCase):
    def test_nse_and_mcx_archives_are_reported_but_never_scored(self):
        nse = {"records": [
            {"date": "2026-11-05", "symbols": {"NIFTY": {
                "contract_rows": 10, "by_expiry": {
                    "2026-11-09": {
                        "CE": {"open_interest": 100, "change_in_oi": 10, "contracts": 2},
                        "PE": {"open_interest": 120, "change_in_oi": 20, "contracts": 2},
                    }
                }
            }}},
            {"date": "2026-11-06", "symbols": {"NIFTY": {
                "contract_rows": 12, "by_expiry": {
                    "2026-11-09": {
                        "CE": {"open_interest": 110, "change_in_oi": 10, "contracts": 3},
                        "PE": {"open_interest": 140, "change_in_oi": 20, "contracts": 3},
                    }
                }
            }}},
        ]}
        mcx = {"records": [
            {"date": "2026-11-05", "contract_rows": [
                {"InstrumentName": "FUTCOM", "Symbol": "GOLD", "ExpiryDate": "04DEC2026", "OpenInterest": 100, "Close": 1000},
                {"InstrumentName": "FUTCOM", "Symbol": "SILVER", "ExpiryDate": "04DEC2026", "OpenInterest": 200, "Close": 2000},
            ]},
            {"date": "2026-11-06", "contract_rows": [
                {"InstrumentName": "FUTCOM", "Symbol": "GOLD", "ExpiryDate": "04DEC2026", "OpenInterest": 110, "Close": 1010},
                {"InstrumentName": "FUTCOM", "Symbol": "SILVER", "ExpiryDate": "04DEC2026", "OpenInterest": 190, "Close": 1990},
            ]},
        ]}
        report = build_report(nse, mcx, generated_at="2026-11-08T00:00:00Z")
        nifty = report["nse_index_options"]["assets"]["NIFTY"]
        futures = report["nse_index_expiry_research"]["index_futures"]["NIFTY"]
        option_research = report["nse_index_expiry_research"]["index_options"]["NIFTY"]
        gold = report["mcx_commodity_futures"]["assets"]["GOLD"]
        silver = report["mcx_commodity_futures"]["assets"]["SILVER"]
        self.assertEqual(nifty["sessions"], 2)
        self.assertEqual(futures["same_expiry_observations"], 0)
        self.assertIsNone(futures["score"])
        self.assertFalse(futures["included_in_asset_final"])
        self.assertEqual(option_research["same_expiry_observations"], 1)
        option_pair = option_research["observations"][0]
        self.assertEqual(option_pair["sides"]["CE"]["oi_change"], 10)
        self.assertEqual(option_pair["sides"]["PE"]["oi_change"], 20)
        self.assertEqual(nifty["same_expiry_session_pairs"], 1)
        self.assertEqual(gold["same_expiry_observations"], 1)
        self.assertEqual(gold["observations"][0]["regime"], "price_up_oi_up")
        self.assertEqual(silver["observations"][0]["regime"], "price_down_oi_down")
        for item in (nifty, gold, silver):
            self.assertIsNone(item["score"])
            self.assertFalse(item["included_in_asset_final"])
            self.assertEqual(item["validation_status"], "INSUFFICIENT_HISTORY")

    def test_missing_expiry_overlap_creates_no_mcx_observation(self):
        mcx = {"records": [
            {"date": "2026-11-05", "contract_rows": [
                {"InstrumentName": "FUTCOM", "Symbol": "GOLD", "ExpiryDate": "04DEC2026", "OpenInterest": 100, "Close": 1000},
                {"InstrumentName": "FUTCOM", "Symbol": "SILVER", "ExpiryDate": "04DEC2026", "OpenInterest": 200, "Close": 2000},
            ]},
            {"date": "2026-11-06", "contract_rows": [
                {"InstrumentName": "FUTCOM", "Symbol": "GOLD", "ExpiryDate": "05JAN2027", "OpenInterest": 110, "Close": 1010},
                {"InstrumentName": "FUTCOM", "Symbol": "SILVER", "ExpiryDate": "05JAN2027", "OpenInterest": 190, "Close": 1990},
            ]},
        ]}
        from archive_component_diagnostics import summarize_mcx
        result = summarize_mcx(mcx)
        self.assertEqual(result["assets"]["GOLD"]["same_expiry_observations"], 0)
        self.assertEqual(result["assets"]["SILVER"]["same_expiry_observations"], 0)


if __name__ == "__main__":
    unittest.main()
