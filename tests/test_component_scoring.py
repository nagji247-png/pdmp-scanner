import copy
import json
import math
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from component_scoring import (
    DEFAULT_COMPONENT_WEIGHTS,
    build_component,
    clamp_score,
    client_oi_context,
    combine_components,
    is_fresh_timestamp,
    search_component_from_snapshot,
)


class ComponentScoringTests(unittest.TestCase):
    def test_score_is_clamped_to_minus_ten_plus_ten(self):
        self.assertEqual(clamp_score(15), 10.0)
        self.assertEqual(clamp_score(-15), -10.0)
        self.assertEqual(clamp_score(3.25), 3.25)
        self.assertIsNone(clamp_score(None))
        self.assertIsNone(clamp_score(float("nan")))
        self.assertIsNone(clamp_score(float("inf")))

    def test_missing_component_is_omitted_not_zero_filled(self):
        components = {
            "news": build_component(6.0, "Google News RSS", "2026-11-05", 40),
            "search": None,
            "eod_oi": {"score": None, "source": "NSE", "source_date": "2026-11-05", "weight": 20},
        }
        final = combine_components(components, DEFAULT_COMPONENT_WEIGHTS)
        self.assertEqual(final["score"], 6.0)
        self.assertEqual(final["included_components"], ["news"])
        self.assertEqual(final["normalized_weights_pct"], {"news": 100.0})
        self.assertNotIn("search", final["included_components"])
        self.assertNotIn("eod_oi", final["included_components"])

    def test_denominator_uses_only_included_component_weights(self):
        components = {
            "news": build_component(10, "Google News RSS", "2026-11-05", 40),
            "search": build_component(-10, "Google Trends", "2026-11-05", 40),
            "eod_oi": build_component(0, "NSE option chain", "2026-11-05", 20),
        }
        final = combine_components(components, DEFAULT_COMPONENT_WEIGHTS)
        self.assertEqual(final["score"], 0.0)
        self.assertEqual(final["weight_total"], 100.0)
        self.assertEqual(final["normalized_weights_pct"], {
            "news": 40.0, "search": 40.0, "eod_oi": 20.0
        })

        without_oi = combine_components(
            {"news": components["news"], "search": components["search"], "eod_oi": None},
            DEFAULT_COMPONENT_WEIGHTS,
        )
        self.assertEqual(without_oi["score"], 0.0)
        self.assertEqual(without_oi["normalized_weights_pct"], {
            "news": 50.0, "search": 50.0
        })

    def test_stale_timestamp_is_rejected(self):
        now = datetime(2026, 11, 6, 2, 0, tzinfo=timezone.utc)
        self.assertTrue(is_fresh_timestamp("2026-11-06T01:00:00Z", now, 360))
        self.assertFalse(is_fresh_timestamp("2026-11-05T18:00:00Z", now, 360))
        snapshot = {
            "valid": True,
            "timeframe": "now 1-d",
            "source": "Google Trends related_queries · India",
            "source_data_time": "2026-11-05T18:00:00Z",
            "seed": "nifty",
            "neutral_aware_score": 4.0,
            "directional_bull_pct": 50.0,
        }
        component, reason = search_component_from_snapshot(
            snapshot, now_utc=now, max_age_minutes=360
        )
        self.assertIsNone(component)
        self.assertIn("stale", reason)

    def test_search_source_date_uses_ist_calendar_day(self):
        snapshot = {
            "valid": True,
            "timeframe": "now 1-d",
            "source": "Google Trends related_queries · India",
            "source_data_time": "2026-11-06T01:40:00Z",
            "seed": "nifty",
            "neutral_aware_score": 4.0,
            "directional_bull_pct": 50.0,
        }
        component, reason = search_component_from_snapshot(
            snapshot,
            now_utc=datetime(2026, 11, 6, 2, 0, tzinfo=timezone.utc),
        )
        self.assertIsNone(reason)
        self.assertEqual(component["source_date"], "2026-11-06")

    def test_asset_search_reading_older_than_two_hours_is_stale(self):
        now = datetime(2026, 11, 6, 2, 0, tzinfo=timezone.utc)
        snapshot = {
            "valid": True,
            "timeframe": "now 1-d",
            "source": "Google Trends related_queries · India",
            "source_data_time": "2026-11-06T00:00:00Z",
            "seed": "sensex",
            "neutral_aware_score": 5.0,
            "directional_bull_pct": 50.0,
        }
        component, reason = search_component_from_snapshot(
            snapshot, now_utc=now, max_age_minutes=120
        )
        self.assertIsNotNone(component)
        self.assertIsNone(reason)

        snapshot["source_data_time"] = "2026-11-05T23:59:00Z"
        component, reason = search_component_from_snapshot(
            snapshot, now_utc=now, max_age_minutes=120
        )
        self.assertIsNone(component)
        self.assertIn("stale", reason)

    def test_seven_day_fallback_never_enters_search_score(self):
        snapshot = {
            "valid": True,
            "timeframe": "now 7-d",
            "source": "Google Trends related_queries · India",
            "source_data_time": "2026-11-06T01:00:00Z",
            "seed": "nifty",
            "neutral_aware_score": 8.0,
            "directional_bull_pct": 50.0,
        }
        component, reason = search_component_from_snapshot(
            snapshot,
            now_utc=datetime(2026, 11, 6, 2, 0, tzinfo=timezone.utc),
        )
        self.assertIsNone(component)
        self.assertIn("now 1-d", reason)

    def test_trends_classifier_requires_directional_or_explicit_flat_mood(self):
        import fetch_and_score

        directional = {
            "Nifty breakout today": "bull",
            "share market teji": "bull",
            "निफ्टी ऊपर": "bull",
            "बाजार में तेजी": "bull",
            "market crash": "bear",
            "निफ्टी नीचे": "bear",
            "गिरावट": "bear",
            "Nifty sideways": "neutral",
            "बाजार सपाट": "neutral",
        }
        for phrase, expected in directional.items():
            with self.subTest(phrase=phrase):
                self.assertEqual(fetch_and_score.tq_dir(phrase), expected)

        for phrase in ("Nifty 50 today", "Sensex live", "share market news",
                       "option chain", "Nifty prediction"):
            with self.subTest(phrase=phrase):
                self.assertIsNone(fetch_and_score.tq_dir(phrase))

    def test_gold_generic_price_search_is_not_neutral_sentiment(self):
        import fetch_and_score

        self.assertIsNone(fetch_and_score._asset_search_direction("gold price", "GOLD"))
        self.assertIsNone(fetch_and_score._asset_search_direction("silver rate", "SILVER"))
        self.assertEqual(fetch_and_score._asset_search_direction("gold price today", "GOLD"), "neutral")
        self.assertEqual(fetch_and_score._asset_search_direction("gold sideways", "GOLD"), "neutral")

    def test_asset_specific_information_queries_are_neutral_without_cross_asset_leakage(self):
        import fetch_and_score

        cases = [
            ("Nifty 50 today", "NIFTY", "neutral"),
            ("gift nifty live", "NIFTY", "neutral"),
            ("Sensex today", "SENSEX", "neutral"),
            ("Bank Nifty live", "BANKNIFTY", "neutral"),
            ("gold price today", "GOLD", "neutral"),
            ("silver price today", "SILVER", "neutral"),
        ]
        for phrase, asset, expected in cases:
            with self.subTest(phrase=phrase, asset=asset):
                self.assertEqual(
                    fetch_and_score._asset_search_direction(phrase, asset), expected
                )

        self.assertIsNone(fetch_and_score._asset_search_direction("Sensex today", "NIFTY"))
        self.assertIsNone(fetch_and_score._asset_search_direction("Bank Nifty live", "NIFTY"))
        self.assertIsNone(fetch_and_score._asset_search_direction("silver price today", "GOLD"))
        self.assertIsNone(fetch_and_score._asset_search_direction("gold price today", "SILVER"))
        self.assertIsNone(fetch_and_score._asset_search_direction("gold price", "GOLD"))

    def test_neutral_only_trends_is_not_added_as_zero_final_component(self):
        snapshot = {
            "valid": True,
            "timeframe": "now 1-d",
            "source": "Google Trends related_queries · India",
            "source_data_time": "2026-11-06T01:40:00Z",
            "seed": "sensex",
            "neutral_aware_score": 0.0,
            "directional_bull_pct": None,
            "bull_pct": 0.0,
            "bear_pct": 0.0,
            "neutral_pct": 100.0,
        }
        component, reason = search_component_from_snapshot(
            snapshot,
            now_utc=datetime(2026, 11, 6, 2, 0, tzinfo=timezone.utc),
        )
        self.assertIsNone(component)
        self.assertIn("directional evidence", reason)

    def test_shadow_news_score_does_not_use_fivefold_amplifier(self):
        import fetch_and_score

        headlines = [
            {"score": 2, "source": "Unknown Publisher", "age_h": 1},
            {"score": 3, "source": "Unknown Publisher", "age_h": 1},
        ]
        self.assertEqual(fetch_and_score.weighted_score(headlines), 12.5)
        self.assertEqual(fetch_and_score.shadow_weighted_news_score(headlines), 2.5)

    def test_four_client_long_short_changes_are_kept_separate(self):
        today = {
            "ok": True,
            "stale": False,
            "date": "2026-11-05",
            "source": "NSE official participant-wise OI",
        }
        changes = {
            "ok": True,
            "prev_date": "2026-11-04",
            "by_group": {
                "CLIENT": {
                    "index_call_long": 101,
                    "index_call_short": -202,
                    "index_put_long": 303,
                    "index_put_short": -404,
                    "future_index_long": 505,
                    "future_index_short": -606,
                }
            },
        }
        context = client_oi_context(today, changes)
        self.assertTrue(context["available"])
        self.assertEqual(context["ce_build_up"]["call_long_change"], 101)
        self.assertEqual(context["ce_build_up"]["call_short_change"], -202)
        self.assertEqual(context["pe_build_up"]["put_long_change"], 303)
        self.assertEqual(context["pe_build_up"]["put_short_change"], -404)
        self.assertEqual(context["client_index_futures"]["long_change"], 505)
        self.assertEqual(context["client_index_futures"]["short_change"], -606)

    def test_participant_scope_is_market_wide_not_symbol_specific(self):
        context = client_oi_context(
            {"ok": True, "stale": False, "date": "2026-11-05"},
            {
                "ok": True,
                "prev_date": "2026-11-04",
                "by_group": {"CLIENT": {"index_call_long": 1, "index_call_short": 2}},
            },
        )
        self.assertIn("market-wide", context["scope"])
        self.assertIn("not index-specific", context["scope"])
        self.assertFalse(context["included_in_asset_final"])

    def test_current_data_json_and_dashboard_contract(self):
        data_path = Path("data.json")
        dashboard_path = Path("dashboard.html")
        self.assertTrue(data_path.exists(), "current data.json fixture must be present")
        self.assertTrue(dashboard_path.exists(), "dashboard.html must be present")
        data = json.loads(data_path.read_text(encoding="utf-8"))
        self.assertIsInstance(data.get("instruments"), dict)

        import fetch_and_score

        instruments = copy.deepcopy(data["instruments"])
        original_scores = {
            name: item.get("score") for name, item in instruments.items()
        }
        try:
            snapshot_time = datetime.fromisoformat(
                str(data["updated"]).replace("Z", "+00:00")
            )
        except ValueError:
            snapshot_time = datetime.now(timezone.utc)
        fetch_and_score.build_asset_component_breakdowns(
            instruments,
            data.get("updated"),
            snapshot_time,
            data.get("participant_oi"),
            (data.get("participant_oi") or {}).get("changes"),
        )
        ist_date = snapshot_time.astimezone(
            timezone(timedelta(hours=5, minutes=30))
        ).date().isoformat()

        for name, item in instruments.items():
            self.assertEqual(item.get("score"), original_scores[name])
            breakdown = item.get("component_breakdown")
            self.assertIsInstance(breakdown, dict)
            json.dumps(breakdown, ensure_ascii=False, allow_nan=False)
            if "news" in (breakdown.get("components") or {}):
                self.assertEqual(breakdown["components"]["news"]["source_date"], ist_date)
            for component in (breakdown.get("components") or {}).values():
                self.assertGreaterEqual(component["score"], -10)
                self.assertLessEqual(component["score"], 10)
                self.assertTrue(component.get("source"))
                self.assertTrue(component.get("source_date"))
            final = breakdown.get("final") or {}
            if final.get("score") is not None:
                self.assertAlmostEqual(
                    sum((final.get("normalized_weights_pct") or {}).values()),
                    100.0,
                    places=1,
                )

        for name in ("NIFTY", "SENSEX", "BANKNIFTY"):
            breakdown = instruments[name]["component_breakdown"]
            self.assertNotIn("client", breakdown["components"])
            self.assertFalse(
                breakdown["client_market_context"]["included_in_asset_final"]
            )
            self.assertIn("not index-specific", breakdown["client_market_context"]["scope"])

        html = dashboard_path.read_text(encoding="utf-8")
        self.assertIn("function renderComponentBreakdown", html)
        self.assertIn("${componentBreakdown}", html)


if __name__ == "__main__":
    unittest.main()
