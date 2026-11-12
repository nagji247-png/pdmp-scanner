import unittest
from crowd_mood_intraday import classify_mood, update_archive


class CrowdMoodArchiveTests(unittest.TestCase):
    def test_extreme_directional_share(self):
        mood, share = classify_mood({"ok": True, "stale": False, "today_basis": "now_1d",
            "bull_score_pct": 18, "bear_score_pct": 2, "neutral_score_pct": 80})
        self.assertEqual((mood, share), ("EXTREME_BULLISH", 90.0))

    def test_stale_and_seven_day_data_are_excluded(self):
        for stale, basis in ((True, "now_1d"), (False, "now_7d")):
            self.assertEqual(classify_mood({"ok": True, "stale": stale, "today_basis": basis,
                "bull_score_pct": 90, "bear_score_pct": 10, "neutral_score_pct": 0}), (None, None))

    def test_one_daily_event_despite_repeated_scans(self):
        row = {"updated": "2026-11-12T04:00:00Z", "trends": {"ok": True, "stale": False,
            "today_basis": "now_1d", "source_data_time": "2026-11-12T03:55:00Z",
            "bull_score_pct": 80, "bear_score_pct": 10, "neutral_score_pct": 10}, "instruments": {}}
        archive = update_archive({}, row)
        archive = update_archive(archive, dict(row, updated="2026-11-12T04:30:00Z"))
        self.assertEqual(len(archive["events"]), 1)
        self.assertEqual(len(archive["price_snapshots"]), 6)

    def test_last_close_is_not_intraday_quote(self):
        row = {"updated": "2026-11-12T04:00:00Z", "trends": {}, "instruments": {
            "NIFTY": {"price": 25000, "price_as_of": "2026-11-12", "price_time": "09:30",
                      "price_source": "Yahoo Finance · LAST CLOSING PRICE"}}}
        archive = update_archive({}, row)
        nifty = next(x for x in archive["price_snapshots"] if x["index"] == "NIFTY")
        self.assertFalse(nifty["intraday_eligible"])


if __name__ == "__main__":
    unittest.main()
