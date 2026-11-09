import unittest
from unittest import mock
from datetime import datetime, timezone
from types import ModuleType

import fetch_and_score


class ComponentBreakdownIntegrationTests(unittest.TestCase):
    def test_global_trends_mood_percentages_use_real_three_way_group_weights(self):
        queries = {
            "a": {"term": "nifty breakout", "weight": 60, "rising": False},
            "b": {"term": "nifty correction", "weight": 20, "rising": False},
            "c": {"term": "nifty today", "weight": 20, "rising": False},
        }
        result = fetch_and_score.tq_aggregate(queries)
        self.assertEqual(result["crowd_bull_pct"], 75)
        self.assertEqual(result["bull_score_pct"], 60.0)
        self.assertEqual(result["bear_score_pct"], 20.0)
        self.assertEqual(result["neutral_score_pct"], 20.0)
        self.assertEqual(
            round(result["bull_score_pct"] + result["bear_score_pct"] + result["neutral_score_pct"], 1),
            100.0,
        )

    def test_asset_matched_information_searches_are_neutral(self):
        cases = [
            ("nifty today", "NIFTY"),
            ("nifty live price", "NIFTY"),
            ("sensex option chain", "SENSEX"),
            ("bank nifty prediction", "BANKNIFTY"),
            ("gold price today", "GOLD"),
            ("silver rate live", "SILVER"),
        ]
        for term, asset in cases:
            with self.subTest(term=term, asset=asset):
                self.assertEqual(fetch_and_score._asset_search_direction(term, asset), "neutral")

    def test_bare_price_only_searches_remain_unclassified(self):
        self.assertIsNone(fetch_and_score._asset_search_direction("gold price", "GOLD"))
        self.assertIsNone(fetch_and_score._asset_search_direction("silver rate", "SILVER"))

    def test_explicit_sideways_search_is_neutral(self):
        self.assertEqual(
            fetch_and_score._asset_search_direction("nifty sideways", "NIFTY"),
            "neutral",
        )

    def test_asset_directional_terms_remain_directional(self):
        self.assertEqual(
            fetch_and_score._asset_search_direction("nifty breakout", "NIFTY"),
            "bull",
        )
        self.assertEqual(
            fetch_and_score._asset_search_direction("gold price fall", "GOLD"),
            "bear",
        )

    def test_asset_search_classifier_covers_common_directional_english_and_hindi_queries(self):
        bullish = [
            ("nifty going up", "NIFTY"),
            ("nifty upside", "NIFTY"),
            ("sensex positive trend", "SENSEX"),
            ("bank nifty strong buying", "BANKNIFTY"),
            ("सोने में तेजी", "GOLD"),
            ("चांदी ऊपर जाएगी", "SILVER"),
            ("निफ्टी बढ़ने की उम्मीद", "NIFTY"),
        ]
        bearish = [
            ("nifty going down", "NIFTY"),
            ("sensex downside", "SENSEX"),
            ("bank nifty selling pressure", "BANKNIFTY"),
            ("सोने में कमजोरी", "GOLD"),
            ("चांदी नीचे जाएगी", "SILVER"),
            ("निफ्टी में गिरावट", "NIFTY"),
        ]
        for term, asset in bullish:
            with self.subTest(term=term, asset=asset):
                self.assertEqual(fetch_and_score._asset_search_direction(term, asset), "bull")
        for term, asset in bearish:
            with self.subTest(term=term, asset=asset):
                self.assertEqual(fetch_and_score._asset_search_direction(term, asset), "bear")

    def test_asset_search_classifier_rejects_negated_and_cross_asset_direction(self):
        self.assertIsNone(fetch_and_score._asset_search_direction("nifty नहीं बढ़ेगा", "NIFTY"))
        self.assertIsNone(fetch_and_score._asset_search_direction("sensex rally", "NIFTY"))
        self.assertIsNone(fetch_and_score._asset_search_direction("gold price rise", "SILVER"))

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

    def test_directional_phrase_diagnostics_return_three_way_mix_for_each_asset(self):
        from fetch_and_score import fetch_asset_directional_trends_diagnostics

        class FakeTrendReq:
            calls = []
            def __init__(self, **kwargs):
                pass
            def build_payload(self, terms, **kwargs):
                self.calls.append(list(terms))
                self.terms = list(terms)
            def interest_over_time(self):
                stamp = pd.Timestamp.now(tz="UTC")
                return pd.DataFrame(
                    {self.terms[0]: [100] * 24,
                     self.terms[1]: [60] * 24,
                     self.terms[2]: [30] * 24,
                     self.terms[3]: [10] * 24},
                    index=pd.date_range(end=stamp, periods=24, freq="h"),
                )

        request_module = ModuleType("pytrends.request")
        request_module.TrendReq = FakeTrendReq
        package_module = ModuleType("pytrends")
        package_module.request = request_module
        with mock.patch.dict("sys.modules", {
            "pytrends": package_module, "pytrends.request": request_module,
        }):
            result = fetch_asset_directional_trends_diagnostics()

        self.assertEqual(len(FakeTrendReq.calls), 5)
        self.assertEqual(set(result), {"NIFTY", "SENSEX", "BANKNIFTY", "GOLD", "SILVER"})
        for asset, item in result.items():
            with self.subTest(asset=asset):
                self.assertTrue(item["available"], item.get("reason"))
                self.assertEqual(item["query_interest_mix_pct"], {
                    "bull": 60.0, "bear": 30.0, "neutral": 10.0,
                })
                self.assertEqual(item["diagnostic_only"], True)

    def test_directional_phrase_diagnostics_stop_after_google_trends_429(self):
        from fetch_and_score import fetch_asset_directional_trends_diagnostics

        class FakeTrendReq:
            calls = 0
            def __init__(self, **kwargs):
                pass
            def build_payload(self, terms, **kwargs):
                FakeTrendReq.calls += 1
                if FakeTrendReq.calls == 2:
                    raise RuntimeError("429 Too Many Requests")
                self.terms = list(terms)
            def interest_over_time(self):
                stamp = pd.Timestamp.now(tz="UTC")
                return pd.DataFrame(
                    {self.terms[0]: [100] * 24,
                     self.terms[1]: [60] * 24,
                     self.terms[2]: [30] * 24,
                     self.terms[3]: [10] * 24},
                    index=pd.date_range(end=stamp, periods=24, freq="h"),
                )

        request_module = ModuleType("pytrends.request")
        request_module.TrendReq = FakeTrendReq
        package_module = ModuleType("pytrends")
        package_module.request = request_module
        with mock.patch.dict("sys.modules", {
            "pytrends": package_module, "pytrends.request": request_module,
        }):
            result = fetch_asset_directional_trends_diagnostics()

        self.assertEqual(FakeTrendReq.calls, 2)
        self.assertTrue(result["NIFTY"]["available"])
        self.assertFalse(result["SENSEX"]["available"])
        self.assertIn("rate limit", result["BANKNIFTY"]["reason"].lower())
        self.assertIn("rate limit", result["GOLD"]["reason"].lower())
        self.assertIn("rate limit", result["SILVER"]["reason"].lower())

    def test_asset_search_snapshots_are_saved_for_all_five_assets(self):
        now = datetime(2026, 11, 7, 13, 30, tzinfo=timezone.utc)
        seeds = {
            "NIFTY": "nifty", "SENSEX": "sensex", "BANKNIFTY": "bank nifty",
            "GOLD": "gold price", "SILVER": "silver price",
        }
        instruments = {name: {"score": 2.5} for name in seeds}
        fresh = {
            name: {
                "valid": True, "seed": seed, "timeframe": "now 1-d",
                "source_data_time": now.isoformat(), "production_score_used": False,
            }
            for name, seed in seeds.items()
        }
        fetch_and_score.attach_asset_search_snapshots(
            instruments, {}, now, fresh_results=fresh
        )
        for name, seed in seeds.items():
            field = ("index_search_shadow" if name in ("NIFTY", "SENSEX", "BANKNIFTY")
                     else "asset_search_shadow")
            self.assertEqual(instruments[name][field]["seed"], seed)
            self.assertTrue(instruments[name][field]["valid"])
            self.assertEqual(instruments[name]["score"], 2.5)

    def test_ordinary_scan_reuses_fresh_asset_search_without_refetching(self):
        now = datetime(2026, 11, 7, 13, 30, tzinfo=timezone.utc)
        seeds = {
            "NIFTY": "nifty", "SENSEX": "sensex", "BANKNIFTY": "bank nifty",
            "GOLD": "gold price", "SILVER": "silver price",
        }
        previous = {}
        instruments = {}
        for name, seed in seeds.items():
            field = ("index_search_shadow" if name in ("NIFTY", "SENSEX", "BANKNIFTY")
                     else "asset_search_shadow")
            previous[name] = {field: {
                "valid": True, "seed": seed, "timeframe": "now 1-d",
                "source_data_time": now.isoformat(),
            }}
            instruments[name] = {"score": 1.0}
        fetch_and_score.attach_asset_search_snapshots(
            instruments, previous, now, fresh_results=None
        )
        for name, seed in seeds.items():
            field = ("index_search_shadow" if name in ("NIFTY", "SENSEX", "BANKNIFTY")
                     else "asset_search_shadow")
            self.assertEqual(instruments[name][field]["seed"], seed)
            self.assertTrue(instruments[name][field]["cached"])

    def test_asset_search_cache_uses_six_hour_declared_freshness_window(self):
        now = datetime(2026, 11, 7, 13, 30, tzinfo=timezone.utc)
        instruments = {"NIFTY": {"score": 1.0}, "SENSEX": {"score": 2.0}}
        previous = {
            "NIFTY": {"index_search_shadow": {
                "valid": True, "seed": "nifty", "timeframe": "now 1-d",
                "source_data_time": "2026-11-07T08:30:00Z",
            }},
            "SENSEX": {"index_search_shadow": {
                "valid": True, "seed": "sensex", "timeframe": "now 1-d",
                "source_data_time": "2026-11-07T07:29:00Z",
            }},
        }
        fetch_and_score.attach_asset_search_snapshots(
            instruments, previous, now, fresh_results=None
        )
        self.assertTrue(instruments["NIFTY"]["index_search_shadow"]["valid"])
        self.assertTrue(instruments["NIFTY"]["index_search_shadow"]["cached"])
        self.assertFalse(instruments["SENSEX"]["index_search_shadow"]["valid"])
        self.assertIn("stale", instruments["SENSEX"]["index_search_shadow"]["reason"])

    def test_stale_asset_search_is_not_reused_by_ordinary_scan(self):
        now = datetime(2026, 11, 7, 13, 30, tzinfo=timezone.utc)
        instruments = {"NIFTY": {"score": 1.0}}
        previous = {"NIFTY": {"index_search_shadow": {
            "valid": True, "seed": "nifty", "timeframe": "now 1-d",
            "source_data_time": "2026-11-07T06:00:00Z",
        }}}
        fetch_and_score.attach_asset_search_snapshots(
            instruments, previous, now, fresh_results=None
        )
        snapshot = instruments["NIFTY"]["index_search_shadow"]
        self.assertFalse(snapshot["valid"])
        self.assertIn("stale", snapshot["reason"])

    def test_failed_refresh_preserves_only_still_fresh_asset_search_snapshot(self):
        now = datetime(2026, 11, 7, 13, 30, tzinfo=timezone.utc)
        instruments = {"NIFTY": {"score": 1.0}, "SENSEX": {"score": 2.0}}
        previous = {
            "NIFTY": {"index_search_shadow": {
                "valid": True, "seed": "nifty", "timeframe": "now 1-d",
                "source_data_time": "2026-11-07T12:45:00Z", "neutral_aware_score": 2.0,
            }},
            "SENSEX": {"index_search_shadow": {
                "valid": True, "seed": "sensex", "timeframe": "now 1-d",
                "source_data_time": "2026-11-07T06:00:00Z",
            }},
        }
        failed = {
            "NIFTY": {"valid": False, "seed": "nifty", "reason": "temporary Trends response error"},
            "SENSEX": {"valid": False, "seed": "sensex", "reason": "temporary Trends response error"},
        }
        fetch_and_score.attach_asset_search_snapshots(
            instruments, previous, now, fresh_results=failed
        )
        kept = instruments["NIFTY"]["index_search_shadow"]
        self.assertTrue(kept["valid"])
        self.assertTrue(kept["cached"])
        self.assertEqual(kept["source_data_time"], "2026-11-07T12:45:00Z")
        self.assertEqual(kept["refresh_error"], "temporary Trends response error")
        rejected = instruments["SENSEX"]["index_search_shadow"]
        self.assertFalse(rejected["valid"])
        self.assertIn("temporary Trends response error", rejected["reason"])

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

    def test_news_requires_real_publisher_timestamp_and_uses_headline_date(self):
        now = datetime(2026, 11, 7, 7, 0, tzinfo=timezone.utc)
        instruments = {
            "NIFTY": {
                "score": 4.0,
                "headlines": [
                    {"title": "Nifty rises on broad buying", "source": "Reuters",
                     "score": 2.0, "age_h": 1.0},
                    {"title": "Nifty gains after strong results", "source": "Bloomberg",
                     "score": 3.0, "age_h": 0.1,
                     "published_at": "2026-11-07T06:30:00Z"},
                ],
            }
        }
        fetch_and_score.build_asset_component_breakdowns(
            instruments, "2026-11-07T07:00:00Z", now
        )
        breakdown = instruments["NIFTY"]["component_breakdown"]
        news = breakdown["components"]["news"]
        self.assertEqual(news["evidence_count"], 1)
        self.assertEqual(news["source_date"], "2026-11-07")
        self.assertEqual(news["source_date_basis"],
                         "newest eligible publisher timestamp converted to IST; observed_at is scan time")
        self.assertEqual(news["newest_headline_published_at"], "2026-11-07T06:30:00Z")
        self.assertEqual(news["newest_headline_age_h"], 0.5)
        self.assertEqual(news["observed_at"], "2026-11-07T07:00:00Z")
        self.assertEqual(instruments["NIFTY"]["score"], 4.0)

    def test_each_asset_search_component_rejects_another_assets_seed(self):
        now = datetime(2026, 11, 6, 7, 0, tzinfo=timezone.utc)
        seeds = {
            "NIFTY": "nifty",
            "SENSEX": "sensex",
            "BANKNIFTY": "bank nifty",
            "GOLD": "gold price",
            "SILVER": "silver price",
        }
        instruments = {}
        for name, seed in seeds.items():
            instruments[name] = {
                "score": 0.0,
                "headlines": [],
                "index_search_shadow" if name in ("NIFTY", "SENSEX", "BANKNIFTY") else "asset_search_shadow": {
                    "valid": True,
                    "seed": seed,
                    "source": "Google Trends related_queries · India",
                    "timeframe": "now 1-d",
                    "source_data_time": now.isoformat(),
                    "bull_pct": 70.0,
                    "bear_pct": 20.0,
                    "neutral_pct": 10.0,
                    "directional_bull_pct": 77.8,
                    "neutral_aware_score": 5.0,
                    "classified_queries": 5,
                },
            }
        # Deliberately copy NIFTY's seed into SENSEX: it must never be scored.
        instruments["SENSEX"]["index_search_shadow"]["seed"] = "nifty"
        fetch_and_score.build_asset_component_breakdowns(
            instruments, now.isoformat(), now
        )
        for name in ("NIFTY", "BANKNIFTY", "GOLD", "SILVER"):
            self.assertEqual(
                instruments[name]["component_breakdown"]["components"]["search"]["seed"],
                seeds[name],
            )
        sensex = instruments["SENSEX"]["component_breakdown"]
        self.assertNotIn("search", sensex["components"])
        self.assertIn("seed mismatch", sensex["excluded_components"]["search"]["reason"])
        self.assertEqual(sensex["final"]["status"], "unavailable")

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
        # Bare price/rate queries remain unclassified; explicit index lookup intent is neutral, not directional.
        self.assertIsNone(classify("gold price", "GOLD"))
        self.assertIsNone(classify("silver rate", "SILVER"))
        self.assertEqual(classify("gold price today", "GOLD"), "neutral")
        self.assertEqual(classify("Nifty live", "NIFTY"), "neutral")
        self.assertEqual(classify("Nifty share price", "NIFTY"), "neutral")
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
        # Explicit record-price phrases are directional; bare high/low remain ambiguous.
        self.assertEqual(classify("Nifty all time high", "NIFTY"), "bull")
        self.assertEqual(classify("Sensex record high", "SENSEX"), "bull")
        self.assertEqual(classify("BankNifty new high", "BANKNIFTY"), "bull")
        self.assertEqual(classify("gold record high", "GOLD"), "bull")
        self.assertEqual(classify("silver all time low", "SILVER"), "bear")
        self.assertIsNone(classify("Nifty all time high crash", "NIFTY"))
        self.assertIsNone(classify("Nifty record low", "SENSEX"))
        self.assertIsNone(classify("Nifty buy", "NIFTY"))
        self.assertIsNone(classify("Nifty not bullish", "NIFTY"))
        self.assertIsNone(classify("Nifty rally crash", "NIFTY"))
        self.assertIsNone(classify("Sensex today", "NIFTY"))
        self.assertIsNone(classify("silver price today", "GOLD"))

        # Hindi asset names and sentiment phrases must be classified too.
        self.assertEqual(classify("निफ़्टी ऊपर", "NIFTY"), "bull")
        self.assertEqual(classify("निफ्टी में गिरावट", "NIFTY"), "bear")
        self.assertEqual(classify("बैंक निफ्टी में तेजी", "BANKNIFTY"), "bull")
        self.assertIsNone(classify("बैंक निफ्टी में तेजी", "NIFTY"))
        self.assertEqual(classify("BankNifty breakout", "BANKNIFTY"), "bull")
        self.assertEqual(classify("बैंकनिफ्टी में तेजी", "BANKNIFTY"), "bull")
        self.assertIsNone(classify("BankNifty breakout", "NIFTY"))
        self.assertEqual(classify("सेंसेक्स में उछाल", "SENSEX"), "bull")
        self.assertEqual(classify("सोने में तेजी", "GOLD"), "bull")
        self.assertEqual(classify("सोने में गिरावट", "GOLD"), "bear")
        self.assertEqual(classify("चाँदी में तेजी", "SILVER"), "bull")
        self.assertEqual(classify("चांदी में कमजोरी", "SILVER"), "bear")
        self.assertEqual(classify("सोने में कमज़ोरी", "GOLD"), "bear")
        self.assertIsNone(classify("चांदी में तेजी", "GOLD"))
        self.assertEqual(classify("गोल्ड में तेजी", "GOLD"), "bull")
        self.assertEqual(classify("सिल्वर में गिरावट", "SILVER"), "bear")
        self.assertEqual(classify("रजत में तेजी", "SILVER"), "bull")

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

    def test_nse_index_futures_comparator_is_exact_expiry_and_diagnostic_only(self):
        from component_scoring import compare_nse_udiff_index_futures_oi

        current = [{
            "Sgmt": "FO", "Src": "NSE", "FinInstrmTp": "FUTIDX",
            "TckrSymb": "NIFTY", "BizDt": "2026-11-06",
            "XpryDt": "2026-11-26", "OpnIntrst": 120000,
            "ChngInOpnIntrst": 1500, "ClsPric": 25100,
        }]
        previous = [{
            "Sgmt": "FO", "Src": "NSE", "FinInstrmTp": "FUTIDX",
            "TckrSymb": "NIFTY", "BizDt": "2026-11-05",
            "XpryDt": "2026-11-26", "OpnIntrst": 118000,
            "ChngInOpnIntrst": 900, "ClsPric": 25000,
        }]
        result = compare_nse_udiff_index_futures_oi(
            current, previous, "NIFTY", "2026-11-06", "2026-11-05", "2026-11-26"
        )
        self.assertTrue(result["available"])
        self.assertEqual(result["change_in_oi"], 2000)
        self.assertEqual(result["change_in_close"], 100.0)
        self.assertEqual(result["price_oi_regime"], "price_up_oi_up")
        self.assertFalse(result["included_in_asset_final"])
        self.assertFalse(result["coverage_validated"])

        # A different expiry cannot be silently substituted for the requested contract.
        wrong_expiry = [dict(current[0], XpryDt="2026-12-31")]
        rejected = compare_nse_udiff_index_futures_oi(
            wrong_expiry, previous, "NIFTY", "2026-11-06", "2026-11-05", "2026-11-26"
        )
        self.assertFalse(rejected["available"])
        self.assertIn("row_count_not_one", rejected["reason"])

        # Duplicate matching contracts are ambiguous and must fail closed.
        duplicated = current + [dict(current[0])]
        rejected_duplicate = compare_nse_udiff_index_futures_oi(
            duplicated, previous, "NIFTY", "2026-11-06", "2026-11-05", "2026-11-26"
        )
        self.assertFalse(rejected_duplicate["available"])

    def test_nse_index_futures_comparator_is_exposed_to_scan_module(self):
        from component_scoring import compare_nse_udiff_index_futures_oi

        self.assertIs(
            fetch_and_score.compare_nse_udiff_index_futures_oi,
            compare_nse_udiff_index_futures_oi,
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
            "participants": {"CLIENT": {
                "index_call_long": 110, "index_call_short": 180,
                "index_put_long": 330, "index_put_short": 360,
                "future_index_long": 550, "future_index_short": 540,
            }},
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
            evidence = context["evidence_components"]
            self.assertEqual(set(evidence), {
                "ce_long", "ce_short", "pe_long", "pe_short",
                "futures_long", "futures_short",
            })
            self.assertEqual(evidence["ce_long"]["change_pct_prior_gross"], 10.0)
            self.assertEqual(evidence["ce_short"]["change_pct_prior_gross"], -10.0)
            self.assertEqual(evidence["pe_long"]["change_pct_prior_gross"], 10.0)
            self.assertEqual(evidence["pe_short"]["change_pct_prior_gross"], -10.0)
            self.assertEqual(evidence["futures_long"]["change_pct_prior_gross"], 10.0)
            self.assertEqual(evidence["futures_short"]["change_pct_prior_gross"], -10.0)
            for evidence_item in evidence.values():
                self.assertEqual(evidence_item["source_date"], "2026-11-06")
                self.assertEqual(evidence_item["previous_source_date"], "2026-11-05")
                self.assertFalse(evidence_item["included_in_asset_final"])
                self.assertIsNone(evidence_item["score"])
            self.assertEqual(breakdown["final"]["status"], "unavailable")
            self.assertEqual(breakdown["final"]["included_components"], [])
            self.assertEqual(item["score"], 1.25)


    def test_partial_watchlist_never_enters_index_stock_basket_final(self):
        instruments = {
            name: {"score": 1.25, "headlines": []}
            for name in ("NIFTY", "SENSEX", "BANKNIFTY")
        }
        fetch_and_score.build_asset_component_breakdowns(
            instruments,
            "2026-11-06T10:00:00Z",
            datetime(2026, 11, 6, 10, 0, tzinfo=timezone.utc),
        )
        for name, item in instruments.items():
            breakdown = item["component_breakdown"]
            self.assertNotIn("stock_basket", breakdown["components"])
            excluded = breakdown["excluded_components"]["stock_basket"]
            self.assertTrue(excluded["applicable"])
            self.assertFalse(excluded["included"])
            self.assertIn("full-basket daily snapshot", excluded["reason"])
            self.assertIn("60-session directional validation", excluded["reason"])
            self.assertEqual(item["score"], 1.25)


    def test_sensex_component_exclusions_use_bse_not_nse_sources(self):
        now = datetime(2026, 11, 8, 6, 0, tzinfo=timezone.utc)
        instruments = {"SENSEX": {"score": 1.0, "headlines": []}}
        fetch_and_score.build_asset_component_breakdowns(
            instruments, "2026-11-08T06:00:00Z", now
        )
        excluded = instruments["SENSEX"]["component_breakdown"]["excluded_components"]
        self.assertEqual(
            excluded["eod_oi"]["source"],
            "BSE official SENSEX index-option EOD data",
        )
        self.assertIn("BSE", excluded["eod_oi"]["reason"])
        self.assertIn("NSE UDiFF में NIFTY/BANKNIFTY की जाँच को SENSEX पर लागू नहीं किया गया", excluded["eod_oi"]["reason"])
        self.assertEqual(
            excluded["futures"]["source"],
            "BSE SENSEX index-futures contract data",
        )
        self.assertIn("market-wide aggregate", excluded["futures"]["reason"])


    def test_five_asset_trends_shadow_uses_one_independent_seed_batch(self):
        calls = []

        class FakeTrendReq:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def build_payload(self, keywords, **kwargs):
                calls.append((list(keywords), kwargs))
                raise RuntimeError("stop after payload capture; no network request")

        fake_pytrends = ModuleType("pytrends")
        fake_request = ModuleType("pytrends.request")
        fake_request.TrendReq = FakeTrendReq
        fake_pytrends.request = fake_request
        with mock.patch.dict(
            "sys.modules",
            {"pytrends": fake_pytrends, "pytrends.request": fake_request},
        ):
            result = fetch_and_score.fetch_asset_trends_shadow()

        self.assertEqual(len(calls), 1)
        self.assertEqual(
            calls[0][0],
            ["nifty", "sensex", "bank nifty", "gold price", "silver price"],
        )
        self.assertEqual(calls[0][1], {"timeframe": "now 1-d", "geo": "IN"})
        self.assertEqual(
            set(result),
            {"NIFTY", "SENSEX", "BANKNIFTY", "GOLD", "SILVER"},
        )
        self.assertTrue(all(item.get("valid") is False for item in result.values()))


    def test_component_breakdown_labels_partial_coverage_without_changing_score(self):
        now = datetime(2026, 11, 8, 9, 35, tzinfo=timezone.utc)
        instruments = {
            "GOLD": {
                "headlines": [{
                    "title": "Gold price gains",
                    "source": "Reuters",
                    "score": 1.0,
                    "published_at": "2026-11-08T09:00:00Z",
                }],
            }
        }
        fetch_and_score.build_asset_component_breakdowns(
            instruments, now.isoformat(), now
        )
        breakdown = instruments["GOLD"]["component_breakdown"]
        self.assertEqual(breakdown["final"]["status"], "available")
        self.assertEqual(breakdown["final"]["included_components"], ["news"])
        self.assertEqual(breakdown["coverage"]["status"], "partial")
        self.assertEqual(breakdown["coverage"]["included_count"], 1)
        self.assertEqual(breakdown["coverage"]["applicable_count"], 4)
        self.assertEqual(breakdown["coverage"]["coverage_pct"], 25.0)
        self.assertIn("prediction confidence", breakdown["coverage"]["meaning"])

    def test_nse_index_futures_rejects_wrong_exchange_segment_type_symbol_and_date(self):
        from component_scoring import compare_nse_udiff_index_futures_oi

        current = {
            "Sgmt": "FO", "Src": "NSE", "FinInstrmTp": "FUTIDX",
            "TckrSymb": "NIFTY", "BizDt": "2026-11-06",
            "XpryDt": "2026-11-26", "OpnIntrst": 120000,
            "ChngInOpnIntrst": 1500, "ClsPric": 25100,
        }
        previous = [dict(
            current, BizDt="2026-11-05", OpnIntrst=118000,
            ChngInOpnIntrst=900, ClsPric=25000,
        )]
        invalid_current_rows = [
            dict(current, Sgmt="CD"),
            dict(current, Src="BSE"),
            dict(current, FinInstrmTp="OPTIDX"),
            dict(current, TckrSymb="BANKNIFTY"),
            dict(current, BizDt="2026-11-05"),
            dict(current, XpryDt="2026-12-31"),
        ]
        for invalid_row in invalid_current_rows:
            with self.subTest(row=invalid_row):
                result = compare_nse_udiff_index_futures_oi(
                    [invalid_row], previous, "NIFTY",
                    "2026-11-06", "2026-11-05", "2026-11-26",
                )
                self.assertFalse(result["available"])
                self.assertFalse(result["included_in_asset_final"])
                self.assertIn("row_count_not_one", result["reason"])

    def test_nse_index_futures_requires_same_exact_expiry_on_both_sessions(self):
        from component_scoring import compare_nse_udiff_index_futures_oi

        current = [{
            "Sgmt": "FO", "Src": "NSE", "FinInstrmTp": "FUTIDX",
            "TckrSymb": "BANKNIFTY", "BizDt": "2026-11-06",
            "XpryDt": "2026-11-25", "OpnIntrst": 52000,
            "ChngInOpnIntrst": -300, "ClsPric": 58400,
        }]
        previous_wrong_expiry = [dict(
            current[0], BizDt="2026-11-05", XpryDt="2026-12-30",
        )]
        result = compare_nse_udiff_index_futures_oi(
            current, previous_wrong_expiry, "BANKNIFTY",
            "2026-11-06", "2026-11-05", "2026-11-25",
        )
        self.assertFalse(result["available"])
        self.assertFalse(result["included_in_asset_final"])
        self.assertIn("row_count_not_one", result["reason"])


if __name__ == "__main__":
    unittest.main()
