import unittest

from market_signal_archive_backtest import build_archive_inputs, run_archive_backtest
from offline_contrarian_market_backtest import _day


def component(score, included=None):
    return {
        "final": {
            "status": "available", "score": score,
            "included_components": included or ["news"],
        },
        "components": {
            "news": {
                "score": score, "source": "Google News RSS · test",
                "source_date": "2026-11-06", "observed_at": "2026-11-06T20:05+05:30",
                "evidence_count": 3,
            }
        },
        "excluded_components": {
            "search": {"source": "Google Trends", "reason": "not validated"}
        },
        "coverage": {
            "status": "partial", "included_count": 1,
            "applicable_count": 4, "coverage_pct": 25,
        },
    }


def snapshot(day, captured, score, close, close_as_of=None):
    return {
        "date": day,
        "captured_at_ist": captured,
        "indices": {
            "NIFTY": {
                "close": close, "close_as_of": close_as_of or day,
                "price_source": "NSE dated index close",
                "published_score": 8.5,
                "component_breakdown": component(score),
            }
        },
        "other_assets": {
            "GOLD": {
                "close": 70000 + close, "close_as_of": day,
                "close_valid": True, "price_source": "MCX dated close",
                "published_score": 9.0,
                "component_breakdown": component(-2.0),
            }
        },
    }


class MarketSignalArchiveBacktestTests(unittest.TestCase):
    def test_indian_date_formats_are_parsed(self):
        self.assertEqual(_day("06/11/2026").isoformat(), "2026-11-06")
        self.assertEqual(_day("2026-11-06").isoformat(), "2026-11-06")

    def test_only_component_final_is_used_not_published_score(self):
        archive = {"records": [{
            "date": "06/11/2026",
            "captured_at_ist": "2026-11-06T20:05+05:30",
            "indices": {"NIFTY": {
                "close": 25000, "close_as_of": "06/11/2026",
                "published_score": 9.0,
            }},
        }]}
        signals, closes, audit = build_archive_inputs(archive)
        self.assertEqual(signals, [])
        self.assertEqual(closes, [])
        self.assertEqual(audit["missing_component_final"], 1)

    def test_eod_component_signals_and_closes_are_extracted(self):
        archive = {"records": [
            snapshot("2026-11-05", "2026-11-05T20:05+05:30", -2.0, 100),
            snapshot("2026-11-06", "2026-11-06T20:05+05:30", 2.0, 102),
        ]}
        signals, closes, audit = build_archive_inputs(archive)
        self.assertEqual(len(signals), 4)
        self.assertEqual(len(closes), 4)
        self.assertEqual(signals[0]["score"], -2.0)
        self.assertIn("news", signals[0]["source"])
        self.assertEqual(audit["assets_with_component_final"], {"NIFTY": 2, "GOLD": 2})
        latest = audit["latest_asset_evidence"]
        self.assertEqual(latest["NIFTY"]["date"], "2026-11-06")
        self.assertEqual(latest["NIFTY"]["final_score"], 2.0)
        self.assertEqual(latest["NIFTY"]["coverage"]["coverage_pct"], 25)
        self.assertEqual(latest["NIFTY"]["components"]["news"]["source_date"], "2026-11-06")
        self.assertEqual(latest["NIFTY"]["components"]["news"]["evidence_count"], 3)
        self.assertIn("search", latest["NIFTY"]["excluded_components"])
        self.assertEqual(latest["GOLD"]["final_score"], 2.0 - 4.0)

    def test_non_eod_snapshots_are_not_used(self):
        archive = {"records": [
            snapshot("2026-11-06", "2026-11-06T15:29+05:30", -4.0, 100)
        ]}
        signals, closes, audit = build_archive_inputs(archive)
        self.assertEqual(signals, [])
        self.assertEqual(closes, [])
        self.assertEqual(audit["invalid_or_non_eod_snapshot"], 1)

    def test_wrong_close_date_is_not_backtest_eligible(self):
        archive = {"records": [
            snapshot("2026-11-06", "2026-11-06T20:05+05:30", -4.0, 100, "2026-11-05")
        ]}
        signals, closes, audit = build_archive_inputs(archive)
        self.assertEqual(len(signals), 2)
        self.assertEqual(len(closes), 1)
        self.assertEqual(audit["invalid_or_mismatched_close"], 1)

    def test_archive_backtest_reports_independent_asset_results(self):
        archive = {"records": [
            snapshot("2026-11-05", "2026-11-05T20:05+05:30", -2.0, 100),
            snapshot("2026-11-06", "2026-11-06T20:05+05:30", 2.0, 102),
        ]}
        report = run_archive_backtest(archive)
        self.assertEqual(report["summary"]["sample_count"], 2)
        self.assertEqual(report["provider_calls"], 0)
        self.assertFalse(report["production_score_modified"])
        self.assertIn("NIFTY", report["by_asset"])
        self.assertIn("GOLD", report["by_asset"])


if __name__ == "__main__":
    unittest.main()
