import unittest

from index_oi_expiry_research import (
    summarize_index_futures_same_expiry,
    summarize_index_options_same_expiry,
)


class ExactExpiryIndexOIResearchTests(unittest.TestCase):
    def test_futures_compares_only_same_expiry_and_classifies_regime(self):
        payload = {"records": [
            {"date": "2026-11-05", "index_futures": {"NIFTY": {"by_expiry": {
                "2026-11-26": {"open_interest": 100, "close": 25000},
                "2026-12-31": {"open_interest": 500, "close": 25100},
            }}}},
            {"date": "2026-11-06", "index_futures": {"NIFTY": {"by_expiry": {
                "2026-11-26": {"open_interest": 120, "close": 25100},
                "2027-01-28": {"open_interest": 900, "close": 25200},
            }}}},
        ]}
        result = summarize_index_futures_same_expiry(payload)["NIFTY"]
        self.assertEqual(result["same_expiry_observations"], 1)
        self.assertEqual(result["observations"][0]["expiry"], "2026-11-26")
        self.assertEqual(result["observations"][0]["regime"], "long_buildup")
        self.assertIsNone(result["score"])
        self.assertFalse(result["included_in_asset_final"])

    def test_options_keep_ce_and_pe_separate(self):
        payload = {"records": [
            {"date": "2026-11-05", "symbols": {"NIFTY": {"by_expiry": {
                "2026-11-26": {"CE": {"open_interest": 100}, "PE": {"open_interest": 200}}
            }}}},
            {"date": "2026-11-06", "symbols": {"NIFTY": {"by_expiry": {
                "2026-11-26": {"CE": {"open_interest": 130}, "PE": {"open_interest": 180}}
            }}}},
        ]}
        result = summarize_index_options_same_expiry(payload)["NIFTY"]
        self.assertEqual(result["observations"][0]["sides"]["CE"]["oi_change"], 30)
        self.assertEqual(result["observations"][0]["sides"]["PE"]["oi_change"], -20)
        self.assertIsNone(result["score"])

    def test_gap_over_five_days_is_not_paired(self):
        payload = {"records": [
            {"date": "2026-11-02", "index_futures": {"NIFTY": {"by_expiry": {
                "2026-11-26": {"open_interest": 100, "close": 25000}
            }}}},
            {"date": "2026-11-09", "index_futures": {"NIFTY": {"by_expiry": {
                "2026-11-26": {"open_interest": 120, "close": 25100}
            }}}},
        ]}
        result = summarize_index_futures_same_expiry(payload)["NIFTY"]
        self.assertEqual(result["same_expiry_observations"], 0)


if __name__ == "__main__":
    unittest.main()
