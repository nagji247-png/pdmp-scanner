import sys
import unittest
from unittest import mock

import fetch_and_score


class GoogleTrendsRateLimitTests(unittest.TestCase):
    def test_http_429_stops_remaining_fallback_timeframes(self):
        with mock.patch.dict(sys.modules, {"pytrends": mock.MagicMock()}), \
             mock.patch.object(
                 fetch_and_score, "_trends_once",
                 side_effect=RuntimeError("HTTP 429 Too Many Requests"),
             ) as hourly, \
             mock.patch.object(
                 fetch_and_score, "_trends_related_queries"
             ) as related:
            result = fetch_and_score.fetch_trends()

        self.assertFalse(result["ok"])
        self.assertIn("429", result["error"])
        self.assertEqual(hourly.call_count, 1)
        related.assert_not_called()


if __name__ == "__main__":
    unittest.main()
