import unittest

from fetch_and_score import load_latest_stock_basket_diagnostics


def metric(status="complete_diagnostic", score=2.0):
    return {
        "status": status, "score": score, "expected": 50, "matched": 50,
        "coverage_pct": 100.0, "research_only": True, "score_eligible": False,
        "advances": 30, "declines": 20, "unchanged": 0,
    }


def record(day, status="complete_diagnostic"):
    return {
        "date": day, "indices": {"NIFTY": metric(status)},
        "research_only": True, "score_eligible": False,
    }


class StockBasketLoaderFreshnessTests(unittest.TestCase):
    def test_before_eod_cutoff_uses_previous_session(self):
        archive = {"records": [record("2026-11-12")]}
        result = load_latest_stock_basket_diagnostics(
            "2026-11-13", archive=archive, scan_timestamp="2026-11-13T14:00:00Z"
        )
        self.assertEqual(result["NIFTY"]["source_date"], "2026-11-12")

    def test_after_eod_cutoff_never_falls_back_to_yesterdays_basket(self):
        archive = {"records": [
            record("2026-11-12"),
            record("2026-11-13", "withheld_incomplete"),
        ]}
        result = load_latest_stock_basket_diagnostics(
            "2026-11-13", archive=archive, scan_timestamp="2026-11-13T15:00:00Z"
        )
        self.assertEqual(result, {})

    def test_missing_expected_session_never_falls_back_to_older_record(self):
        archive = {"records": [record("2026-11-12")]}
        result = load_latest_stock_basket_diagnostics(
            "2026-11-13", archive=archive, scan_timestamp="2026-11-13T15:00:00Z"
        )
        self.assertEqual(result, {})


if __name__ == "__main__":
    unittest.main()
