import unittest

from fetch_and_score import (
    is_google_trends_rate_limited,
    should_run_asset_directional_diagnostics,
)


class GoogleTrendsRequestPolicyTests(unittest.TestCase):
    def test_phrase_diagnostics_run_only_in_1900_slot(self):
        self.assertTrue(should_run_asset_directional_diagnostics("1900"))
        for slot in ("0915", "1100", "1300", "", None):
            self.assertFalse(should_run_asset_directional_diagnostics(slot))

    def test_rate_limit_detection_covers_common_provider_messages(self):
        self.assertTrue(is_google_trends_rate_limited("HTTP 429"))
        self.assertTrue(is_google_trends_rate_limited("Too many requests"))
        self.assertTrue(is_google_trends_rate_limited("rate limit exceeded"))
        self.assertFalse(is_google_trends_rate_limited("connection timeout"))

    def test_rate_limit_detection_handles_missing_error(self):
        self.assertFalse(is_google_trends_rate_limited(None))


if __name__ == "__main__":
    unittest.main()
