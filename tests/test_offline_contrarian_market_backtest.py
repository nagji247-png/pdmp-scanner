import unittest

from offline_contrarian_market_backtest import run_contrarian_backtest


def signal(day, score, observed="2026-11-02T10:00:00Z", asset="NIFTY", **extra):
    row = {"asset": asset, "signal_date": day, "known_on": day, "score": score,
           "source": "dated crowd archive", "observed_at": observed}
    row.update(extra)
    return row


def close(day, value, asset="NIFTY"):
    return {"asset": asset, "market_date": day, "close": value,
            "source": "official close archive"}


class OfflineContrarianMarketBacktestTests(unittest.TestCase):
    def test_bearish_crowd_then_rising_market_is_contrarian_win(self):
        report = run_contrarian_backtest(
            [signal("2026-11-02", -6)],
            [close("2026-11-02", 100), close("2026-11-03", 102)])
        self.assertEqual(report["summary"]["sample_count"], 1)
        self.assertEqual(report["summary"]["contrarian_accuracy_pct"], 100.0)
        self.assertEqual(report["summary"]["crowd_follow_accuracy_pct"], 0.0)
        self.assertEqual(report["trades"][0]["target_session"], "2026-11-03")
        self.assertEqual(report["provider_calls"], 0)
        self.assertFalse(report["production_score_modified"])

    def test_bullish_crowd_then_falling_market_is_contrarian_win(self):
        report = run_contrarian_backtest(
            [signal("2026-11-02", 5)],
            [close("2026-11-02", 100), close("2026-11-03", 98)])
        self.assertTrue(report["trades"][0]["contrarian_correct"])

    def test_latest_snapshot_per_asset_day_is_counted_once(self):
        report = run_contrarian_backtest(
            [signal("2026-11-02", -5, "2026-11-02T09:00:00Z"),
             signal("2026-11-02", 6, "2026-11-02T10:00:00Z")],
            [close("2026-11-02", 100), close("2026-11-03", 98)])
        self.assertEqual(report["summary"]["sample_count"], 1)
        self.assertEqual(report["trades"][0]["signal_score"], 6)

    def test_future_known_on_signal_is_rejected(self):
        report = run_contrarian_backtest(
            [signal("2026-11-02", -6, known_on="2026-11-03")],
            [close("2026-11-02", 100), close("2026-11-03", 102)])
        self.assertEqual(report["malformed_signal_rows"], 1)
        self.assertEqual(report["summary"]["sample_count"], 0)

    def test_neutral_and_missing_base_close_are_not_scored(self):
        report = run_contrarian_backtest(
            [signal("2026-11-02", 0), signal("2026-11-03", -5, asset="SENSEX")],
            [close("2026-11-02", 100)])
        self.assertEqual(report["skipped"]["neutral_or_below_threshold"], 1)
        self.assertEqual(report["skipped"]["missing_base_close"], 1)
        self.assertEqual(report["summary"]["sample_count"], 0)

    def test_conflicting_duplicate_closes_fail_closed(self):
        with self.assertRaises(ValueError):
            run_contrarian_backtest(
                [signal("2026-11-02", -5)],
                [close("2026-11-02", 100), close("2026-11-02", 101)])

    def test_assets_are_scored_independently(self):
        report = run_contrarian_backtest(
            [signal("2026-11-02", -5, asset="NIFTY"),
             signal("2026-11-02", 5, asset="GOLD")],
            [close("2026-11-02", 100, "NIFTY"), close("2026-11-03", 101, "NIFTY"),
             close("2026-11-02", 100, "GOLD"), close("2026-11-03", 99, "GOLD")])
        self.assertEqual(report["by_asset"]["NIFTY"]["contrarian_accuracy_pct"], 0.0)
        self.assertEqual(report["by_asset"]["GOLD"]["contrarian_accuracy_pct"], 100.0)


if __name__ == "__main__":
    unittest.main()
