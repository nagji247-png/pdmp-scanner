import unittest
from unittest import mock

import fetch_and_score


class DailyScoreHistoryTests(unittest.TestCase):
    def test_same_day_score_refreshes_and_uses_next_session_direction(self):
        records = []
        with mock.patch.object(fetch_and_score, "SKIP_EVENTS", False):
            fetch_and_score.update_daily_score_history(
                records, "NIFTY", 6, "2026-11-10", {}
            )
            fetch_and_score.update_daily_score_history(
                records, "NIFTY", -2, "2026-11-10", {}
            )
            fetch_and_score.update_daily_score_history(
                records, "NIFTY", -2, "2026-11-11",
                {"2026-11-11": 0.2, "2026-11-12": -0.5}
            )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["score"], -2.0)
        self.assertEqual(records[0]["direction"], "bearish")
        self.assertEqual(records[0]["next_session_date"], "2026-11-11")
        self.assertEqual(records[0]["next_change"], 0.2)
        self.assertEqual(records[0]["outcome"], "trap")

    def test_each_date_gets_its_own_outcome_and_neutral_is_not_directional(self):
        records = []
        with mock.patch.object(fetch_and_score, "SKIP_EVENTS", False):
            fetch_and_score.update_daily_score_history(
                records, "NIFTY", 6, "2026-11-10", {}
            )
            fetch_and_score.update_daily_score_history(
                records, "NIFTY", -2, "2026-11-11",
                {"2026-11-11": -0.5}
            )
            fetch_and_score.update_daily_score_history(
                records, "NIFTY", 0, "2026-11-12",
                {"2026-11-11": -0.5, "2026-11-12": 0.0, "2026-11-13": 0.4}
            )

        by_date = {row["date"]: row for row in records}
        self.assertEqual(by_date["2026-11-10"]["outcome"], "trap")
        self.assertEqual(by_date["2026-11-10"]["next_change"], -0.5)
        self.assertEqual(by_date["2026-11-11"]["outcome"], "neutral")
        self.assertEqual(by_date["2026-11-12"]["outcome"], "neutral_signal")

    def test_no_news_does_not_create_a_false_neutral_record(self):
        records = []
        with mock.patch.object(fetch_and_score, "SKIP_EVENTS", False):
            fetch_and_score.update_daily_score_history(
                records, "NIFTY", 0, "2026-11-10", {}, has_news=False
            )
        self.assertEqual(records, [])

    def test_daily_archive_retains_only_latest_260_records_per_instrument(self):
        records = []
        with mock.patch.object(fetch_and_score, "SKIP_EVENTS", False):
            for day in range(1, 263):
                date = f"2026-{(day - 1) // 28 + 1:02d}-{(day - 1) % 28 + 1:02d}"
                fetch_and_score.update_daily_score_history(
                    records, "NIFTY", 1, date, {}
                )
        self.assertEqual(len(records), 260)


if __name__ == "__main__":
    unittest.main()
