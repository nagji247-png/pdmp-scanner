import unittest

from nse_option_buildup import build_option_buildup_diagnostic


class NSEOptionBuildupTests(unittest.TestCase):
    def _contract(self, expiry, side, strike, close, oi):
        return {
            "expiry": expiry, "side": side, "strike": strike,
            "close": close, "open_interest": oi,
        }

    def test_all_four_patterns_use_same_contract_and_oi_quantity(self):
        old = [
            self._contract("2026-11-17", "CE", 25000, 100, 1000),
            self._contract("2026-11-17", "PE", 25000, 100, 1000),
            self._contract("2026-11-17", "CE", 25100, 100, 1000),
            self._contract("2026-11-17", "PE", 25100, 100, 1000),
        ]
        new = [
            self._contract("2026-11-17", "CE", 25000, 110, 1200),  # long build-up
            self._contract("2026-11-17", "PE", 25000, 90, 1300),   # short build-up
            self._contract("2026-11-17", "CE", 25100, 110, 800),  # short covering
            self._contract("2026-11-17", "PE", 25100, 90, 700),   # long unwinding
        ]
        archive = {"records": [
            {"date": "2026-11-12", "option_contracts": {"NIFTY": {"contracts": old}}},
            {"date": "2026-11-13", "option_contracts": {"NIFTY": {"contracts": new}}},
        ]}
        result = build_option_buildup_diagnostic(
            archive, "NIFTY", as_of_date="2026-11-13", min_matched_contracts=4
        )
        self.assertTrue(result["available"])
        self.assertEqual(result["categories"]["long_build_up"]["oi_quantity"], 200)
        self.assertEqual(result["categories"]["short_build_up"]["oi_quantity"], 300)
        self.assertEqual(result["categories"]["short_covering"]["oi_quantity"], 200)
        self.assertEqual(result["categories"]["long_unwinding"]["oi_quantity"], 300)
        self.assertEqual(result["classified_contracts"], 4)
        self.assertFalse(result["included_in_asset_final"])

    def test_does_not_match_different_expiry_or_strike(self):
        archive = {"records": [
            {"date": "2026-11-12", "option_contracts": {"NIFTY": {"contracts": [
                self._contract("2026-11-17", "CE", 25000, 100, 1000)
            ]}}},
            {"date": "2026-11-13", "option_contracts": {"NIFTY": {"contracts": [
                self._contract("2026-11-24", "CE", 25000, 110, 1200)
            ]}}},
        ]}
        result = build_option_buildup_diagnostic(
            archive, "NIFTY", as_of_date="2026-11-13", min_matched_contracts=1
        )
        self.assertFalse(result["available"])
        self.assertEqual(result["matched_contracts"], 0)

    def test_unavailable_when_archive_stale_or_insufficient(self):
        archive = {"records": [
            {"date": "2026-11-06", "option_contracts": {"BANKNIFTY": {"contracts": [
                self._contract("2026-11-23", "PE", 58000, 100, 1000)
            ]}}},
            {"date": "2026-11-09", "option_contracts": {"BANKNIFTY": {"contracts": [
                self._contract("2026-11-23", "PE", 58000, 110, 1200)
            ]}}},
        ]}
        stale = build_option_buildup_diagnostic(
            archive, "BANKNIFTY", as_of_date="2026-11-13", max_age_days=3,
            min_matched_contracts=1
        )
        self.assertFalse(stale["available"])
        insufficient = build_option_buildup_diagnostic(
            archive, "BANKNIFTY", as_of_date="2026-11-09", min_matched_contracts=20
        )
        self.assertFalse(insufficient["available"])

    def test_unchanged_price_or_oi_is_not_classified(self):
        rows = [
            self._contract("2026-11-17", "CE", 25000, 100, 1000),
            self._contract("2026-11-17", "PE", 25000, 100, 1000),
        ]
        changed = [
            self._contract("2026-11-17", "CE", 10000, 110, 1200),
            self._contract("2026-11-17", "PE", 25000, 110, 1000),
        ]
        archive = {"records": [
            {"date": "2026-11-12", "option_contracts": {"NIFTY": {"contracts": rows}}},
            {"date": "2026-11-13", "option_contracts": {"NIFTY": {"contracts": changed}}},
        ]}
        result = build_option_buildup_diagnostic(
            archive, "NIFTY", as_of_date="2026-11-13", min_matched_contracts=1
        )
        self.assertFalse(result["available"])
        self.assertEqual(result["classified_contracts"], 0)


if __name__ == "__main__":
    unittest.main()
