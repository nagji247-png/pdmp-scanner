import unittest
from unittest import mock
from datetime import datetime, timezone

import fetch_and_score


class ComponentBreakdownIntegrationTests(unittest.TestCase):
    def test_optional_trends_phrase_diagnostics_are_off_by_default(self):
        seeds = {
            "NIFTY": "nifty", "SENSEX": "sensex", "BANKNIFTY": "bank nifty",
            "GOLD": "gold price", "SILVER": "silver price",
        }
        output = {}
        with mock.patch.object(
            fetch_and_score, "fetch_asset_directional_trends_diagnostics",
            side_effect=AssertionError("extra Trends calls must be opt-in"),
        ):
            result = fetch_and_score._attach_asset_directional_trends_diagnostics(
                output, seeds
            )
        self.assertEqual(set(result), set(seeds))
        self.assertTrue(all(
            item["directional_query_diagnostic"]["available"] is False
            for item in result.values()
        ))
        self.assertTrue(all(
            "अतिरिक्त Google Trends अनुरोध" in item["directional_query_diagnostic"]["reason"]
            for item in result.values()
        ))

    def test_optional_trends_phrase_diagnostics_can_be_enabled_explicitly(self):
        seeds = {"NIFTY": "nifty"}
        expected = {"NIFTY": {"available": True, "diagnostic_only": True}}
        with unittest.mock.patch.object(
            fetch_and_score, "fetch_asset_directional_trends_diagnostics",
            return_value=expected,
        ) as fetch:
            result = fetch_and_score._attach_asset_directional_trends_diagnostics(
                {}, seeds, enabled=True
            )
        fetch.assert_called_once_with()
        self.assertEqual(
            result["NIFTY"]["directional_query_diagnostic"], expected["NIFTY"]
        )

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
            # Reproduce the legacy bug: neutral-only snapshots must not carry a zero score.
            "neutral_aware_score": 0.0,
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
        self.assertIsNone(breakdown["search_diagnostic"]["directional_bull_pct"])
        self.assertEqual(instruments["NIFTY"]["score"], 1.0)

    def test_asset_search_classifier_blocks_cross_asset_and_bare_price_queries(self):
        classify = fetch_and_score._asset_search_direction
        self.assertIsNone(classify("gold price", "GOLD"))
        self.assertIsNone(classify("silver rate", "SILVER"))
        # Navigation / price lookup is informational, not neutral crowd mood.
        self.assertIsNone(classify("gold price today", "GOLD"))
        self.assertIsNone(classify("Nifty live", "NIFTY"))
        self.assertIsNone(classify("Nifty share price", "NIFTY"))
        self.assertEqual(classify("Nifty sideways today", "NIFTY"), "neutral")
        self.assertEqual(classify("Nifty rangebound", "NIFTY"), "neutral")
        self.assertIsNone(classify("Nifty range", "NIFTY"))
        self.assertIsNone(classify("Nifty trading range today", "NIFTY"))
        self.assertEqual(classify("Nifty स्थिर", "NIFTY"), "neutral")
        self.assertEqual(classify("Nifty breakout today", "NIFTY"), "bull")
        self.assertEqual(classify("Nifty crash", "NIFTY"), "bear")
        self.assertEqual(classify("Nifty price rise today", "NIFTY"), "bull")
        self.assertEqual(classify("Nifty price fall today", "NIFTY"), "bear")
        # Ambiguous analyst/navigation intent must not be promoted into mood.
        self.assertIsNone(classify("Nifty target today", "NIFTY"))
        self.assertEqual(classify("Nifty 52 week high", "NIFTY"), None)
        self.assertIsNone(classify("Nifty buy", "NIFTY"))
        self.assertIsNone(classify("Nifty not bullish", "NIFTY"))
        self.assertIsNone(classify("Nifty rally crash", "NIFTY"))
        self.assertIsNone(classify("Sensex today", "NIFTY"))
        self.assertIsNone(classify("silver price today", "GOLD"))

    def test_asset_directional_trends_phrase_diagnostic_is_not_a_score(self):
        import pandas as pd

        now = pd.Timestamp.now(tz="UTC")
        index = pd.date_range(end=now, periods=24, freq="h")
        frame = pd.DataFrame({
            "nifty": [100] * 24,
            "nifty breakout": [20] * 24,
            "nifty crash": [10] * 24,
            "nifty sideways": [5] * 24,
        }, index=index)
        spec = {
            "seed": "nifty",
            "bull": "nifty breakout",
            "bear": "nifty crash",
            "neutral": "nifty sideways",
        }
        result = fetch_and_score._summarize_asset_directional_trends(
            frame, "NIFTY", spec
        )
        self.assertTrue(result["available"])
        self.assertTrue(result["diagnostic_only"])
        self.assertEqual(result["query_interest_mix_pct"], {
            "bull": 57.1, "bear": 28.6, "neutral": 14.3
        })
        self.assertNotIn("score", result)
        self.assertIn("शामिल नहीं", result["interpretation"])

    def test_asset_directional_trends_rejects_zero_or_missing_data(self):
        import pandas as pd

        now = pd.Timestamp.now(tz="UTC").floor("h")
        index = pd.date_range(end=now, periods=24, freq="h")
        spec = {
            "seed": "gold price",
            "bull": "gold price rise",
            "bear": "gold price fall",
            "neutral": "gold price stable",
        }
        zero = pd.DataFrame({key: [0] * 24 for key in spec.values()}, index=index)
        with self.assertRaisesRegex(ValueError, "search-interest शून्य"):
            fetch_and_score._summarize_asset_directional_trends(zero, "GOLD", spec)
        missing = zero.drop(columns=["gold price fall"])
        with self.assertRaisesRegex(ValueError, "columns missing"):
            fetch_and_score._summarize_asset_directional_trends(missing, "GOLD", spec)

    def test_asset_directional_trends_are_scoped_to_each_asset(self):
        expected = {
            "NIFTY": "nifty breakout",
            "SENSEX": "sensex rally",
            "BANKNIFTY": "bank nifty breakout",
            "GOLD": "gold price rise",
            "SILVER": "silver price rise",
        }
        self.assertEqual(
            {asset: spec["bull"] for asset, spec in
             fetch_and_score.ASSET_DIRECTIONAL_TRENDS_QUERIES.items()},
            expected,
        )

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


    def test_client_market_wide_context_never_enters_any_index_final(self):
        instruments = {
            name: {"score": 1.25, "headlines": []}
            for name in ("NIFTY", "SENSEX", "BANKNIFTY")
        }
        participant_today = {
            "ok": True, "stale": False, "date": "2026-11-06",
            "source": "NSE official participant-wise OI",
        }
        participant_changes = {
            "ok": True, "prev_date": "2026-11-05",
            "by_group": {"CLIENT": {
                "index_call_long": 10, "index_call_short": -20,
                "index_put_long": 30, "index_put_short": -40,
                "future_index_long": 50, "future_index_short": -60,
            }},
        }
        fetch_and_score.build_asset_component_breakdowns(
            instruments,
            "2026-11-06T10:00:00Z",
            datetime(2026, 11, 6, 10, 0, tzinfo=timezone.utc),
            participant_today=participant_today,
            participant_changes_data=participant_changes,
        )
        for name, item in instruments.items():
            breakdown = item["component_breakdown"]
            context = breakdown["client_market_context"]
            self.assertTrue(context["available"])
            self.assertFalse(context["included_in_asset_final"])
            self.assertIn("not index-specific", context["scope"])
            self.assertEqual(context["ce_build_up"]["call_long_change"], 10)
            self.assertEqual(context["ce_build_up"]["call_short_change"], -20)
            self.assertEqual(context["pe_build_up"]["put_long_change"], 30)
            self.assertEqual(context["pe_build_up"]["put_short_change"], -40)
            self.assertEqual(context["client_index_futures"]["long_change"], 50)
            self.assertEqual(context["client_index_futures"]["short_change"], -60)
            self.assertEqual(breakdown["final"]["status"], "unavailable")
            self.assertEqual(breakdown["final"]["included_components"], [])
            self.assertEqual(item["score"], 1.25)


if __name__ == "__main__":
    unittest.main()
