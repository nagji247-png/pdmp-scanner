import unittest

from archive_component_diagnostics import build_report, summarize_option_buildup


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


    def test_option_buildup_archive_reports_per_index_test_score_and_category_counts(self):
        def contract(symbol, side, strike, close, oi, expiry="2026-11-12"):
            return {"expiry": expiry, "side": side, "strike": strike,
                    "close": close, "open_interest": oi}
        old_nifty, new_nifty, old_bank, new_bank = [], [], [], []
        for i in range(50):
            old_nifty.append(contract("NIFTY", "CE", 25000+i, 100, 1000))
            new_nifty.append(contract("NIFTY", "CE", 25000+i,
                                      110 if i < 35 else 90, 1100))
            old_nifty.append(contract("NIFTY", "PE", 25000+i, 100, 1000))
            new_nifty.append(contract("NIFTY", "PE", 25000+i,
                                      90 if i < 35 else 110, 1100))
            old_bank.append(contract("BANKNIFTY", "CE", 50000+i, 100, 1000))
            new_bank.append(contract("BANKNIFTY", "CE", 50000+i,
                                     110 if i < 15 else 90, 1100))
            old_bank.append(contract("BANKNIFTY", "PE", 50000+i, 100, 1000))
            new_bank.append(contract("BANKNIFTY", "PE", 50000+i,
                                     90 if i < 15 else 110, 1100))
        archive = {"records": [
            {"date": "2026-11-11", "option_contracts": {
                "NIFTY": {"contracts": old_nifty},
                "BANKNIFTY": {"contracts": old_bank}}},
            {"date": "2026-11-12", "option_contracts": {
                "NIFTY": {"contracts": new_nifty},
                "BANKNIFTY": {"contracts": new_bank}}},
        ]}
        report = summarize_option_buildup(archive, min_classified=100)
        nifty = report["assets"]["NIFTY"]
        bank = report["assets"]["BANKNIFTY"]
        self.assertEqual(nifty["matched_contracts"], 100)
        self.assertEqual(nifty["classified_contracts"], 100)
        self.assertEqual(bank["matched_contracts"], 100)
        self.assertEqual(bank["classified_contracts"], 100)
        self.assertIsNotNone(nifty["test_score"])
        self.assertIsNotNone(bank["test_score"])
        self.assertNotEqual(nifty["test_score"], bank["test_score"])
        self.assertFalse(nifty["included_in_asset_final"])
        self.assertFalse(bank["included_in_asset_final"])
        self.assertFalse(nifty["coverage_validated"])
        self.assertEqual(nifty["test_score_status"], "ARCHIVE_PAIR_TEST_ONLY_NOT_LIVE")

    def test_option_buildup_archive_does_not_score_insufficient_classified_contracts(self):
        def row(side, strike, close, oi):
            return {"expiry": "2026-11-12", "side": side, "strike": strike,
                    "close": close, "open_interest": oi}
        old, new = [], []
        for i in range(10):
            for side in ("CE", "PE"):
                old.append(row(side, 25000+i, 100, 1000))
                new.append(row(side, 25000+i, 110 if side == "CE" else 90, 1100))
        archive = {"records": [
            {"date": "2026-11-11", "option_contracts": {"NIFTY": {"contracts": old}}},
            {"date": "2026-11-12", "option_contracts": {"NIFTY": {"contracts": new}}},
        ]}
        result = summarize_option_buildup(archive, min_classified=100)["assets"]["NIFTY"]
        self.assertEqual(result["matched_contracts"], 20)
        self.assertEqual(result["classified_contracts"], 20)
        self.assertIsNone(result["test_score"])
        self.assertEqual(result["test_score_status"], "UNAVAILABLE")
        self.assertFalse(result["included_in_asset_final"])



if __name__ == "__main__":
    unittest.main()
