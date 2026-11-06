import unittest
from datetime import datetime, timezone

import fetch_and_score


class ComponentBreakdownIntegrationTests(unittest.TestCase):
    def test_news_only_final_is_normalized_and_does_not_change_live_score(self):
        instruments = {
            "NIFTY": {
                "score": 3.5,
                "headline_score": 3.5,
                "news_query": "Nifty 50 India",
                "headlines": [{
                    "title": "Nifty rises on broad buying",
                    "source": "Reuters",
                    "score": 2.0,
                    "age_h": 1.0,
                    "published_at": "2026-11-06T06:00:00Z",
                }],
            }
        }
        fetch_and_score.build_asset_component_breakdowns(
            instruments,
            "2026-11-06T07:00:00Z",
            datetime(2026, 11, 6, 7, 0, tzinfo=timezone.utc),
        )
        item = instruments["NIFTY"]
        self.assertEqual(item["score"], 3.5)
        breakdown = item["component_breakdown"]
        self.assertEqual(breakdown["final"]["score"], 2.0)
        self.assertEqual(breakdown["final"]["normalized_weights_pct"], {"news": 100.0})
        self.assertEqual(
            breakdown["components"]["news"]["newest_headline_published_at"],
            "2026-11-06T06:00:00Z",
        )
        self.assertIn("search", breakdown["excluded_components"])
        self.assertNotIn("search", breakdown["components"])

    def test_neutral_only_asset_search_is_visible_but_not_scored(self):
        snapshot = {
            "valid": True,
            "scope": "asset_specific_google_related_queries_shadow",
            "seed": "nifty",
            "source": "Google Trends related_queries · India",
            "timeframe": "now 1-d",
            "source_data_time": "2026-11-06T06:30:00Z",
            "raw_queries": 7,
            "classified_queries": 7,
            "unclassified_queries": 0,
            "classification_coverage_pct": 100.0,
            "bull_pct": 0.0,
            "bear_pct": 0.0,
            "neutral_pct": 100.0,
            "directional_bull_pct": None,
            "terms": [{"term": "nifty today", "direction": "neutral", "weight": 100}],
        }
        instruments = {
            "NIFTY": {
                "score": 1.0,
                "headlines": [],
                "index_search_shadow": snapshot,
            }
        }
        fetch_and_score.build_asset_component_breakdowns(
            instruments,
            "2026-11-06T07:00:00Z",
            datetime(2026, 11, 6, 7, 0, tzinfo=timezone.utc),
        )
        breakdown = instruments["NIFTY"]["component_breakdown"]
        self.assertEqual(breakdown["search_diagnostic"]["neutral_pct"], 100.0)
        self.assertNotIn("search", breakdown["components"])
        self.assertIn("directional evidence", breakdown["excluded_components"]["search"]["reason"])
        self.assertEqual(instruments["NIFTY"]["score"], 1.0)

    def test_asset_search_classifier_blocks_cross_asset_and_bare_price_queries(self):
        classify = fetch_and_score._asset_search_direction
        self.assertIsNone(classify("gold price", "GOLD"))
        self.assertIsNone(classify("silver rate", "SILVER"))
        self.assertEqual(classify("gold price today", "GOLD"), "neutral")
        self.assertEqual(classify("Nifty breakout today", "NIFTY"), "bull")
        self.assertEqual(classify("Nifty crash", "NIFTY"), "bear")
        self.assertIsNone(classify("Sensex today", "NIFTY"))
        self.assertIsNone(classify("silver price today", "GOLD"))

    def test_mcx_bhavcopy_comparator_is_imported_for_diagnostic_workflow(self):
        from component_scoring import compare_mcx_bhavcopy_contract_oi

        self.assertIs(
            fetch_and_score.compare_mcx_bhavcopy_contract_oi,
            compare_mcx_bhavcopy_contract_oi,
        )
        current = [{
            "InstrumentName": "FUTCOM", "Symbol": "GOLD",
            "DateDisplay": "05 Nov 2026", "ExpiryDate": "04DEC2026",
            "OptionType": "-", "OpenInterest": 15716, "Close": 144095,
        }]
        previous = [{
            "InstrumentName": "FUTCOM", "Symbol": "GOLD",
            "DateDisplay": "04 Nov 2026", "ExpiryDate": "04DEC2026",
            "OptionType": "-", "OpenInterest": 16095, "Close": 143234,
        }]
        result = fetch_and_score.compare_mcx_bhavcopy_contract_oi(
            current, previous, "GOLD", "2026-11-05", "2026-11-04", "2026-12-04"
        )
        self.assertTrue(result["available"])
        self.assertEqual(result["change_in_oi_lots"], -379)
        self.assertEqual(result["change_in_close"], 861.0)
        self.assertFalse(result["included_in_asset_final"])


if __name__ == "__main__":
    unittest.main()
