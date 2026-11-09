import unittest

from nse_cash_basket_breadth import calculate_three_index_baskets


TRADE_DATE = "2026-11-06"


def make_bundle():
    specs = {
        "NIFTY": (50, "https://www.nseindia.com/content/indices/ind_nifty50list.csv"),
        "BANKNIFTY": (14, "https://www.niftyindices.com/IndexConstituent/ind_niftybanklist.csv"),
        "SENSEX": (30, "https://www.bseindices.com/constituents/code/16"),
    }
    bundle = {}
    archives = {}
    for index, (count, source_url) in specs.items():
        members = [
            {"symbol": f"{index}{i:02d}", "isin": f"INE{index[:2]}{i:07d}"}
            for i in range(count)
        ]
        bundle[index] = {
            "as_of": TRADE_DATE,
            "source_url": source_url,
            "expected_count": count,
            "members": members,
        }
        archives[index] = {
            "records": [{
                "date": TRADE_DATE,
                "equity_rows": [
                    {
                        "symbol": member["symbol"],
                        "isin": member["isin"],
                        "close": 101.0 if i % 2 == 0 else 99.0,
                        "previous_close": 100.0,
                    }
                    for i, member in enumerate(members)
                ],
            }]
        }
    return bundle, archives


class ThreeIndexCashBasketTests(unittest.TestCase):
    def test_all_three_full_rosters_and_cash_archives_complete(self):
        bundle, archives = make_bundle()
        result = calculate_three_index_baskets(archives, bundle, TRADE_DATE)
        self.assertTrue(result["all_three_complete"])
        self.assertEqual(result["status"], "complete_diagnostic")
        self.assertEqual(result["indices"]["NIFTY"]["matched"], 50)
        self.assertEqual(result["indices"]["BANKNIFTY"]["matched"], 14)
        self.assertEqual(result["indices"]["SENSEX"]["matched"], 30)
        self.assertFalse(result["score_eligible"])
        self.assertTrue(all(x["score"] is not None for x in result["indices"].values()))

    def test_missing_cash_archive_withholds_only_that_index(self):
        bundle, archives = make_bundle()
        del archives["SENSEX"]
        result = calculate_three_index_baskets(archives, bundle, TRADE_DATE)
        self.assertFalse(result["all_three_complete"])
        self.assertEqual(result["indices"]["SENSEX"]["status"], "withheld_unverified")
        self.assertIsNone(result["indices"]["SENSEX"]["score"])
        self.assertEqual(result["indices"]["NIFTY"]["status"], "complete_diagnostic")

    def test_wrong_official_member_count_is_withheld(self):
        bundle, archives = make_bundle()
        bundle["BANKNIFTY"]["expected_count"] = 12
        result = calculate_three_index_baskets(archives, bundle, TRADE_DATE)
        self.assertEqual(result["indices"]["BANKNIFTY"]["status"], "withheld_unverified")
        self.assertIsNone(result["indices"]["BANKNIFTY"]["score"])

    def test_incomplete_member_coverage_never_becomes_zero_score(self):
        bundle, archives = make_bundle()
        archives["NIFTY"]["records"][0]["equity_rows"].pop()
        result = calculate_three_index_baskets(archives, bundle, TRADE_DATE)
        nifty = result["indices"]["NIFTY"]
        self.assertEqual(nifty["status"], "withheld_incomplete")
        self.assertIsNone(nifty["score"])
        self.assertEqual(nifty["matched"], 49)
        self.assertFalse(result["all_three_complete"])

    def test_isin_mismatch_withholds_index_score(self):
        bundle, archives = make_bundle()
        archives["SENSEX"]["records"][0]["equity_rows"][0]["isin"] = "WRONGISIN"
        result = calculate_three_index_baskets(archives, bundle, TRADE_DATE)
        sensex = result["indices"]["SENSEX"]
        self.assertEqual(sensex["status"], "withheld_incomplete")
        self.assertIsNone(sensex["score"])
        self.assertEqual(sensex["matched"], 29)


if __name__ == "__main__":
    unittest.main()
