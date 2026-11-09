import unittest

from evaluate_cash_basket_forward import evaluate_cash_basket


class CashBasketForwardEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.diagnostics = {"records": [{
            "date": "2026-11-06",
            "indices": {
                key: {"status": "complete_diagnostic", "score": score}
                for key, score in (("NIFTY", 8), ("BANKNIFTY", 4), ("SENSEX", 9))
            },
        }]}
        self.history = {"records": [
            {"date": "2026-11-06", "indices": {
                key: {"close": 100, "close_as_of": "06/11/2026"}
                for key in ("NIFTY", "BANKNIFTY", "SENSEX")
            }},
            {"date": "2026-11-09", "indices": {
                key: {"close": 102, "close_as_of": "2026-11-09"}
                for key in ("NIFTY", "BANKNIFTY", "SENSEX")
            }},
        ]}

    def test_pairs_breadth_with_next_captured_close_and_stays_research_only(self):
        result = evaluate_cash_basket(self.diagnostics, self.history, min_samples=2)
        nifty = result["indices"]["NIFTY"]
        self.assertEqual(nifty["sample_count"], 1)
        self.assertEqual(nifty["samples"][0]["next_captured_date"], "2026-11-09")
        self.assertEqual(nifty["samples"][0]["next_captured_return_pct"], 2.0)
        self.assertEqual(nifty["status"], "insufficient_sample")
        self.assertFalse(result["score_eligible"])
        self.assertFalse(result["production_mutation"])

    def test_missing_or_misdated_close_is_not_paired(self):
        self.history["records"][0]["indices"]["NIFTY"]["close_as_of"] = "2026-11-05"
        result = evaluate_cash_basket(self.diagnostics, self.history, min_samples=2)
        self.assertEqual(result["indices"]["NIFTY"]["sample_count"], 0)

    def test_missing_close_date_is_not_paired(self):
        del self.history["records"][0]["indices"]["NIFTY"]["close_as_of"]
        result = evaluate_cash_basket(self.diagnostics, self.history, min_samples=2)
        self.assertEqual(result["indices"]["NIFTY"]["sample_count"], 0)

    def test_explicitly_invalid_close_is_not_paired(self):
        self.history["records"][0]["indices"]["NIFTY"]["close_valid"] = False
        result = evaluate_cash_basket(self.diagnostics, self.history, min_samples=2)
        self.assertEqual(result["indices"]["NIFTY"]["sample_count"], 0)

    def test_incomplete_basket_is_excluded(self):
        self.diagnostics["records"][0]["indices"]["SENSEX"]["status"] = "withheld_incomplete"
        result = evaluate_cash_basket(self.diagnostics, self.history, min_samples=2)
        self.assertEqual(result["indices"]["SENSEX"]["sample_count"], 0)

    def test_zero_or_missing_next_close_is_excluded(self):
        self.history["records"][1]["indices"]["BANKNIFTY"]["close"] = 0
        result = evaluate_cash_basket(self.diagnostics, self.history, min_samples=2)
        self.assertEqual(result["indices"]["BANKNIFTY"]["sample_count"], 0)

    def test_default_gate_requires_60_paired_sessions(self):
        result = evaluate_cash_basket(self.diagnostics, self.history)
        self.assertEqual(result["minimum_samples_required"], 60)
        for metric in result["indices"].values():
            self.assertEqual(metric["status"], "insufficient_sample")

    def test_minimum_sample_count_is_enforced(self):
        with self.assertRaises(ValueError):
            evaluate_cash_basket(self.diagnostics, self.history, min_samples=1)


if __name__ == "__main__":
    unittest.main()
