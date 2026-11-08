import unittest

from offline_component_replay import replay_component_scores


class OfflineComponentReplayTests(unittest.TestCase):
    def test_replays_each_asset_independently_and_renormalizes_available_parts(self):
        rows = [
            {"asset": "NIFTY", "component": "news", "score": 6,
             "source": "News archive", "source_date": "2026-11-05",
             "observed_at": "2026-11-05T10:00:00Z", "weight": 40},
            {"asset": "NIFTY", "component": "search", "score": -2,
             "source": "Trends archive", "source_date": "2026-11-05",
             "observed_at": "2026-11-05T11:00:00Z", "weight": 40},
            {"asset": "GOLD", "component": "news", "score": 4,
             "source": "Gold news archive", "source_date": "2026-11-05",
             "observed_at": "2026-11-05T10:00:00Z", "weight": 40},
        ]
        result = replay_component_scores(rows, ["2026-11-05"])
        assets = result["results"][0]["assets"]
        self.assertEqual(assets["NIFTY"]["score"], 2.0)
        self.assertEqual(assets["NIFTY"]["normalized_weights_pct"],
                         {"news": 50.0, "search": 50.0})
        self.assertEqual(assets["GOLD"]["score"], 4.0)
        self.assertEqual(assets["GOLD"]["included_components"], ["news"])

    def test_no_lookahead_future_observations_are_excluded(self):
        rows = [{
            "asset": "SENSEX", "component": "news", "score": 9,
            "source": "Future news", "source_date": "2026-11-06",
            "observed_at": "2026-11-06T09:00:00Z", "weight": 40,
        }]
        result = replay_component_scores(rows, ["2026-11-05"])
        self.assertEqual(result["results"][0]["assets"], {})
        self.assertEqual(result["results"][0]["excluded_observations"]["future_observation"], 1)

    def test_latest_component_snapshot_wins_without_double_counting(self):
        rows = [
            {"asset": "BANKNIFTY", "component": "news", "score": 1,
             "source": "News", "source_date": "2026-11-05",
             "observed_at": "2026-11-05T09:00:00Z", "weight": 40},
            {"asset": "BANKNIFTY", "component": "news", "score": 5,
             "source": "News", "source_date": "2026-11-05",
             "observed_at": "2026-11-05T12:00:00Z", "weight": 40},
        ]
        result = replay_component_scores(rows, ["2026-11-05"])
        asset = result["results"][0]["assets"]["BANKNIFTY"]
        self.assertEqual(asset["score"], 5.0)
        self.assertEqual(asset["included_components"], ["news"])

    def test_stale_and_malformed_rows_fail_closed(self):
        rows = [
            {"asset": "GOLD", "component": "news", "score": 3,
             "source": "Old", "source_date": "2026-11-01",
             "observed_at": "2026-11-01T12:00:00Z", "weight": 40},
            {"asset": "GOLD", "component": "search", "score": float("nan"),
             "source": "Bad", "source_date": "2026-11-05",
             "observed_at": "2026-11-05T12:00:00Z", "weight": 40},
        ]
        result = replay_component_scores(rows, ["2026-11-05"], max_age_days=1)
        day = result["results"][0]
        self.assertEqual(day["assets"], {})
        self.assertEqual(day["excluded_observations"]["stale_observation"], 1)
        self.assertEqual(day["malformed_observations"], 1)

    def test_replay_never_changes_production_or_calls_providers(self):
        result = replay_component_scores([], ["2026-11-05"])
        self.assertEqual(result["provider_calls"], 0)
        self.assertFalse(result["production_score_modified"])
        self.assertEqual(result["results"][0]["provider_calls"], 0)
        self.assertFalse(result["results"][0]["production_score_modified"])


if __name__ == "__main__":
    unittest.main()
