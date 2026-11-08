import unittest

from market_signal_archive_backtest import build_archive_inputs, run_archive_backtest
from offline_contrarian_market_backtest import _day


def component(score, day, included=None):
    return {
        "final": {
            "status": "available", "score": score,
            "included_components": included or ["news"],
            "normalized_weights_pct": {"news": 100.0},
            "weight_total": 40.0,
        },
        "component_weights": {"news": 40.0},
        "components": {
            "news": {
                "score": score, "source": "Google News RSS · test",
                "source_date": day, "observed_at": f"{day}T20:00+05:30",
                "weight": 40.0, "included": True, "evidence_count": 3,
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
                "component_breakdown": component(score, day),
            }
        },
        "other_assets": {
            "GOLD": {
                "close": 70000 + close, "close_as_of": day,
                "close_valid": True, "price_source": "MCX dated close",
                "published_score": 9.0,
                "component_breakdown": component(-2.0, day),
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
        self.assertEqual(latest["NIFTY"]["components"]["news"]["weight"], 40.0)
        self.assertTrue(latest["NIFTY"]["components"]["news"]["included"])
        self.assertIn("search", latest["NIFTY"]["excluded_components"])
        self.assertEqual(latest["GOLD"]["final_score"], -2.0)


    def test_future_component_observation_is_rejected(self):
        row = snapshot("2026-11-06", "2026-11-06T20:05+05:30", 2.0, 100)["indices"]["NIFTY"]
        row["component_breakdown"]["components"]["news"]["observed_at"] = "2026-11-06T20:06+05:30"
        signals, closes, audit = build_archive_inputs({"records": [{
            "date": "2026-11-06", "captured_at_ist": "2026-11-06T20:05+05:30",
            "indices": {"NIFTY": row},
        }]})
        self.assertEqual(signals, [])
        self.assertEqual(closes, [])
        self.assertEqual(audit["invalid_component_evidence"], 1)

    def test_final_score_must_match_weighted_components(self):
        row = snapshot("2026-11-06", "2026-11-06T20:05+05:30", 2.0, 100)["indices"]["NIFTY"]
        row["component_breakdown"]["final"]["score"] = 7.5
        signals, closes, audit = build_archive_inputs({"records": [{
            "date": "2026-11-06", "captured_at_ist": "2026-11-06T20:05+05:30",
            "indices": {"NIFTY": row},
        }]})
        self.assertEqual(signals, [])
        self.assertEqual(closes, [])
        self.assertEqual(audit["invalid_component_evidence"], 1)

    def test_future_component_source_date_is_rejected(self):
        row = snapshot("2026-11-06", "2026-11-06T20:05+05:30", 2.0, 100)["indices"]["NIFTY"]
        row["component_breakdown"]["components"]["news"]["source_date"] = "2026-11-07"
        signals, closes, audit = build_archive_inputs({"records": [{
            "date": "2026-11-06", "captured_at_ist": "2026-11-06T20:05+05:30",
            "indices": {"NIFTY": row},
        }]})
        self.assertEqual(signals, [])
        self.assertEqual(closes, [])
        self.assertEqual(audit["invalid_component_evidence"], 1)

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


    def test_real_component_writer_output_is_accepted_by_archive_backtest(self):
        from datetime import datetime, timezone
        from fetch_and_score import build_asset_component_breakdowns

        updated = "2026-11-06T14:05:00Z"
        now_utc = datetime(2026, 11, 6, 14, 5, tzinfo=timezone.utc)
        instruments = {
            "NIFTY": {
                "news_query": "Nifty index India",
                "headlines": [{
                    "title": "Nifty rallies strongly",
                    "source": "Reuters",
                    "score": 2,
                    "published_at": "2026-11-06T14:00:00Z",
                }],
            }
        }
        build_asset_component_breakdowns(instruments, updated, now_utc)
        breakdown = instruments["NIFTY"]["component_breakdown"]
        self.assertEqual(breakdown["final"]["status"], "available")
        self.assertEqual(breakdown["final"]["included_components"], ["news"])
        self.assertTrue(breakdown["components"]["news"]["included"])
        self.assertEqual(breakdown["components"]["news"]["observed_at"], updated)

        archive = {"records": [{
            "date": "2026-11-06",
            "captured_at_ist": "2026-11-06T20:05+05:30",
            "indices": {
                "NIFTY": {
                    "close": 25000,
                    "close_as_of": "2026-11-06",
                    "close_valid": True,
                    "price_source": "NSE dated index close",
                    "component_breakdown": breakdown,
                }
            },
        }]}
        signals, closes, audit = build_archive_inputs(archive)
        self.assertEqual(len(signals), 1)
        self.assertEqual(len(closes), 1)
        self.assertEqual(audit["invalid_component_evidence"], 0)
        self.assertEqual(signals[0]["score"], breakdown["final"]["score"])




    def test_eod_writer_serializes_all_five_asset_component_evidence(self):
        import json
        import os
        import tempfile
        from datetime import datetime as RealDateTime, timezone
        from unittest.mock import patch
        import fetch_and_score as scorer

        class FixedDateTime(RealDateTime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 11, 6, 20, 5, tzinfo=tz)

        updated = "2026-11-06T14:05:00Z"
        now_utc = RealDateTime(2026, 11, 6, 14, 5, tzinfo=timezone.utc)
        instruments = {}
        for asset in ("NIFTY", "SENSEX", "BANKNIFTY", "GOLD", "SILVER"):
            instruments[asset] = {
                "news_query": f"{asset} market news",
                "price": 1000.0,
                "price_as_of": "2026-11-06",
                "price_source": "dated test close",
                "change_pct": 0.5,
                "headlines": [{
                    "title": f"{asset} rallies in test session",
                    "source": "Reuters",
                    "score": 2,
                    "published_at": "2026-11-06T14:00:00Z",
                }],
            }
        scorer.build_asset_component_breakdowns(instruments, updated, now_utc)
        self.assertTrue(all(
            instruments[asset]["component_breakdown"]["final"]["status"] == "available"
            for asset in instruments
        ))

        result = {
            "updated": updated,
            "instruments": instruments,
            "participant_oi": {},
            "trends": {},
            "market_news": {},
        }
        with tempfile.TemporaryDirectory() as directory:
            archive_path = os.path.join(directory, "market_signal_history.json")
            with (
                patch.object(scorer, "MARKET_SIGNAL_HISTORY_FILE", archive_path),
                patch.object(scorer, "SKIP_EVENTS", False),
                patch.object(scorer.dt, "datetime", FixedDateTime),
            ):
                scorer.update_market_signal_history(result)

            with open(archive_path, encoding="utf-8") as handle:
                archive = json.load(handle)

        record = archive["records"][0]
        self.assertEqual(set(record["indices"]), {"NIFTY", "SENSEX", "BANKNIFTY"})
        self.assertEqual(set(record["other_assets"]), {"GOLD", "SILVER"})
        for asset in ("NIFTY", "SENSEX", "BANKNIFTY"):
            self.assertEqual(
                record["indices"][asset]["component_breakdown"],
                instruments[asset]["component_breakdown"],
            )
            self.assertTrue(record["indices"][asset]["close_valid"])
        for asset in ("GOLD", "SILVER"):
            self.assertEqual(
                record["other_assets"][asset]["component_breakdown"],
                instruments[asset]["component_breakdown"],
            )
            self.assertTrue(record["other_assets"][asset]["close_valid"])

        signals, closes, audit = build_archive_inputs(archive)
        self.assertEqual(len(signals), 5)
        self.assertEqual(len(closes), 5)
        self.assertEqual(audit["invalid_component_evidence"], 0)


if __name__ == "__main__":
    unittest.main()
