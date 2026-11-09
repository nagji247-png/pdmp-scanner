import unittest

from fetch_and_score import load_latest_stock_basket_diagnostics


def row(date, index, score, *, status="complete_diagnostic", matched=50,
        expected=50, coverage=100.0, research_only=True, score_eligible=False):
    return {
        "date": date,
        "indices": {
            index: {
                "status": status, "score": score, "matched": matched,
                "expected": expected, "coverage_pct": coverage,
                "advances": 45, "declines": 5, "unchanged": 0,
                "research_only": research_only,
                "score_eligible": score_eligible,
            }
        },
    }


class StockBasketDisplaySnapshotTests(unittest.TestCase):
    def test_latest_complete_diagnostic_is_available_for_display_only(self):
        archive = {"records": [
            row("2026-11-05", "NIFTY", 4.0),
            row("2026-11-06", "NIFTY", 8.0),
        ]}
        result = load_latest_stock_basket_diagnostics("2026-11-09", archive)
        self.assertEqual(result["NIFTY"]["score"], 8.0)
        self.assertEqual(result["NIFTY"]["source_date"], "2026-11-06")
        self.assertTrue(result["NIFTY"]["research_only"])
        self.assertFalse(result["NIFTY"]["score_eligible"])
        self.assertFalse(result["NIFTY"]["included"])

    def test_complete_member_detail_is_carried_to_dashboard_diagnostic(self):
        members = [{
            "symbol": "AAA", "instrument_id": "", "isin": "ISINAAA",
            "close": 110.0, "previous_close": 100.0,
            "change_pct": 10.0, "volume": 12345,
        }]
        archive = {"records": [{
            "date": "2026-11-06",
            "indices": {
                "NIFTY": {
                    "status": "complete_diagnostic", "score": 10.0,
                    "matched": 1, "expected": 1, "coverage_pct": 100.0,
                    "advances": 1, "declines": 0, "unchanged": 0,
                    "research_only": True, "score_eligible": False,
                    "constituents": members,
                }
            },
        }]}
        result = load_latest_stock_basket_diagnostics("2026-11-09", archive)
        self.assertEqual(result["NIFTY"]["constituents"], members)

    def test_incomplete_or_unvalidated_diagnostic_is_not_displayed_as_score(self):
        archive = {"records": [
            row("2026-11-06", "NIFTY", 8.0, matched=49),
            row("2026-11-05", "BANKNIFTY", 7.0, score_eligible=True),
        ]}
        result = load_latest_stock_basket_diagnostics("2026-11-09", archive)
        self.assertEqual(result, {})

    def test_future_diagnostic_is_not_used_for_earlier_scan(self):
        archive = {"records": [row("2026-11-10", "NIFTY", 8.0)]}
        result = load_latest_stock_basket_diagnostics("2026-11-09", archive)
        self.assertEqual(result, {})

    def test_each_index_uses_its_own_latest_complete_record(self):
        archive = {"records": [
            row("2026-11-05", "NIFTY", 5.0),
            row("2026-11-06", "NIFTY", 8.0),
            row("2026-11-05", "BANKNIFTY", -2.0),
        ]}
        result = load_latest_stock_basket_diagnostics("2026-11-09", archive)
        self.assertEqual(result["NIFTY"]["score"], 8.0)
        self.assertEqual(result["BANKNIFTY"]["score"], -2.0)


if __name__ == "__main__":
    unittest.main()
