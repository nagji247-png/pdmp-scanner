import unittest

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


if __name__ == "__main__":
    unittest.main()
