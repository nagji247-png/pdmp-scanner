import sys
import types
import unittest
from unittest.mock import patch

import pandas as pd

import fetch_and_score


class _FakeTrends:
    def __init__(self):
        self.payloads = []
        self.interest_calls = 0

    def build_payload(self, seeds, timeframe, geo):
        self.payloads.append((list(seeds), timeframe, geo))

    def related_queries(self):
        return {}

    def interest_over_time(self):
        self.interest_calls += 1
        return None


class AssetTrendsBoundedFallbackTests(unittest.TestCase):
    def test_directional_phrase_groups_include_hindi_and_english_alternatives(self):
        for spec in fetch_and_score.ASSET_DIRECTIONAL_TRENDS_QUERIES.values():
            for direction in ("bull", "bear", "neutral"):
                self.assertIn("+", spec[direction])
                self.assertRegex(spec[direction], r"[\\u0900-\\u097f]")

    def test_directional_diagnostic_rejects_tiny_denominator_instead_of_false_100_percent(self):
        spec = fetch_and_score.ASSET_DIRECTIONAL_TRENDS_QUERIES["SILVER"]
        frame = pd.DataFrame({
            spec["seed"]: [100.0],
            spec["bull"]: [0.0],
            spec["bear"]: [0.0],
            spec["neutral"]: [0.91],
        }, index=pd.DatetimeIndex(["2026-11-22T01:52:00Z"]))
        with patch.object(fetch_and_score, "_trends_observation_time", return_value=pd.Timestamp("2026-11-22T01:52:00Z").to_pydatetime()):
            with self.assertRaisesRegex(ValueError, "संयुक्त खोज-रुचि"):
                fetch_and_score._summarize_asset_directional_trends(frame, "SILVER", spec)

    def test_directional_diagnostic_normalizes_only_after_minimum_interest_is_met(self):
        spec = fetch_and_score.ASSET_DIRECTIONAL_TRENDS_QUERIES["SENSEX"]
        frame = pd.DataFrame({
            spec["seed"]: [100.0],
            spec["bull"]: [6.25],
            spec["bear"]: [0.0],
            spec["neutral"]: [0.0],
        }, index=pd.DatetimeIndex(["2026-11-22T01:52:00Z"]))
        with patch.object(fetch_and_score, "_trends_observation_time", return_value=pd.Timestamp("2026-11-22T01:52:00Z").to_pydatetime()):
            result = fetch_and_score._summarize_asset_directional_trends(frame, "SENSEX", spec)
        self.assertEqual(result["query_interest_mix_pct"], {"bull": 100.0, "bear": 0.0, "neutral": 0.0})
        self.assertTrue(result["diagnostic_only"])

    def test_manual_asset_refresh_allowed_when_primary_is_sparse_or_unavailable(self):

        self.assertTrue(fetch_and_score.should_refresh_manual_asset_trends(False, "insufficient classified search interest"))

    def test_manual_asset_refresh_skipped_on_rate_limit(self):
        self.assertFalse(fetch_and_score.should_refresh_manual_asset_trends(False, "429 Too Many Requests"))

    def test_manual_asset_refresh_fails_closed_without_error_detail(self):
        self.assertFalse(fetch_and_score.should_refresh_manual_asset_trends(False, None))

    def test_manual_asset_refresh_allowed_when_primary_succeeds(self):
        self.assertTrue(fetch_and_score.should_refresh_manual_asset_trends(True, None))

    def _run_with_fake_trends(self, summarize):
        fake = _FakeTrends()
        request_module = types.ModuleType("pytrends.request")
        request_module.TrendReq = lambda **kwargs: fake
        package_module = types.ModuleType("pytrends")
        package_module.request = request_module
        with patch.dict(sys.modules, {"pytrends": package_module, "pytrends.request": request_module}), \
             patch.object(fetch_and_score, "_summarize_asset_related_query_snapshot", side_effect=summarize), \
             patch.object(fetch_and_score, "_trends_snapshot_timestamp", return_value=("2026-11-21T10:00:00+05:30", "retrieval_time")), \
             patch.object(fetch_and_score.time, "sleep"):
            result = fetch_and_score.fetch_asset_trends_shadow()
        self.assertEqual(fake.interest_calls, 0, "asset related-query refresh must not spend an extra timestamp request")
        return result, fake.payloads

    def test_sparse_one_day_uses_one_shared_seven_day_fallback(self):
        def summarize(related, asset, seed, source_time, source, timestamp_basis="source_observation", timeframe="now 1-d"):
            if timeframe == "now 1-d":
                return {"valid": False, "reason": "insufficient classified queries", "timeframe": timeframe}
            return {"valid": True, "timeframe": timeframe, "bull_pct": 60.0, "production_score_used": False}

        result, payloads = self._run_with_fake_trends(summarize)
        self.assertEqual([item[1] for item in payloads], ["now 1-d", "now 7-d"])
        self.assertEqual(set(result), {"NIFTY", "SENSEX", "BANKNIFTY", "GOLD", "SILVER"})
        for snapshot in result.values():
            self.assertTrue(snapshot["valid"])
            self.assertEqual(snapshot["timeframe"], "now 7-d")
            self.assertTrue(snapshot["fallback_used"])
            self.assertFalse(snapshot["production_score_used"])

    def test_rate_limit_does_not_trigger_seven_day_retry(self):
        def summarize(*args, **kwargs):
            return {"valid": False, "reason": "429 Too Many Requests", "timeframe": "now 1-d"}

        result, payloads = self._run_with_fake_trends(summarize)
        self.assertEqual([item[1] for item in payloads], ["now 1-d"])
        self.assertTrue(all(not item["valid"] for item in result.values()))

    def test_initial_batch_rate_limit_skips_crude_and_phrase_diagnostics(self):
        class RateLimitedTrends:
            def __init__(self):
                self.payloads = []

            def build_payload(self, seeds, timeframe, geo):
                self.payloads.append((list(seeds), timeframe, geo))
                raise RuntimeError("Google returned a response with code 429")

        fake = RateLimitedTrends()
        request_module = types.ModuleType("pytrends.request")
        request_module.TrendReq = lambda **kwargs: fake
        package_module = types.ModuleType("pytrends")
        package_module.request = request_module
        with patch.dict(sys.modules, {"pytrends": package_module, "pytrends.request": request_module}):
            with patch.object(fetch_and_score, "_attach_asset_directional_trends_diagnostics", side_effect=lambda output, seeds, enabled=False, diagnostics=None: output) as diagnostics:
                with patch.object(fetch_and_score.time, "sleep"):
                    result = fetch_and_score.fetch_asset_trends_shadow(
                        include_directional_diagnostics=True, include_crude=True
                    )

        self.assertEqual(len(fake.payloads), 1)
        self.assertEqual(set(result), {"NIFTY", "SENSEX", "BANKNIFTY", "GOLD", "SILVER", "CRUDEOIL"})
        self.assertTrue(diagnostics.call_args.kwargs["enabled"])
        self.assertTrue(all(not item["valid"] for item in result.values()))


    def test_manual_directional_diagnostics_run_before_related_batch_and_stop_on_429(self):
        class ShouldNotBeCalledTrends:
            def __init__(self):
                self.payload_calls = 0

            def build_payload(self, seeds, timeframe, geo):
                self.payload_calls += 1
                raise AssertionError("related-query batch must not run after diagnostic 429")

        fake = ShouldNotBeCalledTrends()
        request_module = types.ModuleType("pytrends.request")
        request_module.TrendReq = lambda **kwargs: fake
        package_module = types.ModuleType("pytrends")
        package_module.request = request_module
        diagnostic_result = {
            asset: {
                "available": False, "diagnostic_only": True,
                "reason": "Google returned a response with code 429",
            }
            for asset in fetch_and_score.ASSET_DIRECTIONAL_TRENDS_QUERIES
        }
        with patch.dict(sys.modules, {"pytrends": package_module, "pytrends.request": request_module}), \
             patch.object(fetch_and_score, "fetch_asset_directional_trends_diagnostics", return_value=diagnostic_result) as diagnostic, \
             patch.object(fetch_and_score.time, "sleep"):
            result = fetch_and_score.fetch_asset_trends_shadow(
                include_directional_diagnostics=True, include_crude=True
            )

        diagnostic.assert_called_once()
        self.assertEqual(fake.payload_calls, 0)
        self.assertIn("directional_query_diagnostic", result["NIFTY"])
        self.assertEqual(
            result["NIFTY"]["directional_query_diagnostic"]["reason"],
            "Google returned a response with code 429",
        )
        self.assertIn("CRUDEOIL", result)

    def test_only_invalid_assets_are_reclassified_on_fallback(self):
        fallback_assets = []

        def summarize(related, asset, seed, source_time, source, timestamp_basis="source_observation", timeframe="now 1-d"):
            if timeframe == "now 1-d" and asset != "NIFTY":
                return {"valid": True, "timeframe": timeframe, "production_score_used": False}
            if timeframe == "now 1-d":
                return {"valid": False, "reason": "sparse", "timeframe": timeframe}
            fallback_assets.append(asset)
            return {"valid": True, "timeframe": timeframe, "production_score_used": False}

        result, payloads = self._run_with_fake_trends(summarize)
        self.assertEqual([item[1] for item in payloads], ["now 1-d", "now 7-d"])
        self.assertEqual(fallback_assets, ["NIFTY"])
        self.assertEqual(result["NIFTY"]["timeframe"], "now 7-d")
        self.assertEqual(result["SENSEX"]["timeframe"], "now 1-d")


if __name__ == "__main__":
    unittest.main()
