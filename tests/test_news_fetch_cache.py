from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

from fetch_and_score import fetch_news_snapshot, news_refresh_due


class NewsFetchCacheTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 17, 13, 30, tzinfo=timezone.utc)
        self.published = (self.now - timedelta(hours=3)).isoformat().replace("+00:00", "Z")
        self.headlines = [{
            "title": "Nifty market rally continues",
            "source": "Example News",
            "link": "https://example.invalid/story",
            "score": 1,
            "age_h": 0.5,
            "published_at": self.published,
        }]

    def test_recent_attempt_reuses_headlines_without_another_rss_request(self):
        previous = {
            "news_fetch_attempted_at": (self.now - timedelta(minutes=30)).isoformat(),
            "headlines": self.headlines,
        }
        with patch("fetch_and_score.fetch_news") as fetch:
            snapshot = fetch_news_snapshot("nifty news", previous, self.now)
        fetch.assert_not_called()
        self.assertEqual(snapshot["status"], "cached")
        self.assertEqual(snapshot["headlines"][0]["age_h"], 3.0)
        self.assertEqual(snapshot["headlines"][0]["published_at"], self.published)
        self.assertEqual(snapshot["attempted_at"], previous["news_fetch_attempted_at"])

    def test_rate_limit_preserves_previous_headlines_with_original_age(self):
        previous = {
            "news_fetch_attempted_at": (self.now - timedelta(hours=1)).isoformat(),
            "headlines": self.headlines,
        }
        with patch("fetch_and_score.fetch_news", side_effect=RuntimeError("429 Too Many Requests")):
            snapshot = fetch_news_snapshot("nifty news", previous, self.now)
        self.assertEqual(snapshot["status"], "refresh_failed_using_cached_headlines")
        self.assertEqual(snapshot["headlines"][0]["age_h"], 3.0)
        self.assertEqual(snapshot["headlines"][0]["published_at"], self.published)
        self.assertEqual(snapshot["attempted_at"], "2026-11-17T13:30:00Z")
        self.assertIn("429", snapshot["error"])

    def test_failed_fetch_without_previous_headlines_remains_unavailable(self):
        previous = {
            "news_fetch_attempted_at": (self.now - timedelta(hours=1)).isoformat(),
            "headlines": [],
        }
        with patch("fetch_and_score.fetch_news", side_effect=RuntimeError("429 Too Many Requests")):
            snapshot = fetch_news_snapshot("silver news", previous, self.now)
        self.assertEqual(snapshot["status"], "unavailable")
        self.assertEqual(snapshot["headlines"], [])

    def test_refresh_is_due_after_cooldown_or_without_valid_attempt_timestamp(self):
        recent = {"news_fetch_attempted_at": (self.now - timedelta(minutes=44)).isoformat()}
        old = {"news_fetch_attempted_at": (self.now - timedelta(minutes=46)).isoformat()}
        invalid = {"news_fetch_attempted_at": "not-a-timestamp"}
        self.assertFalse(news_refresh_due(recent, self.now))
        self.assertTrue(news_refresh_due(old, self.now))
        self.assertTrue(news_refresh_due(invalid, self.now))
        self.assertTrue(news_refresh_due({}, self.now))


if __name__ == "__main__":
    unittest.main()
