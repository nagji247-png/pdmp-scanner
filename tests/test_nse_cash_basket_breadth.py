import unittest

from nse_cash_basket_breadth import calculate_breadth


class CashBasketBreadthTests(unittest.TestCase):
    def setUp(self):
        self.rosters = {
            "NIFTY": {
                "as_of": "2026-11-06", "source_url": "https://www.nseindia.com/content/indices/ind_nifty50list.csv",
                "expected_count": 2,
                "members": [
                    {"symbol": "AAA", "isin": "ISINAAA"},
                    {"symbol": "BBB", "isin": "ISINBBB"},
                ],
            }
        }
        self.archive = {"records": [{
            "date": "2026-11-06",
            "equity_rows": [
                {"symbol": "AAA", "isin": "ISINAAA", "close": 110, "previous_close": 100},
                {"symbol": "BBB", "isin": "ISINBBB", "close": 90, "previous_close": 100},
            ],
        }]}

    def test_complete_breadth_has_separate_advance_decline_and_score(self):
        result = calculate_breadth(self.archive, self.rosters, "NIFTY", "2026-11-06")
        self.assertEqual(result["status"], "complete_diagnostic")
        self.assertEqual((result["advances"], result["declines"], result["unchanged"]), (1, 1, 0))
        self.assertEqual(result["score"], 0)
        self.assertFalse(result["score_eligible"])
        self.assertEqual(
            [(row["symbol"], row["change_pct"]) for row in result["constituents"]],
            [("AAA", 10.0), ("BBB", -10.0)],
        )
        self.assertEqual(result["constituents"][0]["close"], 110.0)

    def test_missing_member_withholds_score_instead_of_treating_as_zero(self):
        self.archive["records"][0]["equity_rows"].pop()
        result = calculate_breadth(self.archive, self.rosters, "NIFTY", "2026-11-06")
        self.assertEqual(result["status"], "withheld_incomplete")
        self.assertIsNone(result["score"])
        self.assertEqual(result["missing_symbols"], ["BBB"])

    def test_isin_mismatch_is_missing_not_a_match(self):
        self.archive["records"][0]["equity_rows"][0]["isin"] = "WRONG"
        result = calculate_breadth(self.archive, self.rosters, "NIFTY", "2026-11-06")
        self.assertEqual(result["matched"], 1)
        self.assertEqual(result["score"], None)


    def test_constituent_count_is_roster_driven_not_hardcoded(self):
        members = [{"symbol": f"BANK{i:02d}", "isin": f"ISIN{i:02d}"} for i in range(14)]
        rows = [
            {"symbol": f"BANK{i:02d}", "isin": f"ISIN{i:02d}", "close": 101, "previous_close": 100}
            for i in range(14)
        ]
        rosters = {"BANKNIFTY": {
            "as_of": "2026-11-06",
            "source_url": "https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-bank",
            "expected_count": 14,
            "members": members,
        }}
        archive = {"records": [{"date": "2026-11-06", "equity_rows": rows}]}
        result = calculate_breadth(archive, rosters, "BANKNIFTY", "2026-11-06")
        self.assertEqual(result["status"], "complete_diagnostic")
        self.assertEqual(result["matched"], 14)
        self.assertEqual(result["score"], 10)
        self.assertFalse(result["score_eligible"])

    def test_invalid_price_is_withheld_instead_of_crashing(self):
        self.archive["records"][0]["equity_rows"][0]["close"] = "not-a-price"
        result = calculate_breadth(self.archive, self.rosters, "NIFTY", "2026-11-06")
        self.assertEqual(result["status"], "withheld_incomplete")
        self.assertIsNone(result["score"])
        self.assertEqual(result["missing_symbols"], ["AAA"])

    def test_non_finite_price_is_withheld(self):
        self.archive["records"][0]["equity_rows"][0]["close"] = float("nan")
        result = calculate_breadth(self.archive, self.rosters, "NIFTY", "2026-11-06")
        self.assertEqual(result["status"], "withheld_incomplete")
        self.assertIsNone(result["score"])

    def test_missing_previous_close_is_withheld(self):
        del self.archive["records"][0]["equity_rows"][0]["previous_close"]
        result = calculate_breadth(self.archive, self.rosters, "NIFTY", "2026-11-06")
        self.assertEqual(result["status"], "withheld_incomplete")
        self.assertIsNone(result["score"])

    def test_stale_roster_is_withheld(self):
        self.rosters["NIFTY"]["as_of"] = "2026-01-01"
        with self.assertRaisesRegex(ValueError, "stale constituent roster"):
            calculate_breadth(self.archive, self.rosters, "NIFTY", "2026-11-06")

    def test_future_roster_is_rejected_for_historical_trade_date(self):
        self.rosters["NIFTY"]["as_of"] = "2026-11-07"
        with self.assertRaisesRegex(ValueError, "newer than requested trade date"):
            calculate_breadth(self.archive, self.rosters, "NIFTY", "2026-11-06")

    def test_non_official_roster_url_is_rejected(self):
        self.rosters["NIFTY"]["source_url"] = "https://example.com/nifty.csv"
        with self.assertRaisesRegex(ValueError, "non-official roster source"):
            calculate_breadth(self.archive, self.rosters, "NIFTY", "2026-11-06")

    def test_roster_count_and_provenance_are_mandatory(self):
        self.rosters["NIFTY"]["expected_count"] = 3
        with self.assertRaisesRegex(ValueError, "count mismatch"):
            calculate_breadth(self.archive, self.rosters, "NIFTY", "2026-11-06")

    def test_duplicate_isin_in_roster_is_rejected(self):
        self.rosters["NIFTY"]["members"][1]["isin"] = "ISINAAA"
        with self.assertRaisesRegex(ValueError, "ISIN missing or duplicate"):
            calculate_breadth(self.archive, self.rosters, "NIFTY", "2026-11-06")

    def test_http_official_looking_roster_url_is_rejected(self):
        self.rosters["NIFTY"]["source_url"] = "http://www.nseindia.com/content/indices/ind_nifty50list.csv"
        with self.assertRaisesRegex(ValueError, "non-official roster source"):
            calculate_breadth(self.archive, self.rosters, "NIFTY", "2026-11-06")


if __name__ == "__main__":
    unittest.main()
