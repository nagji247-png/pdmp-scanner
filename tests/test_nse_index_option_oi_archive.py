import unittest

from component_scoring import aggregate_nse_udiff_index_option_oi


class NSEIndexOptionOIArchiveTests(unittest.TestCase):
    def rows(self):
        common = {
            "FinInstrmTp": "IDO",
            "TckrSymb": "NIFTY",
            "BizDt": "2026-11-06",
            "XpryDt": "2026-11-26",
            "OpnIntrst": "1000",
            "ChngInOpnIntrst": "125",
        }
        return [
            {**common, "OptnTp": "CE"},
            {**common, "OptnTp": "PE", "OpnIntrst": "2000", "ChngInOpnIntrst": "-50"},
        ]

    def test_exact_symbol_and_date_aggregate_both_option_sides(self):
        result = aggregate_nse_udiff_index_option_oi(
            self.rows(), "NIFTY", "2026-11-06"
        )
        self.assertTrue(result["available"])
        self.assertFalse(result["included_in_asset_final"])
        self.assertFalse(result["coverage_validated"])
        self.assertEqual(result["call"]["open_interest"], 1000)
        self.assertEqual(result["call"]["change_in_oi"], 125)
        self.assertEqual(result["put"]["open_interest"], 2000)
        self.assertEqual(result["put"]["change_in_oi"], -50)
        self.assertEqual(result["matched_contract_rows"], 2)

    def test_wrong_symbol_or_trade_date_never_contributes(self):
        rows = self.rows() + [
            {**self.rows()[0], "TckrSymb": "BANKNIFTY"},
            {**self.rows()[1], "BizDt": "2026-11-05"},
        ]
        result = aggregate_nse_udiff_index_option_oi(
            rows, "NIFTY", "2026-11-06"
        )
        self.assertFalse(result["available"])
        self.assertEqual(result["matched_contract_rows"], 1)

    def test_missing_one_side_fails_closed(self):
        result = aggregate_nse_udiff_index_option_oi(
            [self.rows()[0]], "NIFTY", "2026-11-06"
        )
        self.assertFalse(result["available"])
        self.assertIsNotNone(result["reason"])
        self.assertFalse(result["included_in_asset_final"])

    def test_malformed_oi_or_expiry_is_not_silently_zeroed(self):
        rows = self.rows()
        rows[1] = {**rows[1], "OpnIntrst": "", "XpryDt": ""}
        result = aggregate_nse_udiff_index_option_oi(
            rows, "NIFTY", "2026-11-06"
        )
        self.assertFalse(result["available"])
        self.assertIn("missing_oi_change_or_expiry", result["validation_warnings"])


if __name__ == "__main__":
    unittest.main()
