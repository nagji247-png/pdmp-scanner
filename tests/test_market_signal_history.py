import unittest
from unittest import mock

import fetch_and_score

from validate_market_signal_history import (
    assess_snapshot, market_snapshot_completeness, validate_archives,
)


DATE = "2026-11-06"
OI_FIELDS = (
    "future_index_long", "future_index_short",
    "index_call_long", "index_call_short",
    "index_put_long", "index_put_short",
    "future_stock_long", "future_stock_short",
    "stock_call_long", "stock_call_short",
    "stock_put_long", "stock_put_short",
)


def participants():
    return {
        group: {field: 100.0 for field in OI_FIELDS}
        for group in ("FII", "DII", "PRO", "CLIENT")
    }


def trends_slot_evidence():
    return {
        "date": DATE,
        "slots": [
            {"id": "0915", "time": "09:15", "status": "success",
             "source_data_time": "2026-11-06T09:10:00+05:30",
             "bull_pct": 55.0, "bear_pct": 25.0, "neutral_pct": 20.0, "crowd_pct": 55.0},
            {"id": "1100", "time": "11:00", "status": "success",
             "source_data_time": "2026-11-06T10:55:00+05:30",
             "bull_pct": 55.0, "bear_pct": 25.0, "neutral_pct": 20.0, "crowd_pct": 55.0},
            {"id": "1300", "time": "13:00", "status": "success",
             "source_data_time": "2026-11-06T12:55:00+05:30",
             "bull_pct": 55.0, "bear_pct": 25.0, "neutral_pct": 20.0, "crowd_pct": 55.0},
            {"id": "1900", "time": "19:00", "status": "success",
             "source_data_time": "2026-11-06T18:55:00+05:30",
             "bull_pct": 55.0, "bear_pct": 25.0, "neutral_pct": 20.0, "crowd_pct": 55.0},
        ],
    }


def snapshot(*, trends_complete=True, oi_date=DATE, capture="2026-11-06T14:32:00Z"):
    return {
        "date": DATE,
        "captured_at_utc": capture,
        "trends": {
            "valid": True,
            "as_of": "2026-11-06T13:25:00+00:00",
            "daily_complete": trends_complete,
            "daily_slot_evidence": trends_slot_evidence(),
            "crowd_bull_pct": 55.0,
            "bull_score_pct": 55.0,
            "bear_score_pct": 25.0,
            "neutral_score_pct": 20.0,
        },
        "indices": {
            name: {
                "close": 25000.0,
                "close_as_of": "06/11/2026",
                "experimental_news_score": 1.0,
                "experimental_headline_count": 3,
            }
            for name in ("NIFTY", "SENSEX", "BANKNIFTY")
        },
        "participant_oi": {
            "date": oi_date,
            "participants": participants(),
        },
    }


def oi_history():
    return {
        "records": [
            {"date": "2026-11-05", "participants": participants()},
            {"date": DATE, "participants": participants()},
        ]
    }


class MarketSignalHistoryTests(unittest.TestCase):
    def test_complete_point_in_time_snapshot_is_eligible(self):
        quality = assess_snapshot(snapshot(), {
            "2026-11-05": None,
            DATE: "2026-11-05",
        })
        self.assertTrue(quality["complete_for_combined_backtest"])
        self.assertTrue(quality["trends_daily_complete"])
        self.assertTrue(quality["oi_change_available"])

    def test_partial_daily_trends_are_not_eligible(self):
        quality = assess_snapshot(snapshot(trends_complete=False), {
            "2026-11-05": None,
            DATE: "2026-11-05",
        })
        self.assertFalse(quality["trends_daily_complete"])
        self.assertFalse(quality["complete_for_combined_backtest"])

    def test_all_four_unique_same_day_trends_slots_are_required(self):
        row = snapshot()
        row["trends"]["daily_slot_evidence"]["slots"].pop()
        quality = assess_snapshot(row, {"2026-11-05": None, DATE: "2026-11-05"})
        self.assertFalse(quality["trends_slot_evidence_complete"])
        self.assertFalse(quality["complete_for_combined_backtest"])

        row = snapshot()
        slots = row["trends"]["daily_slot_evidence"]["slots"]
        slots[-1] = dict(slots[0])
        quality = assess_snapshot(row, {"2026-11-05": None, DATE: "2026-11-05"})
        self.assertFalse(quality["trends_slot_evidence_complete"])

    def test_trends_slot_timestamp_must_match_its_session_and_window(self):
        row = snapshot()
        row["trends"]["daily_slot_evidence"]["slots"][0]["source_data_time"] = (
            "2026-11-05T09:10:00+05:30"
        )
        quality = assess_snapshot(row, {"2026-11-05": None, DATE: "2026-11-05"})
        self.assertFalse(quality["trends_slot_evidence_complete"])
        self.assertFalse(quality["trends_daily_complete"])

    def test_oi_must_match_snapshot_date_and_have_prior_session(self):
        wrong_date = assess_snapshot(snapshot(oi_date="2026-11-05"), {
            "2026-11-05": None,
            DATE: "2026-11-05",
        })
        no_prior = assess_snapshot(snapshot(), {DATE: None})
        self.assertFalse(wrong_date["participant_oi_complete"])
        self.assertFalse(no_prior["oi_change_available"])
        self.assertFalse(no_prior["complete_for_combined_backtest"])

    def test_index_news_and_closes_must_be_complete(self):
        row = snapshot()
        row["indices"]["SENSEX"]["experimental_news_score"] = None
        quality = assess_snapshot(row, {"2026-11-05": None, DATE: "2026-11-05"})
        self.assertFalse(quality["index_news_complete"])
        self.assertFalse(quality["complete_for_combined_backtest"])

        row = snapshot()
        row["indices"]["BANKNIFTY"]["close_as_of"] = "05/11/2026"
        quality = assess_snapshot(row, {"2026-11-05": None, DATE: "2026-11-05"})
        self.assertFalse(quality["index_closes_complete"])

    def test_capture_and_trends_timestamps_must_be_same_ist_session(self):
        late_capture = assess_snapshot(
            snapshot(capture="2026-11-06T19:00:00Z"),
            {"2026-11-05": None, DATE: "2026-11-05"},
        )
        self.assertFalse(late_capture["eod_capture_valid"])

        row = snapshot()
        row["trends"]["as_of"] = "2026-11-06T19:00:00Z"
        quality = assess_snapshot(row, {"2026-11-05": None, DATE: "2026-11-05"})
        self.assertFalse(quality["trends_daily_complete"])

    def test_complete_trends_snapshot_outranks_later_partial_snapshot(self):
        complete = snapshot()
        partial = snapshot(trends_complete=False)
        for name in ("NIFTY", "SENSEX", "BANKNIFTY"):
            partial["indices"][name]["headline_score"] = 9.0
        self.assertGreater(
            market_snapshot_completeness(complete, DATE),
            market_snapshot_completeness(partial, DATE),
        )

    def test_duplicate_market_dates_are_invalid_archive(self):
        row = snapshot()
        report = validate_archives(
            {"records": [row, row]},
            oi_history(),
            min_sessions=1,
            target_sessions=1,
        )
        self.assertEqual(report["status"], "invalid_archive")
        self.assertEqual(report["market_signal_duplicate_dates"], 1)

    def test_insufficient_complete_sessions_do_not_create_a_score(self):
        report = validate_archives(
            {"records": [snapshot(trends_complete=False)]},
            oi_history(),
            min_sessions=120,
            target_sessions=250,
        )
        self.assertEqual(report["status"], "insufficient_data")
        self.assertEqual(report["combined_backtest_eligible_sessions"], 0)
        self.assertFalse(report["eligible_for_live_score"])
        self.assertFalse(report["score_changed"])

    def test_minimum_threshold_requires_valid_configuration(self):
        with self.assertRaisesRegex(ValueError, "target_sessions"):
            validate_archives({"records": []}, {"records": []}, min_sessions=120, target_sessions=60)

    def test_participant_oi_backfill_is_capped_and_persists_resume_cursor(self):
        failed_snapshot = {"ok": False, "stale": False}
        with mock.patch.object(fetch_and_score, "load_json", return_value={}), \
             mock.patch.object(fetch_and_score, "fetch_participant_oi",
                               return_value=failed_snapshot) as fetch:
            archive = fetch_and_score.update_participant_oi_history()

        self.assertLessEqual(fetch.call_count, 3)
        self.assertEqual(archive["backfill"]["version"], 6)
        self.assertEqual(archive["backfill"]["requests_this_run"], fetch.call_count)
        self.assertIsNotNone(archive["backfill"]["next_date"])
        self.assertGreaterEqual(archive["backfill"]["calendar_days_remaining"], 0)


if __name__ == "__main__":
    unittest.main()


class GoldSilverEODSnapshotTests(unittest.TestCase):
    def test_gold_and_silver_closes_and_component_evidence_are_archived(self):
        import datetime as dt
        import json
        import tempfile
        from pathlib import Path

        class FrozenDateTime(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                value = cls(2026, 11, 6, 20, 30)
                return value.replace(tzinfo=tz) if tz else value

        def instrument(price, score):
            return {
                "price": price, "price_as_of": DATE, "price_source": "MCX official close",
                "change_pct": 0.5, "score": score, "headline_score": score,
                "headlines": [{"title": "sample", "source": "archive", "score": 1, "age_h": 1}],
                "component_breakdown": {"components": {"news": {"score": score, "source": "dated news"}}},
                "asset_search_shadow": {"valid": False, "classified_queries": 0},
            }

        result = {
            "updated": "2026-11-06T15:00Z",
            "participant_oi": {"ok": True, "stale": False, "date": DATE},
            "trends": {
                "ok": True, "stale": False, "as_of": "2026-11-06T19:00:00+05:30",
                "crowd_bull_pct": 55.0, "bull_score_pct": 55.0,
                "bear_score_pct": 25.0, "neutral_score_pct": 20.0,
                "daily_complete": True, "daily": {"date": DATE, "slots": []},
            },
            "market_news": {"ok": True, "as_of": "2026-11-06T15:00Z", "items": []},
            "instruments": {
                name: {"price": 100.0, "price_as_of": "06/11/2026",
                       "change_pct": 0.2, "price_source": "official index close",
                       "headline_score": 1.0, "score": 1.0,
                       "headlines": [], "component_breakdown": {"components": {"news": {"score": 1.0}}}}
                for name in ("NIFTY", "SENSEX", "BANKNIFTY")
            },
        }
        result["instruments"]["GOLD"] = instrument(70000.0, -0.5)
        result["instruments"]["SILVER"] = instrument(80000.0, 0.8)

        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "market_signal_history.json"
            with (
                mock.patch.object(fetch_and_score.dt, "datetime", FrozenDateTime),
                mock.patch.object(fetch_and_score, "SKIP_EVENTS", False),
                mock.patch.object(fetch_and_score, "MARKET_SIGNAL_HISTORY_FILE", str(archive_path)),
                mock.patch.object(fetch_and_score, "load_json", return_value={}),
            ):
                fetch_and_score.update_market_signal_history(result)

            archive = json.loads(archive_path.read_text(encoding="utf-8"))
            record = archive["records"][0]
            self.assertEqual(record["other_assets"]["GOLD"]["close"], 70000.0)
            self.assertTrue(record["other_assets"]["GOLD"]["close_valid"])
            self.assertEqual(record["other_assets"]["SILVER"]["close"], 80000.0)
            self.assertEqual(
                record["other_assets"]["SILVER"]["component_breakdown"]["components"]["news"]["score"],
                0.8,
            )
            self.assertEqual(
                record["indices"]["NIFTY"]["component_breakdown"]["components"]["news"]["score"],
                1.0,
            )

    def test_gold_and_silver_wrong_date_closes_are_not_backtest_eligible(self):
        import datetime as dt
        import json
        import tempfile
        from pathlib import Path

        class FrozenDateTime(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                value = cls(2026, 11, 6, 20, 30)
                return value.replace(tzinfo=tz) if tz else value

        def index_row():
            return {
                "price": 100.0, "price_as_of": "06/11/2026", "price_source": "official close",
                "change_pct": 0.0, "headline_score": 0.0, "score": 0.0, "headlines": [],
            }

        result = {
            "updated": "2026-11-06T15:00Z",
            "participant_oi": {"ok": True, "stale": False, "date": DATE},
            "trends": {"ok": False, "stale": False, "daily": {"date": DATE, "slots": []}},
            "market_news": {"ok": False, "items": []},
            "instruments": {name: index_row() for name in ("NIFTY", "SENSEX", "BANKNIFTY")},
        }
        result["instruments"]["GOLD"] = {
            "price": 70000.0, "price_as_of": "2026-11-05", "price_source": "old MCX close",
        }
        result["instruments"]["SILVER"] = {
            "price": 80000.0, "price_as_of": DATE, "price_source": "MCX official close",
        }

        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "market_signal_history.json"
            with mock.patch.object(fetch_and_score.dt, "datetime", FrozenDateTime), \
                 mock.patch.object(fetch_and_score, "SKIP_EVENTS", False), \
                 mock.patch.object(fetch_and_score, "MARKET_SIGNAL_HISTORY_FILE", str(archive_path)), \
                 mock.patch.object(fetch_and_score, "load_json", return_value={}):
                fetch_and_score.update_market_signal_history(result)
            record = json.loads(archive_path.read_text(encoding="utf-8"))["records"][0]
            self.assertFalse(record["other_assets"]["GOLD"]["close_valid"])
            self.assertIsNone(record["other_assets"]["GOLD"]["close"])
            self.assertTrue(record["other_assets"]["SILVER"]["close_valid"])


class MissingParticipantOIArchiveTests(unittest.TestCase):
    def test_missing_participant_oi_does_not_discard_valid_component_history(self):
        import datetime as dt
        import json
        import tempfile
        from pathlib import Path
        from validate_market_signal_history import assess_snapshot

        class FrozenDateTime(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                value = cls(2026, 11, 6, 20, 30)
                return value.replace(tzinfo=tz) if tz else value

        def index_row():
            return {
                "price": 25000.0,
                "price_as_of": "06/11/2026",
                "price_source": "official same-session close",
                "change_pct": 0.5,
                "headline_score": 1.0,
                "experimental_news_score": 1.0,
                "experimental_headline_count": 2,
                "score": 1.0,
                "headlines": [{"title": "dated headline", "source": "test", "score": 1, "age_h": 1}],
                "component_breakdown": {
                    "components": {
                        "news": {
                            "score": 1.0,
                            "source": "dated asset news",
                            "source_date": DATE,
                            "weight": 40,
                            "included": True,
                        }
                    },
                    "final": {"status": "available", "score": 1.0},
                },
            }

        def commodity_row(price, score):
            return {
                "price": price,
                "price_as_of": DATE,
                "price_source": "MCX official same-session close",
                "change_pct": 0.5,
                "headline_score": score,
                "score": score,
                "headlines": [{"title": "dated commodity headline", "source": "test", "score": 1, "age_h": 1}],
                "component_breakdown": {
                    "components": {
                        "news": {
                            "score": score,
                            "source": "dated commodity news",
                            "source_date": DATE,
                            "weight": 40,
                            "included": True,
                        }
                    },
                    "final": {"status": "available", "score": score},
                },
                "asset_search_shadow": {"valid": False, "classified_queries": 0},
            }

        result = {
            "updated": "2026-11-06T15:00Z",
            "participant_oi": {
                "ok": False,
                "stale": False,
                "date": None,
                "source": "NSE participant-wise OI",
                "reason": "same-session participant OI unavailable",
            },
            "trends": {"ok": False, "stale": False, "error": "no complete daily reading"},
            "market_news": {"ok": False, "items": []},
            "instruments": {
                name: index_row()
                for name in ("NIFTY", "SENSEX", "BANKNIFTY")
            },
        }
        result["instruments"]["GOLD"] = commodity_row(70000.0, -0.5)
        result["instruments"]["SILVER"] = commodity_row(80000.0, 0.8)

        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "market_signal_history.json"
            with mock.patch.object(fetch_and_score.dt, "datetime", FrozenDateTime), \
                 mock.patch.object(fetch_and_score, "SKIP_EVENTS", False), \
                 mock.patch.object(fetch_and_score, "MARKET_SIGNAL_HISTORY_FILE", str(archive_path)), \
                 mock.patch.object(fetch_and_score, "load_json", return_value={}):
                fetch_and_score.update_market_signal_history(result)

            archive = json.loads(archive_path.read_text(encoding="utf-8"))
            self.assertEqual(len(archive["records"]), 1)
            record = archive["records"][0]
            self.assertIsNone(record["participant_oi"]["date"])
            self.assertIsNone(record["participant_oi"]["participants"])
            self.assertEqual(
                record["indices"]["NIFTY"]["component_breakdown"]["components"]["news"]["score"],
                1.0,
            )
            self.assertEqual(
                record["other_assets"]["GOLD"]["component_breakdown"]["components"]["news"]["score"],
                -0.5,
            )
            self.assertTrue(record["other_assets"]["GOLD"]["close_valid"])

            quality = assess_snapshot(record, {})
            self.assertFalse(quality["participant_oi_complete"])
            self.assertFalse(quality["oi_change_available"])
            self.assertFalse(quality["complete_for_combined_backtest"])


class PartialIndexCloseArchiveTests(unittest.TestCase):
    def test_one_stale_index_close_does_not_discard_other_asset_evidence(self):
        import datetime as dt
        import json
        import tempfile
        from pathlib import Path

        class FrozenDateTime(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                value = cls(2026, 11, 6, 20, 30)
                return value.replace(tzinfo=tz) if tz else value

        def instrument(price_date):
            return {
                "price": 25000.0,
                "price_as_of": price_date,
                "price_source": "dated index close",
                "change_pct": 0.5,
                "headlines": [],
                "component_breakdown": {
                    "components": {"news": {"score": 1.0}},
                    "final": {"status": "available", "score": 1.0},
                    "coverage": {"included_count": 1},
                },
            }

        result = {
            "updated": "2026-11-06T15:00Z",
            "participant_oi": {},
            "trends": {},
            "market_news": {},
            "instruments": {
                "NIFTY": instrument(DATE),
                "SENSEX": instrument(DATE),
                "BANKNIFTY": instrument("05/11/2026"),
                "GOLD": instrument(DATE),
                "SILVER": instrument(DATE),
            },
        }

        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "market_signal_history.json"
            with mock.patch.object(fetch_and_score.dt, "datetime", FrozenDateTime), \\
                 mock.patch.object(fetch_and_score, "SKIP_EVENTS", False), \\
                 mock.patch.object(fetch_and_score, "MARKET_SIGNAL_HISTORY_FILE", str(archive_path)), \\
                 mock.patch.object(fetch_and_score, "load_json", return_value={}):
                fetch_and_score.update_market_signal_history(result)

            archive = json.loads(archive_path.read_text(encoding="utf-8"))

        self.assertEqual(len(archive["records"]), 1)
        record = archive["records"][0]
        self.assertTrue(record["indices"]["NIFTY"]["close_valid"])
        self.assertFalse(record["indices"]["BANKNIFTY"]["close_valid"])
        self.assertIsNone(record["indices"]["BANKNIFTY"]["close"])
        self.assertEqual(
            record["indices"]["BANKNIFTY"]["component_breakdown"]["final"]["score"],
            1.0,
        )
        self.assertTrue(record["other_assets"]["GOLD"]["close_valid"])
        self.assertTrue(record["other_assets"]["SILVER"]["close_valid"])
